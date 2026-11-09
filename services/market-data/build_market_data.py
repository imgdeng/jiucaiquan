from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from market_data.fetchers import (
    fetch_etf_from_akshare,
    fetch_stock_from_akshare,
    read_latest_csv,
    sort_quotes,
)
from market_data.schema import CHINA_TZ, QuoteSnapshot, now_china_iso

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "apps" / "web" / "public" / "data"
DEFAULT_SOURCE_DIR = Path(os.environ.get("JCQ_SOURCE_DIR") or str(ROOT))


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.move(str(temp_path), str(path))


def quote_payload(quotes: list[QuoteSnapshot]) -> list[dict]:
    return [quote.to_dict() for quote in sort_quotes(quotes)]


def existing_count(path: Path) -> int:
    try:
        return len(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return 0


def fetch_with_fallback(
    live_fetcher: Callable[[], list[QuoteSnapshot]],
    csv_dir: Path,
    prefix: str,
    output_path: Path,
    allow_live: bool,
) -> tuple[int, bool, str | None]:
    """返回 (可用条数, 本次是否抓到新数据, 错误信息)。

    抓取失败且无 CSV 兜底时，不覆盖 output_path 的既有快照，
    条数按既有文件统计，fresh=False，避免 status 误报 0 条。
    """
    errors: list[str] = []
    quotes: list[QuoteSnapshot] = []

    if allow_live:
        try:
            quotes = live_fetcher()
        except Exception as exc:
            errors.append(f"live fetch failed: {exc}")

    if not quotes:
        try:
            quotes = read_latest_csv(csv_dir, prefix)
        except Exception as exc:
            errors.append(f"csv fallback failed: {exc}")

    if not quotes:
        return existing_count(output_path), False, "; ".join(errors) or "live fetch failed and no csv fallback available"

    write_json_atomic(output_path, quote_payload(quotes))
    return len(quotes), True, None


def build_status(output_dir: Path, stock_count: int, etf_count: int, errors: list[str],
                 fully_fresh: bool) -> None:
    now = now_china_iso()
    status_path = output_dir / "data-status.json"
    previous_last_success = None
    try:
        previous_last_success = json.loads(status_path.read_text(encoding="utf-8")).get("lastSuccessAt")
    except (OSError, json.JSONDecodeError):
        pass
    status = {
        "generatedAt": now,
        "lastSuccessAt": now if fully_fresh else previous_last_success,
        "stockCount": stock_count,
        "etfCount": etf_count,
        "errors": errors,
    }
    write_json_atomic(status_path, status)


def load_trading_calendar() -> set[str] | None:
    """交易所交易日历；不可用时返回 None，由调用方退化为工作日判断。"""
    try:
        import akshare as ak

        return {str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"]}
    except Exception as exc:  # 日历只是判定手段，失败不应中断构建
        print(f"trade calendar unavailable: {exc}", file=sys.stderr)
        return None


def resolve_trade_date(today: str, calendar: set[str] | None) -> str | None:
    """今日是否为交易日；非交易日返回 None，调用方跳过抓取/归档/提交。"""
    if calendar is not None:
        return today if today in calendar else None
    if datetime.fromisoformat(today).weekday() >= 5:
        return None
    print(f"::warning::trade calendar unavailable; falling back to weekday check for {today}", file=sys.stderr)
    return today


def quote_signature(path: Path) -> list[tuple] | None:
    """快照的行情指纹，用于判断是否产生了新的交易时段数据。"""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return [(row.get("code"), row.get("latest"), row.get("amount")) for row in rows]


def latest_archive_dir(output_dir: Path) -> Path | None:
    archive_root = output_dir / "archive"
    if not archive_root.exists():
        return None
    dirs = sorted(path for path in archive_root.iterdir() if path.is_dir())
    return dirs[-1] if dirs else None


def unchanged_since_last_archive(output_dir: Path) -> bool:
    """行情与最新归档逐值相同时，说明没有新的交易时段（节假日/跨零点/重复运行）。"""
    last_dir = latest_archive_dir(output_dir)
    if last_dir is None:
        return False
    for name in ("stock-latest.json", "etf-latest.json"):
        current = quote_signature(output_dir / name)
        previous = quote_signature(last_dir / name)
        if current is None or previous is None or current != previous:
            return False
    print(f"snapshot identical to archive/{last_dir.name}: no new trading session", file=sys.stderr)
    return True


def mark_chain_skipped() -> None:
    """告诉 workflow 后续步骤不必执行（不归档、不重建、不提交）。"""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write("skip=true\n")


def archive_snapshot(output_dir: Path, trade_date: str) -> None:
    archive_dir = output_dir / "archive" / trade_date
    archive_dir.mkdir(parents=True, exist_ok=True)
    for src_name in ("stock-latest.json", "etf-latest.json", "data-status.json"):
        src = output_dir / src_name
        if src.exists():
            shutil.copy2(str(src), str(archive_dir / src_name))
    print(f"archive saved to {archive_dir}")


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve()
    source_dir = Path(args.source_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    allow_live = not args.no_live
    errors: list[str] = []
    stock_count = existing_count(output_dir / "stock-latest.json")
    etf_count = existing_count(output_dir / "etf-latest.json")
    stock_fresh = etf_fresh = False

    trade_date = datetime.now(CHINA_TZ).date().isoformat()
    if args.archive:
        calendar = load_trading_calendar()
        resolved = resolve_trade_date(trade_date, calendar)
        if resolved is None:
            print(f"non-trading day {trade_date}: skip fetch/archive/commit", file=sys.stderr)
            mark_chain_skipped()
            return 0
        trade_date = resolved

    if args.command in ("fetch-stock", "build-market-data"):
        stock_count, stock_fresh, error = fetch_with_fallback(
            fetch_stock_from_akshare,
            source_dir / "stock_data",
            "stock_",
            output_dir / "stock-latest.json",
            allow_live,
        )
        if error:
            errors.append(f"stock: {error}")
        print(f"stock output: {output_dir / 'stock-latest.json'} count={stock_count}")

    if args.command in ("fetch-etf", "build-market-data"):
        etf_count, etf_fresh, error = fetch_with_fallback(
            fetch_etf_from_akshare,
            source_dir / "etf_data",
            "etf_",
            output_dir / "etf-latest.json",
            allow_live,
        )
        if error:
            errors.append(f"etf: {error}")
        print(f"etf output: {output_dir / 'etf-latest.json'} count={etf_count}")

    if args.command == "fetch-stock":
        all_fresh = stock_fresh
    elif args.command == "fetch-etf":
        all_fresh = etf_fresh
    else:
        all_fresh = stock_fresh and etf_fresh

    build_status(output_dir, stock_count, etf_count, errors, all_fresh)

    if args.archive:
        if not all_fresh:
            print("archive skipped: snapshot is stale/partial", file=sys.stderr)
        elif unchanged_since_last_archive(output_dir):
            mark_chain_skipped()
        else:
            archive_snapshot(output_dir, trade_date)

    if errors:
        print("warnings:", " | ".join(errors), file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build market data files for jiucaiquan web.")
    parser.add_argument("command", choices=["fetch-stock", "fetch-etf", "build-market-data"])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--no-live", action="store_true", help="Skip AkShare live fetch and use latest local CSV fallback.")
    parser.add_argument("--archive", action="store_true", help="Archive snapshot to data/archive/<trading-day>/ after a fresh fetch.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
