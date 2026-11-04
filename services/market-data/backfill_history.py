"""历史日线回补（前复权），供 us-110 回测预计算使用。

数据源沿用 archive 快照同一家（AkShare），不引入新的行情供应商、不引入数据库。
复权口径：
- 主序列使用 AkShare 前复权（qfq）日线，字段含 OHLC + 成交额；
- 同时复用 build_leaderboard.adjust_price_series() 的份额折算/除权修正逻辑，
  对原始（未复权）日线做交叉校验，量化仅靠涨跌幅阈值修正时的残留偏差。

缓存落在 services/market-data/cache/history/（不进 git），按标的一份 JSON，
支持分批、断点续抓。非交易日/区间外的行会被剔除。

用法：
    # 抓取 ETF 与个股，每次最多 2500 只（约 8 分钟），可重复执行补完剩余
    python services/market-data/backfill_history.py --limit 2500
    # 只跑抽样校验（对比 qfq 与 build_leaderboard 复权逻辑）
    python services/market-data/backfill_history.py --validate-sample 120
    # 汇总覆盖率与异常标的
    python services/market-data/backfill_history.py --report
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import akshare as ak

SERVICE_DIR = Path(__file__).resolve().parent
ROOT = SERVICE_DIR.parents[1]
DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
CACHE_DIR = SERVICE_DIR / "cache" / "history"
CALENDAR_PATH = CACHE_DIR / "_calendar.json"
MANIFEST_PATH = CACHE_DIR / "_manifest.json"
VALIDATE_PATH = CACHE_DIR / "_validate.json"

sys.path.insert(0, str(SERVICE_DIR))
from build_leaderboard import adjust_price_series, is_bond_etf, price_limit  # noqa: E402

MAX_RETRIES = 3
RETRY_SLEEP = 1.5


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def trading_days(start: str, end: str) -> list[str]:
    """交易日历，缓存到本地，避免每次回补都请求。"""
    if CALENDAR_PATH.exists():
        all_days = read_json(CALENDAR_PATH)  # type: ignore[assignment]
    else:
        cal = ak.tool_trade_date_hist_sina()
        all_days = [str(x)[:10] for x in cal["trade_date"]]
        write_json(CALENDAR_PATH, all_days)
    return [d for d in all_days if start <= d <= end]


def latest_trading_day() -> str:
    """archive 里最新的真实交易日（跳过节假日仍在跑的假快照）。"""
    cal = set(trading_days("2000-01-01", "2100-01-01"))
    folders = [f.name for f in DATA_DIR.joinpath("archive").iterdir()
               if f.is_dir() and (f / "stock-latest.json").exists()]
    return max(d for d in folders if d in cal)


def load_universe() -> list[dict]:
    """archive 最新快照的全量标的，按成交额降序，ETF 剔除债券/货币类。"""
    latest = DATA_DIR / "archive" / latest_trading_day()
    items = []
    for kind, fname in (("etf", "etf-latest.json"), ("stock", "stock-latest.json")):
        for row in read_json(latest / fname):  # type: ignore[union-attr]
            code = str(row.get("code") or "")
            name = str(row.get("name") or "").strip()
            if not code:
                continue
            if kind == "etf" and is_bond_etf(name):
                continue
            items.append({
                "code": code,
                "name": name,
                "kind": kind,
                "amount": float(row.get("amount") or 0.0),
            })
    items.sort(key=lambda x: (x["kind"], -x["amount"], x["code"]))
    return items


def bare_code(code: str) -> str:
    return code[2:] if code[:2] in ("sh", "sz", "bj") else code


def fetch_daily(code: str, kind: str, start: str, end: str, adjust: str):
    symbol = bare_code(code)
    if kind == "etf":
        return ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start.replace("-", ""),
                                   end_date=end.replace("-", ""), adjust=adjust)
    return ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start.replace("-", ""),
                              end_date=end.replace("-", ""), adjust=adjust)


def to_rows(df) -> list[list]:
    rows = []
    for rec in df.to_dict("records"):
        day = str(rec.get("日期"))[:10]
        close = rec.get("收盘")
        if close is None or float(close) <= 0:
            continue
        rows.append([
            day,
            round(float(rec.get("开盘") or 0), 4),
            round(float(rec.get("最高") or 0), 4),
            round(float(rec.get("最低") or 0), 4),
            round(float(close), 4),
            round(float(rec.get("成交额") or 0), 2),
        ])
    rows.sort(key=lambda r: r[0])
    return rows


def cache_path(item: dict) -> Path:
    return CACHE_DIR / item["kind"] / f"{item['code']}.json"


def fetch_and_store(item: dict, days: list[str], start: str, end: str, adjust: str) -> dict:
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = fetch_daily(item["code"], item["kind"], start, end, adjust)
            rows = [r for r in to_rows(df) if r[0] in days]
            entry = {
                "code": item["code"],
                "name": item["name"],
                "kind": item["kind"],
                "source": "akshare",
                "adjust": adjust,
                "start": start,
                "end": end,
                "rows": rows,
                "fetchedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            write_json(cache_path(item), entry)
            return {"rows": len(rows), "first": rows[0][0] if rows else None,
                    "last": rows[-1][0] if rows else None, "error": None}
        except Exception as exc:  # noqa: BLE001 - 网络异常需逐只记录后继续
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(RETRY_SLEEP * attempt)
    return {"rows": 0, "first": None, "last": None, "error": last_err}


def load_manifest() -> dict:
    return read_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}  # type: ignore[return-value]


def run_fetch(args: argparse.Namespace) -> None:
    end = args.end or latest_trading_day()
    start = args.start or f"{int(end[:4]) - 1}{end[4:]}"
    days = trading_days(start, end)
    print(f"区间 {start} ~ {end}，交易日 {len(days)} 个")

    universe = load_universe()
    if args.kind != "all":
        universe = [x for x in universe if x["kind"] == args.kind]
    manifest = load_manifest()
    pending = [x for x in universe
               if args.refresh or not cache_path(x).exists() or x["code"] not in manifest]
    total_pending = len(pending)
    plan = pending[: args.limit] if args.limit else pending
    print(f"标的 {len(universe)} 只，待抓 {total_pending} 只，本次 {len(plan)} 只")

    ok = fail = 0
    t0 = time.time()
    for i, item in enumerate(plan, 1):
        result = fetch_and_store(item, days, start, end, args.adjust)
        manifest[item["code"]] = {**result, "name": item["name"], "kind": item["kind"],
                                 "amount": item["amount"], "adjust": args.adjust}
        if result["error"]:
            fail += 1
        else:
            ok += 1
        if i % 50 == 0 or i == len(plan):
            write_json(MANIFEST_PATH, manifest)
            elapsed = time.time() - t0
            print(f"  {i}/{len(plan)} ok={ok} fail={fail} {elapsed:.0f}s "
                  f"({elapsed / i:.2f}s/只)")
        if args.sleep:
            time.sleep(args.sleep)
    write_json(MANIFEST_PATH, manifest)
    print(f"完成：ok={ok} fail={fail}；剩余未抓 {total_pending - len(plan)} 只")


def run_validate(args: argparse.Namespace) -> None:
    """抽样对比：qfq 主序列 vs build_leaderboard 的比率复权，检查残留偏差。"""
    manifest = load_manifest()
    cached = [c for c in manifest if (CACHE_DIR / manifest[c]["kind"] / f"{c}.json").exists()]
    sample = random.Random(20261104).sample(cached, min(args.validate_sample, len(cached)))
    end = args.end or latest_trading_day()
    start = args.start or f"{int(end[:4]) - 1}{end[4:]}"
    days = trading_days(start, end)
    out = []
    for code in sample:
        entry = read_json(cache_path(manifest[code] | {"code": code}))  # type: ignore[arg-type]
        qfq = {r[0]: r[4] for r in entry["rows"]}  # type: ignore[index]
        if not qfq:
            continue
        name, kind = entry["name"], entry["kind"]  # type: ignore[index]
        try:
            raw_df = fetch_daily(code, kind, days[0], days[-1], "")
        except Exception as exc:  # noqa: BLE001
            out.append({"code": code, "name": name, "kind": kind, "error": str(exc)[:120]})
            continue
        raw = {str(rec["日期"])[:10]: float(rec["收盘"]) for rec in raw_df.to_dict("records")
               if rec.get("收盘")}
        common = sorted(set(raw) & set(qfq))
        if len(common) < 2:
            out.append({"code": code, "name": name, "kind": kind, "error": "raw/qfq 无重叠"})
            continue
        adj = adjust_price_series(days, raw, code, name, kind)
        q_ret = qfq[common[-1]] / qfq[common[0]] - 1
        a_ret = adj[common[-1]] / adj[common[0]] - 1
        max_ratio_gap = max(abs(adj[d] / qfq[d] - 1) for d in common)
        out.append({
            "code": code, "name": name, "kind": kind,
            "qfqRet": round(q_ret, 4), "ratioAdjRet": round(a_ret, 4),
            "driftPp": round((a_ret - q_ret) * 100, 2),
            "maxRatioGap": round(max_ratio_gap, 4),
        })
        time.sleep(0.05)
    write_json(VALIDATE_PATH, out)
    drift = sorted([x for x in out if "driftPp" in x], key=lambda x: -abs(x["driftPp"]))
    print(f"校验样本 {len(out)} 只；口径漂移 |>2pp| 的 {sum(1 for x in drift if abs(x['driftPp']) > 2)} 只")
    for x in drift[:8]:
        print(" ", x["code"], x["name"], "drift", x["driftPp"], "pp", "maxRatioGap", x["maxRatioGap"])


def run_report(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    end = args.end or latest_trading_day()
    start = args.start or f"{int(end[:4]) - 1}{end[4:]}"
    days = trading_days(start, end)
    latest_archive = DATA_DIR / "archive" / end
    archive_close = {}
    for kind, fname in (("stock", "stock-latest.json"), ("etf", "etf-latest.json")):
        for row in read_json(latest_archive / fname):  # type: ignore[union-attr]
            archive_close[str(row.get("code"))] = float(row.get("latest") or 0)

    buckets = {"12m": 0, "6m": 0, "3m": 0, "lt3m": 0, "empty": 0}
    anomalies = []
    by_kind = {"stock": {"n": 0, "12m": 0}, "etf": {"n": 0, "12m": 0}}
    missing = []
    for code, m in manifest.items():
        by_kind.setdefault(m["kind"], {"n": 0, "12m": 0})["n"] += 1
        path = CACHE_DIR / m["kind"] / f"{code}.json"
        if not path.exists() or not m.get("rows"):
            buckets["empty"] += 1
            missing.append(code)
            continue
        entry = read_json(path)
        rows = entry["rows"]  # type: ignore[index]
        n = len(rows)
        if n >= 240:
            buckets["12m"] += 1
            by_kind[m["kind"]]["12m"] += 1
        elif n >= 120:
            buckets["6m"] += 1
        elif n >= 60:
            buckets["3m"] += 1
        else:
            buckets["lt3m"] += 1
            anomalies.append({"code": code, "name": m["name"], "reason": f"仅{n}个交易日"})
            continue
        close = rows[-1][4]
        ac = archive_close.get(code)
        if ac and abs(close / ac - 1) > 0.01:
            anomalies.append({"code": code, "name": m["name"],
                              "reason": f"末收盘与archive偏差{(close / ac - 1) * 100:.2f}%"})
        lim = price_limit(code, m["name"], m["kind"])
        worst = max(abs(rows[i][4] / rows[i - 1][4] - 1) for i in range(1, n))
        if worst > lim + 0.02:
            anomalies.append({"code": code, "name": m["name"],
                              "reason": f"单日涨跌{worst * 100:.1f}%超限"})

    payload = {
        "range": {"start": start, "end": end, "tradingDays": len(days)},
        "symbols": len(manifest),
        "buckets": buckets,
        "byKind": by_kind,
        "anomalies": anomalies[:200],
        "anomalyCount": len(anomalies),
        "emptyCount": len(missing),
    }
    write_json(CACHE_DIR / "_coverage.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"覆盖率明细：{CACHE_DIR / '_coverage.json'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回补 6~12 个月前复权日线，供回测预计算。")
    parser.add_argument("--start", default=None, help="起始日 YYYY-MM-DD，默认 end 往前一年")
    parser.add_argument("--end", default=None, help="结束日，默认 archive 最新真实交易日")
    parser.add_argument("--kind", choices=["all", "stock", "etf"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="本次最多抓取多少只（0=不限）")
    parser.add_argument("--adjust", default="qfq", choices=["qfq", "hfq", ""])
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--refresh", action="store_true", help="忽略已有缓存重新抓取")
    parser.add_argument("--validate-sample", type=int, default=0)
    parser.add_argument("--report", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.report:
        run_report(args)
    elif args.validate_sample:
        run_validate(args)
    else:
        run_fetch(args)
