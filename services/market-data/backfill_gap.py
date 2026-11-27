"""补齐股票故障期缺失的每日快照（缺口自愈）。

背景：akshare 1.20.46 改名导致股票实时抓取断裂（2026-11-14 起），且归档门控为
"股票+ETF 都新鲜才归档"，ETF 快照同期一并缺失。本脚本用东方财富日 K 接口
（stock_zh_a_hist / fund_etf_hist_em）按代码一次性取回缺口期数据，
重建与实时快照同构的 archive 目录。

两种模式：
- --auto：自动检测缺口（最新归档日 → 昨日之间的交易日，无归档目录者）并修复；
  缺口 >30 天时拒绝执行（防意外大任务）。供每日 workflow 自愈使用。
- --start/--end：手动指定缺口区间。供 workflow_dispatch 使用。

口径对齐（与实时 spot 快照逐字段一致）：
- latest = 当日收盘价；close = 昨收（前一交易日收盘价，缺口首日用最后归档日收盘）；
- changePct = 当日涨跌幅（历史接口原值）；amount = 成交额（元）；
- snapshotAt = 各交易日 15:30（收盘后），保证 leaderboard 按快照日期归类正确；
- source 如实标注 backfill，与实时抓取可区分。
- 停牌（当日无 K 线）的代码不入当日快照，与"无数据"语义一致。

幂等：已存在的 archive/<date>/ 目录跳过，可安全重跑。只写归档，不覆盖 *-latest.json。
副产品：把 akshare 交易日历写入 ops/trade-calendar.json（看门狗的独立日历来源）。
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_data.schema import CHINA_TZ  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "apps" / "web" / "public" / "data"
CALENDAR_PATH = ROOT / "ops" / "trade-calendar.json"
MAX_AUTO_GAP_DAYS = 30

STOCK_SOURCE = "akshare.stock_zh_a_hist_backfill"
ETF_SOURCE = "akshare.fund_etf_hist_em_backfill"


def emit_has_gap(pending: list[str]) -> None:
    """告诉 workflow 本次补了缺口：即使后续构建步骤判 skip（快照无变化），
    排行榜/回测重建与提交也必须执行，否则补出的归档不会入库。"""
    if not pending:
        return
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write("has_gap=true\n")
    print(f"::notice::backfill {len(pending)} days; downstream rebuild+commit required")


def strip_prefix(code: str) -> str:
    return code[2:] if code[:2] in ("sh", "sz", "bj") else code


def load_trading_calendar() -> tuple[set[str], str]:
    """交易日历：优先 akshare 实时接口；不可用时读 ops/trade-calendar.json。"""
    try:
        import akshare as ak

        days = {str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"]}
        if days:
            return days, "akshare.tool_trade_date_hist_sina"
    except Exception as exc:
        print(f"::warning::akshare calendar unavailable ({exc}); trying local file", file=sys.stderr)
    if CALENDAR_PATH.exists():
        data = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        return {d for d in data.get("tradingDays", [])}, f"{CALENDAR_PATH.name} (committed)"
    return set(), "none"


def save_trading_calendar(days: set[str], source: str) -> None:
    """把日历写入 ops/trade-calendar.json（看门狗的独立日历；只保留 2024 年以后控制体积）。"""
    if not days:
        return
    recent = sorted(d for d in days if d >= "2024-01-01")
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "updatedAt": datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
        "tradingDays": recent,
    }
    tmp = CALENDAR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CALENDAR_PATH)
    print(f"trade calendar saved: {CALENDAR_PATH} ({len(recent)} days since 2024, source={source})")


def resolve_gap(args: argparse.Namespace, calendar: set[str], archive_dir: Path) -> tuple[list[str], str]:
    """计算待补交易日列表与昨收锚点日（第一个缺口日的前一交易日）。

    --auto 扫描 [最早归档日, 昨日] 全窗口（不只看尾部），找出日历上是交易日
    但无归档目录的所有缺口——中段缺口（如 11-13 → [缺] → 11-27）同样能检出。
    """
    if args.auto:
        existing = sorted(p.name for p in archive_dir.iterdir() if p.is_dir()) if archive_dir.exists() else []
        if not existing:
            print("::error::--auto 需要至少一个已归档交易日作锚点")
            sys.exit(1)
        first = date.fromisoformat(existing[0])
        today = datetime.now(CHINA_TZ).date()
        window: list[str] = []
        d = first + timedelta(days=1)
        while d < today:  # 今日快照由构建步骤负责，补数只补昨日以前
            window.append(d.isoformat())
            d += timedelta(days=1)
        if calendar:
            missing = [x for x in window if x in calendar and not (archive_dir / x / "stock-latest.json").exists()]
        else:
            print("::warning::无日历，按工作日判断缺口", file=sys.stderr)
            missing = [x for x in window if date.fromisoformat(x).weekday() < 5 and not (archive_dir / x / "stock-latest.json").exists()]
        if len(missing) > MAX_AUTO_GAP_DAYS:
            print(f"::error::缺口 {len(missing)} 天超过上限 {MAX_AUTO_GAP_DAYS}，请人工核查后用手动模式分批补")
            sys.exit(1)
        if not missing:
            return [], existing[-1]
        # 锚点 = 第一个缺口日之前最近的已归档交易日
        first_gap = date.fromisoformat(missing[0])
        before = [x for x in existing if date.fromisoformat(x) < first_gap]
        anchor = before[-1] if before else existing[0]
        return missing, anchor
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days: list[str] = []
    d = start
    while d <= end:
        iso = d.isoformat()
        if (calendar and iso in calendar) or (not calendar and d.weekday() < 5):
            days.append(iso)
        d += timedelta(days=1)
    pending = [x for x in days if not (archive_dir / x / "stock-latest.json").exists()]
    # 锚点 = 起始日前最近的已归档交易日（手动模式无法感知归档，按日历回退）
    anchor_d = start - timedelta(days=1)
    while calendar and anchor_d.isoformat() not in calendar and anchor_d > start - timedelta(days=15):
        anchor_d -= timedelta(days=1)
    return pending, anchor_d.isoformat()


def load_universe(data_dir: Path) -> tuple[list[dict], list[dict]]:
    stocks = json.loads((data_dir / "stock-latest.json").read_text(encoding="utf-8"))
    etfs = json.loads((data_dir / "etf-latest.json").read_text(encoding="utf-8"))
    return stocks, etfs


def fetch_hist_daily(ak, kind: str, code: str, start: str, end: str) -> dict[str, dict]:
    """单代码日 K：返回 {date: {open,close,high,low,pct,amount}}，date 为 YYYY-MM-DD。

    异常一律吞掉并返回空 dict：北交所等个别代码 EM 日 K 不支持，
    单码失败不应炸掉整批补数（调用方按"无数据"跳过该码）。
    """
    symbol = strip_prefix(code)
    try:
        if kind == "stock":
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="", timeout=20)
        else:
            df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="")
        out: dict[str, dict] = {}
        for row in df.to_dict("records"):
            day = str(row.get("日期"))[:10]
            if not day:
                continue
            out[day] = {
                "open": row.get("开盘"),
                "close": row.get("收盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "pct": row.get("涨跌幅"),
                "amount": row.get("成交额"),
            }
        return out
    except Exception as exc:
        print(f"  {code}: hist fetch failed ({type(exc).__name__}: {str(exc)[:80]})", file=sys.stderr)
        return {}


def build_day_rows(
    universe: list[dict],
    hist_by_code: dict[str, dict[str, dict]],
    day: str,
    prev_close_by_code: dict[str, float],
    snapshot_at: str,
    source: str,
) -> tuple[list[dict], dict[str, float]]:
    """拼某交易日的快照行；返回 (行列表, 当日收盘价表供次日作昨收)。"""
    rows: list[dict] = []
    closes: dict[str, float] = {}
    for item in universe:
        code = item["code"]
        bar = hist_by_code.get(code, {}).get(day)
        if not bar:
            continue  # 停牌/无数据
        try:
            latest = float(bar["close"])
            high = float(bar["high"])
            low = float(bar["low"])
        except (TypeError, ValueError):
            continue
        if latest <= 0 or high <= 0 or low <= 0 or high < low:
            continue
        prev_close = prev_close_by_code.get(code)
        close_val = prev_close if prev_close and prev_close > 0 else latest
        try:
            pct = float(bar["pct"]) if bar.get("pct") is not None else None
        except (TypeError, ValueError):
            pct = None
        amount = bar.get("amount")
        rows.append({
            "code": code,
            "name": item["name"],
            "latest": latest,
            "open": float(bar["open"]) if bar.get("open") is not None else None,
            "high": high,
            "low": low,
            "close": close_val,
            "changePct": pct,
            "amount": float(amount) if amount is not None else None,
            "snapshotAt": snapshot_at,
            "source": source,
        })
        closes[code] = latest
    rows.sort(key=lambda r: (r["amount"] or 0), reverse=True)
    return rows, closes


def write_snapshot(day_dir: Path, rows: list[dict], name: str) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / name
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_status(day_dir: Path, day: str, stock_rows: list[dict], etf_rows: list[dict]) -> None:
    status = {
        "generatedAt": f"{day}T15:30:00+08:00",
        "lastSuccessAt": f"{day}T15:30:00+08:00",
        "stockCount": len(stock_rows),
        "etfCount": len(etf_rows),
        "errors": [f"backfilled from stock_zh_a_hist/fund_etf_hist_em (gap repair {day})"],
    }
    (day_dir / "data-status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_all(ak, kind: str, universe: list[dict], fetch_start: str, fetch_end: str, workers: int) -> tuple[dict[str, dict[str, dict]], list[str]]:
    name = "stock_zh_a_hist" if kind == "stock" else "fund_etf_hist_em"
    hist_by_code: dict[str, dict[str, dict]] = {}
    failed: list[str] = []

    def one(item: dict):
        try:
            return item["code"], fetch_hist_daily(ak, kind, item["code"], fetch_start, fetch_end)
        except Exception as exc:  # 双保险：线程内任何异常都不炸池
            print(f"  {item['code']}: thread error ({exc})", file=sys.stderr)
            return item["code"], {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, item): item for item in universe}
        done = 0
        for fut in as_completed(futures):
            code, data = fut.result()
            if data:
                hist_by_code[code] = data
            else:
                failed.append(code)
            done += 1
            if done % 500 == 0:
                print(f"  {name}: {done}/{len(universe)} codes, {len(failed)} empty")
    return hist_by_code, failed


def run(args: argparse.Namespace) -> int:
    import akshare as ak

    output_dir = Path(args.output_dir).resolve()
    archive_dir = output_dir / "archive"

    calendar, cal_source = load_trading_calendar()
    save_trading_calendar(calendar, cal_source)

    pending, anchor = resolve_gap(args, calendar, archive_dir)
    emit_has_gap(pending)
    skipped_hint = "auto" if args.auto else f"{args.start}~{args.end}"
    if not pending:
        print(f"nothing to backfill ({skipped_hint})")
        return 0
    print(f"anchor(prev close)={anchor}; gap days to backfill: {pending}")

    stocks, etfs = load_universe(output_dir)
    print(f"universe: stock {len(stocks)} / etf {len(etfs)}")

    # 抓取窗口：锚点日（取昨收）到缺口末日
    fetch_start = anchor.replace("-", "")
    fetch_end = pending[-1].replace("-", "")

    print(f"fetching stock daily bars {fetch_start}~{fetch_end} ...")
    stock_hist, stock_failed = fetch_all(ak, "stock", stocks, fetch_start, fetch_end, args.workers)
    print(f"stock bars: {len(stock_hist)} codes ok, {len(stock_failed)} empty")
    print(f"fetching etf daily bars {fetch_start}~{fetch_end} ...")
    etf_hist, etf_failed = fetch_all(ak, "etf", etfs, fetch_start, fetch_end, args.workers)
    print(f"etf bars: {len(etf_hist)} codes ok, {len(etf_failed)} empty")

    # 昨收初值：锚点日（缺口前一交易日）的当日收盘价
    def prev_closes(hist: dict[str, dict[str, dict]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for code, days_data in hist.items():
            anchor_bar = days_data.get(anchor)
            if anchor_bar:
                try:
                    out[code] = float(anchor_bar["close"])
                except (TypeError, ValueError):
                    pass
        return out

    prev_stock = prev_closes(stock_hist)
    prev_etf = prev_closes(etf_hist)

    for day in pending:
        snapshot_at = f"{day}T15:30:00+08:00"
        stock_rows, prev_stock = build_day_rows(stocks, stock_hist, day, prev_stock, snapshot_at, STOCK_SOURCE)
        etf_rows, prev_etf = build_day_rows(etfs, etf_hist, day, prev_etf, snapshot_at, ETF_SOURCE)
        if not stock_rows:
            print(f"::error::{day}: stock rows empty, abort to avoid writing broken archive")
            return 1
        day_dir = archive_dir / day
        write_snapshot(day_dir, stock_rows, "stock-latest.json")
        write_snapshot(day_dir, etf_rows, "etf-latest.json")
        write_status(day_dir, day, stock_rows, etf_rows)
        print(f"{day}: stock {len(stock_rows)} rows, etf {len(etf_rows)} rows archived")

    if stock_failed:
        print(f"::warning::stock codes with no bars: {len(stock_failed)} e.g. {stock_failed[:5]}")
    if etf_failed:
        print(f"::warning::etf codes with no bars: {len(etf_failed)} e.g. {etf_failed[:5]}")
    print("backfill done")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing archive snapshots from EM daily bars.")
    parser.add_argument("--auto", action="store_true", help="自动检测缺口（最后归档日→昨日）并修复")
    parser.add_argument("--start", help="手动模式：缺口起始日 YYYY-MM-DD（含）")
    parser.add_argument("--end", help="手动模式：缺口结束日 YYYY-MM-DD（含）")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args()


if __name__ == "__main__":
    ns = parse_args()
    if not ns.auto and not (ns.start and ns.end):
        print("::error::需要 --auto 或同时提供 --start/--end")
        sys.exit(1)
    raise SystemExit(run(ns))
