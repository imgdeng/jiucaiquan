from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


CHINA_TZ = timezone(timedelta(hours=8))


@dataclass
class QuoteSnapshot:
    code: str
    name: str
    latest: float
    open: float | None
    high: float
    low: float
    close: float
    changePct: float | None
    amount: float | None
    snapshotAt: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_china_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat(timespec="seconds")


def normalize_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    if code.startswith(("sh", "sz", "bj")):
        return code
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith(("0", "1", "2", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return code


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(str(value).replace(",", "").replace("%", ""))
        if parsed != parsed:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def build_quote(row: dict[str, Any], source: str, snapshot_at: str) -> QuoteSnapshot | None:
    code = normalize_code(row.get("代码") or row.get("symbol") or row.get("code"))
    name = str(row.get("名称") or row.get("name") or "").strip()
    latest = to_float(row.get("最新价") or row.get("最新") or row.get("latest"))
    open_price = to_float(row.get("今开") or row.get("开盘") or row.get("open"))
    high = to_float(row.get("最高") or row.get("high"))
    low = to_float(row.get("最低") or row.get("low"))
    close = to_float(row.get("收盘") or row.get("昨收") or row.get("close") or latest)
    change_pct = to_float(row.get("涨跌幅") or row.get("changePct"))
    amount = to_float(row.get("成交额") or row.get("amount"))

    if not code or not name or latest is None or high is None or low is None:
        return None
    if high <= 0 or low <= 0 or high < low:
        return None

    close_value = close if close is not None and close > 0 else latest
    return QuoteSnapshot(
        code=code,
        name=name,
        latest=latest,
        open=open_price,
        high=high,
        low=low,
        close=close_value,
        changePct=change_pct,
        amount=amount,
        snapshotAt=snapshot_at,
        source=source,
    )
