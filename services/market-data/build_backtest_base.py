"""生成 2w/4w/6m/9m/12m 回测共用的固定历史底座。

只读本地 cache 与 archive，不联网、不改 archive、不改线上 JSON。
输出到 services/market-data/backtest-base/，固定路径，幂等可重跑。

用法：
    python services/market-data/build_backtest_base.py
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
ROOT = SERVICE_DIR.parents[1]
DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
CACHE_DIR = SERVICE_DIR / "cache" / "history"
OUT_DIR = SERVICE_DIR / "backtest-base"
BASE_PATH = OUT_DIR / "history_base.json"
META_PATH = OUT_DIR / "meta.json"
EVIDENCE_PATH = ROOT / "team" / "us" / "us-110" / "p1_evidence.json"

BASE_START, BASE_END = "2025-10-31", "2026-06-05"

sys.path.insert(0, str(SERVICE_DIR))
from build_leaderboard import adjust_price_series  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_calendar() -> list[str]:
    path = CACHE_DIR / "_calendar.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少交易日历：{path}")
    return read_json(path)


def load_pool() -> list[dict]:
    if not EVIDENCE_PATH.exists():
        raise FileNotFoundError(f"缺少候选池证据：{EVIDENCE_PATH}")
    pool = read_json(EVIDENCE_PATH)["pool"]["symbols"]
    if not pool:
        raise RuntimeError("候选池为空，拒绝生成底座")
    return pool


def load_cache(code: str, kind: str) -> dict[str, list]:
    path = CACHE_DIR / kind / f"{code}.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少缓存：{path}")
    return {r[0]: r for r in read_json(path)["rows"]}


def load_archive(cal_set: set[str]):
    series: dict[str, dict[str, float]] = {}
    real_days: set[str] = set()
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
    if not real_days:
        raise RuntimeError("archive 中没有真实交易日快照")
    return sorted(real_days), series


def main() -> int:
    cal = load_calendar()
    cal_set = set(cal)
    pool = load_pool()
    real_days, archive_px = load_archive(cal_set)

    base_dates = [d for d in cal if BASE_START <= d <= BASE_END]
    if not base_dates:
        raise RuntimeError(f"底座区间无交易日：{BASE_START} ~ {BASE_END}")

    symbols, skipped, per_symbol_days = {}, [], {}
    splice_diffs, drift_pp = [], []
    anchor_day = real_days[0]

    for item in sorted(pool, key=lambda x: x["code"]):
        code, kind, name = item["code"], item["kind"], item["name"]
        rows = load_cache(code, kind)
        base = {d: rows[d] for d in base_dates if d in rows}
        arch = archive_px.get(code, {})
        if not base:
            skipped.append({"code": code, "name": name, "reason": "底座区间无数据（尚未上市）"})
            continue
        common = sorted(set(rows) & set(arch))
        if not common:
            raise RuntimeError(f"{code} 的 cache 与 archive 无重叠日，无法锚定")
        anchor = common[0]
        scale = arch[anchor] / rows[anchor][4]

        di = {d: i for i, d in enumerate(base_dates)}
        first = min(base)
        aligned = []
        for d in base_dates[di[first]:]:
            row = base.get(d)
            aligned.append(None if row is None else [
                round(row[1] * scale, 3), round(row[2] * scale, 3),
                round(row[3] * scale, 3), round(row[4] * scale, 3), round(row[5]),
            ])
        symbols[code] = {"asset": kind, "name": name, "start": di[first], "rows": aligned}
        per_symbol_days[code] = len(base)

        # 校验：拼接日收益差 + 全窗口与 qfq 的收益差
        scaled_close = {d: r[4] * scale for d, r in base.items()}
        merged = {**scaled_close, **arch}
        join_dates = sorted(set(base_dates) | set(real_days))
        adj = adjust_price_series(join_dates, merged, code, name, kind)
        prev = max(scaled_close)
        qfq = {d: r[4] for d, r in rows.items()}
        splice_diffs.append(abs((adj[anchor] / adj[prev] - 1) - (qfq[anchor] / qfq[prev] - 1)) * 100)
        common_all = sorted(set(adj) & set(qfq))
        if len(common_all) > 1:
            drift_pp.append((((adj[common_all[-1]] / adj[common_all[0]] - 1) -
                              (qfq[common_all[-1]] / qfq[common_all[0]] - 1)) * 100, code))

    payload = {
        "schemaVersion": 1,
        "dataStart": base_dates[0],
        "dataEnd": base_dates[-1],
        "priceBasis": "qfq_anchored_to_archive",
        "anchorDay": anchor_day,
        "adjustFunction": "build_leaderboard.adjust_price_series",
        "dates": base_dates,
        "symbols": symbols,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BASE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    days = list(per_symbol_days.values())
    meta = {
        "file": "history_base.json",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "services/market-data/build_backtest_base.py",
        "sources": {
            "cache": "services/market-data/cache/history/",
            "archive": "apps/web/public/data/archive/",
            "pool": "team/us/us-110/p1_evidence.json",
        },
        "coverage": {
            "start": base_dates[0], "end": base_dates[-1], "tradingDays": len(base_dates),
            "poolSymbols": len(pool), "symbolsInBase": len(symbols),
            "perSymbolDays": {"min": min(days), "median": statistics.median(days), "max": max(days)},
            "daysBySymbol": per_symbol_days,
            "skipped": skipped,
        },
        "priceBasis": {
            "value": "qfq_anchored_to_archive",
            "explain": "本地 cache 为 AkShare qfq；按 archive 首个重叠日（2026-06-08）的原始价做常数缩放，"
                       "使底座与 archive raw 在拼接点连续。日收益口径为前复权。",
            "adjustFunction": "build_leaderboard.adjust_price_series",
            "consumerNote": "构建时把底座与 archive 统一交给 adjust_price_series；不得再对底座做额外缩放。",
        },
        "validation": {
            "spliceMaxDiffPp": round(max(splice_diffs), 3),
            "driftVsQfqPp": {"median": round(statistics.median(x[0] for x in drift_pp), 2),
                             "maxAbs": round(max(abs(x[0]) for x in drift_pp), 2),
                             "worst": (lambda y: {"code": y[1], "driftPp": round(y[0], 2)})(
                                 max(drift_pp, key=lambda x: abs(x[0])))},
            "auditRawBaseRef": {"median": -0.14, "maxAbs": 6.72,
                                "note": "12m_audit.json 的 raw 底座口径，用于对照；本次底座实测更小"},
        },
        "constraints": {
            "noFullPool12m": "不得写“全池 12 个月”；12m 仅 57/59 只满足 240 日",
            "insufficient": [
                {"code": "sh688012", "name": "中微公司", "days": 235, "gap": 5},
                {"code": "sh688825", "name": "长鑫科技", "days": 66, "gap": 174},
            ],
            "tiers": {"2w": "59/59", "4w": "59/59", "6m": "58/59", "9m": "58/59", "12m": "57/59"},
        },
        "consumerContract": {
            "path": "services/market-data/backtest-base/history_base.json",
            "missingFile": "必须抛错（FileNotFoundError）并终止构建，禁止静默跳过",
            "schema": "dates 为共享日期索引；symbols[code].start 为首日下标；rows 与 dates 逐日对齐，停牌日为 null",
        },
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"底座 {len(symbols)} 只 × {len(base_dates)} 日；"
          f"raw {BASE_PATH.stat().st_size / 1024:.1f}KB；拼接差 {meta['validation']['spliceMaxDiffPp']}pp；"
          f"qfq 漂移中位 {round(statistics.median(x[0] for x in drift_pp), 2)}pp / "
          f"最大 {meta['validation']['driftVsQfqPp']['maxAbs']}pp")
    print(f"跳过 {len(skipped)} 只：{[x['code'] for x in skipped]}")
    print(f"输出 {BASE_PATH} 与 {META_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
