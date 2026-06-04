from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .schema import QuoteSnapshot, build_quote, now_china_iso


def _akshare():
    import akshare as ak  # type: ignore

    return ak


def fetch_stock_from_akshare() -> list[QuoteSnapshot]:
    """Fetch A-share snapshots.

    This is the extracted minimal equivalent of backtest/aitrade/today.py
    get_real_time_data_from_akshare(), normalized for the static site.
    """
    ak = _akshare()
    df = ak.stock_zh_a_spot()
    snapshot_at = now_china_iso()
    quotes: list[QuoteSnapshot] = []
    for row in df.to_dict("records"):
        quote = build_quote(row, source="akshare.stock_zh_a_spot", snapshot_at=snapshot_at)
        if quote:
            quotes.append(quote)
    return quotes


def fetch_etf_from_akshare() -> list[QuoteSnapshot]:
    """Fetch ETF snapshots.

    This is the extracted minimal equivalent of backtest/aitrade/monitor.py
    ETFMonitor.get_etf_real_time_data(), normalized for the static site.
    """
    ak = _akshare()
    df = ak.fund_etf_category_sina("ETF基金")
    snapshot_at = now_china_iso()
    quotes: list[QuoteSnapshot] = []
    for row in df.to_dict("records"):
        quote = build_quote(row, source="akshare.fund_etf_category_sina", snapshot_at=snapshot_at)
        if quote:
            quotes.append(quote)
    return quotes


def read_latest_csv(directory: Path, prefix: str) -> list[QuoteSnapshot]:
    files = sorted(
        [path for path in directory.glob(f"{prefix}*.csv") if path.is_file() and "holding" not in path.name.lower()],
        reverse=True,
    )
    if not files:
        return []
    return read_csv(files[0], source=f"csv:{files[0].name}")


def read_csv(path: Path, source: str | None = None) -> list[QuoteSnapshot]:
    snapshot_at = now_china_iso()
    quotes: list[QuoteSnapshot] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            quote = build_quote(row, source=source or f"csv:{path.name}", snapshot_at=snapshot_at)
            if quote:
                quotes.append(quote)
    return quotes


def sort_quotes(quotes: Iterable[QuoteSnapshot]) -> list[QuoteSnapshot]:
    return sorted(quotes, key=lambda quote: (quote.amount or 0), reverse=True)
