"""us-110 12m 数据可用性核查（只读缓存 + archive，不产出生产文件）。

核查 59 只候选池在本地回补缓存中的覆盖天数、日期连续性、与 archive 的重叠价格、
拼接后的复权跳变，以及固定底座入库形态的体积/耗时。

用法：
    python services/market-data/audit_12m_coverage.py
产物：team/us/us-110/12m_audit.json
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import akshare as ak

SERVICE_DIR = Path(__file__).resolve().parent
ROOT = SERVICE_DIR.parents[1]
DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
CACHE_DIR = SERVICE_DIR / "cache" / "history"
EVIDENCE_PATH = ROOT / "team" / "us" / "us-110" / "p1_evidence.json"
OUT_PATH = ROOT / "team" / "us" / "us-110" / "12m_audit.json"

sys.path.insert(0, str(SERVICE_DIR))
from build_leaderboard import adjust_price_series  # noqa: E402
from backfill_history import fetch_daily, to_rows  # noqa: E402

THRESHOLDS = (("2w", 10), ("4w", 20), ("6m", 120), ("9m", 180), ("12m", 240))
BASE_START, BASE_END = "2025-11-03", "2026-06-05"
AUDIT_START, AUDIT_END = "2025-10-31", "2026-11-03"
SPLICE_SAMPLE = 5


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def trading_calendar() -> list[str]:
    cache = CACHE_DIR / "_calendar.json"
    if cache.exists():
        all_days = read_json(cache)
    else:
        all_days = [str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"]]
    return all_days


def load_pool() -> list[dict]:
    return read_json(EVIDENCE_PATH)["pool"]["symbols"]


def load_cache(code: str, kind: str) -> dict[str, list]:
    path = CACHE_DIR / kind / f"{code}.json"
    if not path.exists():
        return {}
    return {r[0]: r for r in read_json(path)["rows"]}


def archive_raw(cal_set: set[str]):
    """archive 真实交易日的原始快照价 {code: {date: latest}}。"""
    series: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}
    real_days = set()
    for folder in sorted(d for d in DATA_DIR.joinpath("archive").iterdir() if d.is_dir()):
        stocks = read_json(folder / "stock-latest.json")
        etfs = read_json(folder / "etf-latest.json")
        if not stocks:
            continue
        day = str(stocks[0].get("snapshotAt", ""))[:10]
        if day not in cal_set:
            continue
        real_days.add(day)
        for item in stocks + etfs:
            code = str(item.get("code") or "")
            px = item.get("latest")
            if code and px:
                series.setdefault(code, {})[day] = float(px)
                names[code] = str(item.get("name") or "").strip()
    return sorted(real_days), series, names


def main() -> int:
    t0 = time.time()
    cal = trading_calendar()
    cal_set = set(cal)
    audit_cal = [d for d in cal if AUDIT_START <= d <= AUDIT_END]
    pool = load_pool()
    t_arch = time.time()
    real_days, arch_px, _ = archive_raw(cal_set)
    archive_seconds = round(time.time() - t_arch, 2)
    print(f"archive 真实交易日 {len(real_days)}（{real_days[0]} ~ {real_days[-1]}）")

    coverage, continuity, missing_by = [], [], {}
    for item in pool:
        code, kind, name = item["code"], item["kind"], item["name"]
        rows = load_cache(code, kind)
        dates = sorted(rows)
        duplicates = len(rows) != len(dates)
        non_trading = [d for d in dates if d not in cal_set]
        span = [d for d in audit_cal if dates and dates[0] <= d <= dates[-1]]
        missing = [d for d in span if d not in rows]
        # 连续缺口（自然日跨度>1 的交易日缺口，识别停牌）
        gaps = []
        for i in range(1, len(dates)):
            between = [d for d in cal if dates[i - 1] < d < dates[i]]
            if between:
                gaps.append({"after": dates[i - 1], "before": dates[i], "missing": len(between)})
        coverage.append({
            # days 是缓存全区间可用天数（如中微公司 235），不是 12m 窗口口径；
            # 12m 窗口（合并索引末 240 日，2025-11-05 ~ 2026-11-03）的可用天数为 231，
            # 以 backtest-base/meta.json 的 constraints.insufficient 为唯一正确口径。
            "code": code, "name": name, "kind": kind, "days": len(dates),
            "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
            "thresholds": {label: len(dates) >= n for label, n in THRESHOLDS},
            "missingTradingDays": len(missing), "maxGap": max((g["missing"] for g in gaps), default=0),
        })
        continuity.append({"code": code, "duplicates": duplicates,
                           "nonTradingDates": non_trading, "missingCount": len(missing)})
        if missing:
            missing_by[code] = missing

    # 原始未复权价格（拼接底座必须是 raw，不能用 cache 里的 qfq）
    raw: dict[str, dict[str, list]] = {}
    t_fetch = time.time()
    for item in pool:
        code, kind, name = item["code"], item["kind"], item["name"]
        try:
            df = fetch_daily(code, kind, "2025-10-31", "2026-11-03", "")
            rows = to_rows(df)
            raw[code] = {r[0]: r for r in rows if r[0] in cal_set}
        except Exception as exc:  # noqa: BLE001
            raw[code] = {}
            print("fetch raw fail", code, type(exc).__name__)
    fetch_seconds = round(time.time() - t_fetch, 2)

    # 重叠日：raw 底座 vs archive 原始快照
    overlap = []
    for item in pool:
        code = item["code"]
        common = sorted(set(raw.get(code, {})) & set(arch_px.get(code, {})))
        if not common:
            continue
        dev = max(abs(raw[code][d][4] / arch_px[code][d] - 1) for d in common)
        overlap.append({"code": code, "name": item["name"], "dates": len(common),
                        "maxDeviation": round(dev, 5)})
    overlap.sort(key=lambda x: -x["maxDeviation"])

    # 抽 3~5 只 × 5 个重叠日，给出可比对的点位
    sample_points = []
    for row in overlap[:SPLICE_SAMPLE]:
        code = row["code"]
        common = sorted(set(raw[code]) & set(arch_px[code]))
        picked = [common[0], common[len(common) // 4], common[len(common) // 2],
                  common[3 * len(common) // 4], common[-1]]
        for d in picked:
            sample_points.append({"code": code, "date": d,
                                  "baseRaw": round(raw[code][d][4], 3),
                                  "archiveRaw": round(arch_px[code][d], 3),
                                  "deviation": round(raw[code][d][4] / arch_px[code][d] - 1, 5)})

    # 拼接复权：base raw + archive raw，统一 adjust_price_series，检查拼接日收益
    join_dates = sorted(set([d for d in cal if BASE_START <= d <= BASE_END]) | set(real_days))
    splice = []
    full_ret = []
    t_adj = time.time()
    for item in pool:
        code, kind, name = item["code"], item["kind"], item["name"]
        base = {d: r[4] for d, r in raw.get(code, {}).items() if BASE_START <= d <= BASE_END}
        arch = {d: px for d, px in arch_px.get(code, {}).items() if d >= real_days[0]}
        if not base or not arch:
            continue
        merged = {**base, **arch}
        adj = adjust_price_series(join_dates, merged, code, name, kind)
        qfq = {d: r[4] for d, r in load_cache(code, kind).items()}
        first_arch = min(arch)
        prev = max(d for d in merged if d < first_arch)
        if prev in adj and first_arch in adj and prev in qfq and first_arch in qfq:
            ret_join = adj[first_arch] / adj[prev] - 1
            ret_qfq = qfq[first_arch] / qfq[prev] - 1
            splice.append({"code": code, "name": name, "prev": prev, "join": first_arch,
                           "joinRet": round(ret_join, 5), "qfqRet": round(ret_qfq, 5),
                           "diffPp": round((ret_join - ret_qfq) * 100, 3)})
        common = sorted(set(adj) & set(qfq))
        if len(common) > 1:
            drift = (adj[common[-1]] / adj[common[0]] - 1) - (qfq[common[-1]] / qfq[common[0]] - 1)
            full_ret.append({"code": code, "name": name, "driftPp": round(drift * 100, 2)})
    adjust_seconds = round(time.time() - t_adj, 2)

    # 固定底座入库形态：raw OHLC + amount，日期共享索引
    base_dates = [d for d in cal if BASE_START <= d <= BASE_END]
    di = {d: i for i, d in enumerate(base_dates)}
    panel = {"schemaVersion": 1, "dataStart": base_dates[0], "dataEnd": base_dates[-1],
             "dates": base_dates, "symbols": {}}
    for item in pool:
        code = item["code"]
        rows = [raw[code][d] for d in sorted(raw.get(code, {})) if BASE_START <= d <= BASE_END]
        if not rows:
            continue
        panel["symbols"][code] = {
            "asset": item["kind"], "name": item["name"],
            "start": di[rows[0][0]],
            "rows": [[r[1], r[2], r[3], r[4], round(r[5])] for r in rows],
        }
    payload = json.dumps(panel, ensure_ascii=False, separators=(",", ":")).encode()
    gz = gzip.compress(payload, 9)

    def bucket(label: str) -> dict:
        required = next(n for k, n in THRESHOLDS if k == label)
        ok = sum(1 for x in coverage if x["thresholds"][label])
        bad = [{"code": x["code"], "name": x["name"], "days": x["days"],
                "gap": required - x["days"]}
               for x in coverage if not x["thresholds"][label]]
        return {"ok": ok, "notOk": len(bad), "required": required,
                "minDays": min(x["days"] for x in coverage), "shortfall": bad}

    days = [x["days"] for x in coverage]
    result = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pool": {"total": len(pool),
                 "etf": sum(1 for x in pool if x["kind"] == "etf"),
                 "stock": sum(1 for x in pool if x["kind"] == "stock")},
        "coverage": {
            "min": min(days), "max": max(days), "median": statistics.median(days),
            "thresholds": {label: bucket(label) for label, _ in THRESHOLDS},
            "symbols": coverage,
        },
        "continuity": {
            "calendar": {"start": audit_cal[0], "end": audit_cal[-1], "days": len(audit_cal)},
            "duplicateDays": sum(1 for x in continuity if x["duplicates"]),
            "nonTradingDates": {x["code"]: x["nonTradingDates"] for x in continuity if x["nonTradingDates"]},
            "symbolsWithMissing": len(missing_by),
            "missingTotal": sum(len(v) for v in missing_by.values()),
            "maxSingleGap": max(x["maxGap"] for x in coverage),
            "missingDates": missing_by,
        },
        "priceOverlap": {
            "symbolsCompared": len(overlap),
            "maxDeviation": max((x["maxDeviation"] for x in overlap), default=None),
            "worst": overlap[:5],
            "samplePoints": sample_points,
        },
        "splice": {
            "symbolsChecked": len(splice),
            "maxDiffPp": max((abs(x["diffPp"]) for x in splice), default=None),
            "maxDailyRet": round(max((abs(x["joinRet"]) for x in splice), default=0), 5),
            "worst": sorted(splice, key=lambda x: -abs(x["diffPp"]))[:5],
            "fullWindowDriftPp": {
                "median": round(statistics.median(x["driftPp"] for x in full_ret), 2) if full_ret else None,
                "maxAbs": round(max((abs(x["driftPp"]) for x in full_ret), default=0), 2),
                "worst": sorted(full_ret, key=lambda x: -abs(x["driftPp"]))[:5],
            },
        },
        "baseArtifact": {
            "format": "raw OHLC+amount，共享日期索引，json.gz",
            "start": base_dates[0], "end": base_dates[-1], "dates": len(base_dates),
            "symbols": len(panel["symbols"]),
            "rawBytes": len(payload), "gzipBytes": len(gz),
            "fetchSeconds": fetch_seconds,
            "archiveReadSeconds": archive_seconds,
            "adjustSeconds": adjust_seconds,
            "dailyRebuildSeconds": round(archive_seconds + adjust_seconds, 2),
            "buildSeconds": round(time.time() - t0, 1),
        },
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"池 {result['pool']['total']}（ETF {result['pool']['etf']} / 个股 {result['pool']['stock']}）")
    print(f"天数 min/median/max = {result['coverage']['min']}/{result['coverage']['median']}/{result['coverage']['max']}")
    for label, _ in THRESHOLDS:
        b = result["coverage"]["thresholds"][label]
        print(f"  {label}: 可 {b['ok']} / 不足 {b['notOk']}")
    print(f"连续性：重复日标的 {result['continuity']['duplicateDays']}，非交易日 {len(result['continuity']['nonTradingDates'])}，"
          f"有缺口标的 {result['continuity']['symbolsWithMissing']}，最大单标的缺口 {result['continuity']['maxSingleGap']} 日")
    print(f"重叠价格 {result['priceOverlap']['symbolsCompared']} 只，最大偏差 {result['priceOverlap']['maxDeviation']}")
    print(f"拼接跳变 {result['splice']['symbolsChecked']} 只，最大与 qfq 差 {result['splice']['maxDiffPp']}pp，"
          f"拼接日最大日收益 {result['splice']['maxDailyRet']}，全窗口漂移中位 "
          f"{result['splice']['fullWindowDriftPp']['median']}pp / 最大 {result['splice']['fullWindowDriftPp']['maxAbs']}pp")
    b = result["baseArtifact"]
    print(f"底座 {b['symbols']} 只 × {b['dates']} 日：raw {b['rawBytes'] / 1024:.1f}KB，gzip {b['gzipBytes'] / 1024:.1f}KB，"
          f"一次性生成 {b['buildSeconds']}s（抓取 {b['fetchSeconds']}s），每日重建约 {b['dailyRebuildSeconds']}s")
    print(f"输出 {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
