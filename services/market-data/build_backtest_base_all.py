"""生成 us-116 全量历史底座（7,180 只），与现有 58 只底座并存互不影响。

只读本地 cache 与 archive，不联网、不改 archive、不改线上 JSON。
输出：
    services/market-data/backtest-base/history_base_all.json
    services/market-data/backtest-base/meta_all.json

口径：
- cache 为 AkShare qfq；每只按 archive 首个重叠日的原始价做常数缩放，锚定后不再二次缩放。
- 底座区间 2025-10-31 ~ 2026-06-05；停牌/未上市日写 null，start 为首日下标。
- 无 base 区间数据或与 archive 无重叠日的标的显式列入 excluded，不静默补齐。
- 任一声明标的的 cache 文件缺失即抛 FileNotFoundError。

用法：
    python services/market-data/build_backtest_base_all.py
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
ROOT = SERVICE_DIR.parents[1]
DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
CACHE_DIR = SERVICE_DIR / "cache" / "history"
OUT_DIR = SERVICE_DIR / "backtest-base"
BASE_PATH = OUT_DIR / "history_base_all.json"
META_PATH = OUT_DIR / "meta_all.json"

BASE_START, BASE_END = "2025-10-31", "2026-06-05"
TIERS = (("2w", 10), ("4w", 20), ("3m", 60), ("6m", 120), ("9m", 180), ("12m", 240))
RAW_LIMIT = 40 * 1024 * 1024
SAMPLE_CODES = ("sh512170", "sh510300", "sh600519")

sys.path.insert(0, str(SERVICE_DIR))
from build_leaderboard import adjust_price_series  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_calendar() -> list[str]:
    path = CACHE_DIR / "_calendar.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少交易日历：{path}")
    return read_json(path)


def load_universe() -> dict[str, dict]:
    manifest_path = CACHE_DIR / "_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"缺少缓存清单：{manifest_path}")
    manifest = read_json(manifest_path)
    if not manifest:
        raise RuntimeError("缓存清单为空，拒绝生成全量底座")
    return manifest


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


def tier_days(cached: set[str], merged: list[str]) -> dict[str, int]:
    return {label: sum(1 for d in merged[-n:] if d in cached) for label, n in TIERS}


def pick_cold(manifest: dict[str, dict], kind: str) -> str:
    candidates = [
        (float(v.get("amount") or 0), code)
        for code, v in manifest.items()
        if v.get("kind") == kind and int(v.get("rows") or 0) >= 60
    ]
    if not candidates:
        raise RuntimeError(f"没有可用于抽样的 {kind} 标的")
    return sorted(candidates)[0][1]


def main() -> int:
    t0 = time.time()
    cal = load_calendar()
    cal_set = set(cal)
    manifest = load_universe()
    real_days, archive_px = load_archive(cal_set)

    base_dates = [d for d in cal if BASE_START <= d <= BASE_END]
    if not base_dates:
        raise RuntimeError(f"底座区间无交易日：{BASE_START} ~ {BASE_END}")
    merged = sorted(set(base_dates) | set(real_days))
    anchor_day = real_days[0]
    di = {d: i for i, d in enumerate(base_dates)}

    symbols: dict[str, dict] = {}
    excluded: list[dict] = []
    zero_base: list[dict] = []
    per_symbol_days: dict[str, int] = {}
    merged_days: dict[str, int] = {}
    cache_dates: dict[str, set[str]] = {}
    anchor_fallback = 0
    anchor_offsets: dict[str, int] = {}
    for code in sorted(manifest):
        entry = manifest[code]
        kind, name = entry["kind"], str(entry.get("name") or "")
        rows = load_cache(code, kind)
        cache_dates[code] = set(rows)
        merged_days[code] = sum(1 for d in merged if d in cache_dates[code])
        base = {d: rows[d] for d in base_dates if d in rows}
        arch = archive_px.get(code, {})
        if not base:
            if not rows:
                excluded.append({"code": code, "name": name, "asset": kind,
                                 "reason": "cache 无数据", "cacheDays": 0})
                continue
            if not arch:
                excluded.append({"code": code, "name": name, "asset": kind,
                                 "reason": "无 archive 重叠日，无法锚定", "cacheDays": len(rows)})
                continue
            # 2026-06-05 后上市/全区间停牌：底座区间无数据。保留一格 null 占位以满足消费端
            # “start+len(rows)<=日期数”契约，实际行情由 archive 兜底；不伪造价格。
            symbols[code] = {"asset": kind, "name": name,
                             "start": len(base_dates) - 1, "rows": [None]}
            per_symbol_days[code] = 0
            zero_base.append({
                "code": code, "name": name, "asset": kind,
                "reason": "底座区间无数据（新上市或全区间停牌），archive 兜底",
                "cacheDays": len(rows), "cacheFirst": sorted(rows)[0],
                "archiveDays": len(arch),
            })
            continue
        common = sorted(set(rows) & set(arch))
        if not common:
            excluded.append({"code": code, "name": name, "asset": kind,
                             "reason": "无 archive 重叠日，无法锚定", "cacheDays": len(rows)})
            continue
        anchor = common[0]
        if anchor != anchor_day:
            anchor_fallback += 1
            anchor_offsets[code] = real_days.index(anchor)
        scale = arch[anchor] / rows[anchor][4]

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
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    raw_bytes = len(raw.encode("utf-8"))
    fields = 5
    if raw_bytes > RAW_LIMIT:
        # 瘦身：只保留 OHLC 四位小数价格，去掉成交额，不砍标的
        for sym in symbols.values():
            sym["rows"] = [None if r is None else r[:4] for r in sym["rows"]]
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        raw_bytes = len(raw.encode("utf-8"))
        fields = 4
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BASE_PATH.write_text(raw, encoding="utf-8")
    gz_bytes = len(gzip.compress(raw.encode("utf-8"), 9))

    # 抽样：逐档可用日数 + 拼接日跳变
    samples = list(SAMPLE_CODES)
    samples.append(pick_cold(manifest, "stock"))
    samples.append(pick_cold(manifest, "etf"))
    sample_rows = []
    splice_max = 0.0
    for code in samples:
        entry = manifest[code]
        rows = load_cache(code, entry["kind"])
        cached = set(rows)
        tier = tier_days(cached, merged)
        base_close = {}
        arch = archive_px.get(code, {})
        common = sorted(cached & set(arch))
        scale = arch[common[0]] / rows[common[0]][4] if common else 1.0
        for d in base_dates:
            if d in rows:
                base_close[d] = rows[d][4] * scale
        scaled = {**base_close, **arch}
        adj = adjust_price_series(merged, scaled, code, entry["name"], entry["kind"])
        join = anchor_day
        prev = max(base_close) if base_close else None
        qfq = {d: r[4] for d, r in rows.items()}
        diff = None
        if prev and join in adj and prev in adj and join in qfq and prev in qfq:
            diff = round(abs((adj[join] / adj[prev] - 1) - (qfq[join] / qfq[prev] - 1)) * 100, 3)
            splice_max = max(splice_max, diff)
        sample_rows.append({
            "code": code, "name": entry["name"], "asset": entry["kind"],
            "cacheDays": len(rows), "tierDays": tier,
            "passes": {k: tier[k] >= n for k, n in TIERS},
            "joinDay": join, "joinDiffPp": diff,
        })

    base_days = list(per_symbol_days.values())
    avail_days = list(merged_days.values())
    tier_rows = {code: tier_days(cache_dates[code], merged) for code in manifest if code in symbols}
    counts = {
        f">={n}": {
            "total": sum(1 for v in tier_rows.values() if v[label] >= n),
            "etf": sum(1 for c, v in tier_rows.items()
                       if v[label] >= n and manifest[c]["kind"] == "etf"),
            "stock": sum(1 for c, v in tier_rows.items()
                         if v[label] >= n and manifest[c]["kind"] == "stock"),
        }
        for label, n in TIERS
    }
    meta = {
        "file": "history_base_all.json",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "services/market-data/build_backtest_base_all.py",
        "sources": {
            "cache": "services/market-data/cache/history/（95MB，依赖 _manifest.json）",
            "archive": "apps/web/public/data/archive/",
            "universe": "cache _manifest.json 全量 7180 只",
        },
        "coverage": {
            "start": base_dates[0], "end": base_dates[-1], "tradingDays": len(base_dates),
            "universeSymbols": len(manifest),
            "symbolsInBase": len(symbols),
            "rowsFields": fields,
            "rowsFieldsNote": "fields=5 为 [open,high,low,close,amount]；超 40MB 时自动瘦身为 fields=4（仅 OHLC）",
            "perSymbolDays": {"min": min(avail_days), "median": statistics.median(avail_days), "max": max(avail_days)},
            "perSymbolDaysNote": "合并 archive 后的可用日数（≤243），用于 2w~12m 门槛判断",
            "baseDays": {"min": min(base_days), "median": statistics.median(base_days), "max": max(base_days)},
            "daysBySymbol": merged_days,
            "baseDaysBySymbol": per_symbol_days,
            "zeroBaseCount": len(zero_base),
            "thresholdPolicy": "不足门槛不剔除：标的保留在底座，由消费端按档位置灰；"
                               "仅底座区间无数据的 242 只以 null 占位（见 zeroBase）",
            "zeroBase": zero_base,
            "tierCounts": counts,
            "excluded": excluded,
        },
        "priceBasis": {
            "value": "qfq_anchored_to_archive",
            "explain": "cache 为 AkShare qfq；每只按 archive 首个重叠日原始价做常数缩放，使拼接点连续；"
                       "日收益口径为前复权。",
            "adjustFunction": "build_leaderboard.adjust_price_series",
            "anchorDay": anchor_day,
            "anchorFallbackCount": anchor_fallback,
            "anchorFallbackOffsets": anchor_offsets,
            "consumerNote": "底座已锚定，构建时与 archive 一并交给 adjust_price_series；不得再次缩放。",
        },
        "validation": {
            "spliceMaxDiffPp": round(splice_max, 3),
            "samples": sample_rows,
            "note": "抽样 5 只：512170 / 510300 / 600519 + 最低成交额个股与 ETF。",
        },
        "size": {
            "raw": raw_bytes, "rawMB": round(raw_bytes / 1024 / 1024, 2),
            "gzip": gz_bytes, "gzipMB": round(gz_bytes / 1024 / 1024, 2),
            "limit": RAW_LIMIT,
        },
        "elapsedSeconds": round(time.time() - t0, 1),
        "consumerContract": {
            "path": "services/market-data/backtest-base/history_base_all.json",
            "missingFile": "必须抛错（FileNotFoundError）并终止构建，禁止静默跳过或用 archive 短样本降级",
            "schema": "dates 为共享日期索引；symbols[code].start 为首日下标；rows 与 dates 逐日对齐，停牌日为 null",
            "fields": "rows=[open,high,low,close,amount]（fields=5）或 [open,high,low,close]（fields=4，超 40MB 时）",
        },
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"全量底座 {len(symbols)}/{len(manifest)} 只 × {len(base_dates)} 日；"
          f"fields={fields}；raw {meta['size']['rawMB']}MB / gzip {meta['size']['gzipMB']}MB；"
          f"耗时 {meta['elapsedSeconds']}s")
    print(f"排除 {len(excluded)} 只：{[x['code'] for x in excluded]}")
    print(f"抽样拼接最大差 {meta['validation']['spliceMaxDiffPp']}pp")
    print(f"输出 {BASE_PATH} 与 {META_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
