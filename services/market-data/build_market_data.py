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
) -> tuple[int, str | None]:
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
        return 0, "; ".join(errors) or "live fetch failed and no csv fallback available"

    write_json_atomic(output_path, quote_payload(quotes))
    return len(quotes), None


def build_status(output_dir: Path, stock_count: int, etf_count: int, errors: list[str]) -> None:
    now = now_china_iso()
    status = {
        "generatedAt": now,
        "lastSuccessAt": now if stock_count or etf_count else None,
        "stockCount": stock_count,
        "etfCount": etf_count,
        "errors": errors,
    }
    write_json_atomic(output_dir / "data-status.json", status)


def archive_snapshot(output_dir: Path, today_str: str) -> None:
    archive_dir = output_dir / "archive" / today_str
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

    if args.command in ("fetch-stock", "build-market-data"):
        stock_count, error = fetch_with_fallback(
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
        etf_count, error = fetch_with_fallback(
            fetch_etf_from_akshare,
            source_dir / "etf_data",
            "etf_",
            output_dir / "etf-latest.json",
            allow_live,
        )
        if error:
            errors.append(f"etf: {error}")
        print(f"etf output: {output_dir / 'etf-latest.json'} count={etf_count}")

    build_status(output_dir, stock_count, etf_count, errors)

    if args.archive:
        archive_snapshot(output_dir, datetime.now(CHINA_TZ).date().isoformat())

    if errors:
        print("warnings:", " | ".join(errors), file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build market data files for jiucaiquan web.")
    parser.add_argument("command", choices=["fetch-stock", "fetch-etf", "build-market-data"])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--no-live", action="store_true", help="Skip AkShare live fetch and use latest local CSV fallback.")
    parser.add_argument("--archive", action="store_true", help="Archive today's snapshot to data/archive/YYYY-MM-DD/ after fetch.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
