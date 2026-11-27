from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from .schema import QuoteSnapshot, build_quote, now_china_iso


def _akshare():
    import akshare as ak  # type: ignore

    return ak


def _stock_zh_a_spot_em():
    """东财全市场 spot 接口的惰性加载器；不可用时返回 None（该函数在部分版本未入顶层导出）。"""
    try:
        from akshare.stock_a.stock_zh_a_spot import stock_zh_a_spot_em  # type: ignore
    except Exception:
        return None
    return stock_zh_a_spot_em


def fetch_stock_from_akshare() -> list[QuoteSnapshot]:
    """Fetch A-share snapshots，三级数据源降级（新 sina spot → 东财 spot → 旧 sina spot）。

    背景：akshare 1.20.46 将 `stock_zh_a_spot` 更名为 `stock_zh_a_spot_sina`，
    导致线上股票行情 2026-11-14 起断裂。为避免上游接口漂移再次打断管道，
    按源顺序尝试，任一源产出非空快照即返回；`source` 字段如实记录实际使用的接口。
    全部源失败时抛 RuntimeError（由调用方按既有 fallback 链路处理）。
    """
    ak = _akshare()
    attempts: list[tuple[str, Any]] = []
    sina_new = getattr(ak, "stock_zh_a_spot_sina", None)
    if sina_new is not None:
        attempts.append(("akshare.stock_zh_a_spot_sina", sina_new))
    em_spot = _stock_zh_a_spot_em()
    if em_spot is not None:
        attempts.append(("akshare.stock_zh_a_spot_em", em_spot))
    legacy = getattr(ak, "stock_zh_a_spot", None)
    if legacy is not None:
        attempts.append(("akshare.stock_zh_a_spot", legacy))

    errors: list[str] = []
    for source, loader in attempts:
        try:
            df = loader()
            snapshot_at = now_china_iso()
            quotes: list[QuoteSnapshot] = []
            for row in df.to_dict("records"):
                quote = build_quote(row, source=source, snapshot_at=snapshot_at)
                if quote:
                    quotes.append(quote)
            if quotes:
                return quotes
            errors.append(f"{source}: returned {len(quotes)} rows")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    raise RuntimeError("all stock sources failed: " + " | ".join(errors))


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
