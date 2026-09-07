"""阶段排行榜预计算脚本。

读取 apps/web/public/data/archive/ 下的每日行情快照，输出单个静态文件
apps/web/public/data/leaderboard.json，供前端「阶段排行榜」卡片即时筛选排序。

关键处理：
1. 复权修正：相邻快照日收益率超过涨跌幅限制（份额折算/除权除息）时，
   按比例向前修正历史价格，避免榜单出现 -70% 之类的假跌幅。
2. 区间收益：近1周(5 交易日)/近1月(20)/近3月(60)/今年来。
3. 流动性过滤：末日成交额 个股 >= 1000万、ETF >= 2000万。
4. 板块聚合：以行业/主题 ETF 为代理，板块涨幅取成员中位，代表 ETF 取日均成交额最大。

用法：
    python services/market-data/build_leaderboard.py
    python services/market-data/build_leaderboard.py --data-dir <path>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "apps" / "web" / "public" / "data"

WINDOWS = (("1w", 5), ("1m", 20), ("3m", 60))
TOLERANCE = 0.02  # 涨跌幅判定容差
MIN_AMOUNT = {"stock": 1e7, "etf": 2e7}
SECTOR_MIN_AVG_AMOUNT = 5e7

# 债券/货币类 ETF 不参与任何榜单
BOND_KEYWORDS = ("债", "货币", "现金", "添益", "理财", "短融", "国债")

# 板块主题关键词（按 ETF 名称匹配）
SECTOR_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("医药医疗", ("医药", "医疗", "生物", "创新药", "中药", "康养")),
    ("券商金融", ("券商", "证券", "银行", "保险", "金融")),
    ("海外指数", ("纳斯达克", "纳指", "标普", "日经", "德国", "法国", "道琼", "美国")),
    ("有色黄金资源", ("有色", "黄金", "稀土", "钢铁", "煤炭", "化工", "铜", "石油", "能源", "矿业", "材料")),
    ("红利高股息", ("红利", "股息")),
    ("食品饮料", ("酒", "食品", "消费", "白酒")),
    ("地产", ("房地产", "地产")),
    ("军工", ("军工", "国防")),
    ("通信传媒游戏", ("通信", "5G", "传媒", "游戏", "影视", "动漫")),
    ("人工智能软件", ("人工智能", "计算机", "软件", "云计算", "大数据", "机器人", "信创", "信息", "智能")),
    ("半导体芯片", ("芯片", "半导体", "集成电路", "碳化硅", "消费电子", "消电")),
    ("新能源车电池", ("新能车", "电动车", "汽车", "电池", "锂电", "智能车")),
    ("光伏新能源", ("光伏", "碳中和", "绿色", "新能源", "风电", "电网")),
    ("高端制造", ("工业母机", "机床", "制造", "装备", "卫星")),
    ("港股中概", ("恒生", "港股", "中概", "互联网")),
    ("宽基科创创业", ("科创", "创业")),
    ("宽基大盘", ("沪深300", "上证50", "A500", "上证指数", "上证180")),
    ("宽基中小盘", ("中证500", "中证1000", "中证2000", "国证", "中小")),
]


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.move(str(temp_path), str(path))


def load_snapshots(archive_dir: Path) -> tuple[list[str], dict[str, list[dict]], dict[str, list[dict]]]:
    """返回 (交易日列表, {date: stock_items}, {date: etf_items})，按快照实际日期去重。"""
    by_date: dict[str, tuple[list[dict], list[dict]]] = {}
    for folder in sorted(archive_dir.iterdir()):
        if not folder.is_dir():
            continue
        sp, ep = folder / "stock-latest.json", folder / "etf-latest.json"
        if not (sp.exists() and ep.exists()):
            continue
        try:
            stocks = json.loads(sp.read_text(encoding="utf-8"))
            etfs = json.loads(ep.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not stocks:
            continue
        snap_date = str(stocks[0].get("snapshotAt", ""))[:10]
        if not snap_date:
            continue
        by_date[snap_date] = (stocks, etfs)  # 同日重复时保留后者
    dates = sorted(by_date)
    stocks_by_date = {d: by_date[d][0] for d in dates}
    etfs_by_date = {d: by_date[d][1] for d in dates}
    return dates, stocks_by_date, etfs_by_date


def price_limit(code: str, name: str, kind: str) -> float:
    if kind == "stock":
        if code.startswith("bj"):
            return 0.30
        if code.startswith("sh688") or code.startswith("sz300") or code.startswith("sz301"):
            return 0.20
        return 0.10
    # ETF
    return 0.20 if ("科创" in name or "创业" in name) else 0.10


def build_panel(dates: list[str], items_by_date: dict[str, list[dict]], kind: str) -> dict[str, dict]:
    """组装 {code: {name, px: {date: 复权价}, amt: {date: 成交额}}}。"""
    panel: dict[str, dict] = {}
    for date, items in items_by_date.items():
        for it in items:
            px = it.get("latest")
            if not px or px <= 0:
                continue
            code = str(it.get("code") or "")
            if not code:
                continue
            p = panel.setdefault(code, {"name": str(it.get("name") or "").strip(), "px": {}, "amt": {}})
            p["px"][date] = float(px)
            amt = it.get("amount")
            p["amt"][date] = float(amt) if amt else 0.0
            p["name"] = str(it.get("name") or p["name"]).strip()

    didx = {d: i for i, d in enumerate(dates)}
    for code, p in panel.items():
        days = sorted(p["px"])
        lim = price_limit(code, p["name"], kind)
        factor = 1.0
        adjusted: dict[str, float] = {days[0]: p["px"][days[0]]}
        for i in range(1, len(days)):
            gap = didx[days[i]] - didx[days[i - 1]]
            raw_ret = p["px"][days[i]] / p["px"][days[i - 1]] - 1
            if abs(raw_ret) > (1 + lim + TOLERANCE) ** gap - 1:
                # 份额折算/除权：向前复权
                factor *= p["px"][days[i - 1]] / p["px"][days[i]]
            adjusted[days[i]] = p["px"][days[i]] * factor
        p["px"] = adjusted
    return panel


def window_returns(px: dict[str, float], dates: list[str], latest_year: str) -> dict[str, float | None]:
    """计算各窗口区间收益率；起点缺价返回 None。"""
    end = dates[-1]
    end_px = px.get(end)
    out: dict[str, float | None] = {}
    for key, span in WINDOWS:
        start_idx = max(0, len(dates) - 1 - span)
        start = dates[start_idx]
        start_px = px.get(start)
        out[f"ret{key[0].upper()}{key[1:]}"] = (end_px / start_px - 1) if (end_px and start_px) else None
    # 今年来：当年第一个有价格的交易日
    ytd_dates = [d for d in dates if d >= f"{latest_year}-01-01" and d in px]
    if ytd_dates and end_px:
        out["retYtd"] = end_px / px[ytd_dates[0]] - 1
    else:
        out["retYtd"] = None
    return out


def window_start_dates(dates: list[str], latest_year: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for key, span in WINDOWS:
        out[key] = dates[max(0, len(dates) - 1 - span)]
    ytd = [d for d in dates if d >= f"{latest_year}-01-01"]
    out["ytd"] = ytd[0] if ytd else None
    return out


def is_bond_etf(name: str) -> bool:
    return any(k in name for k in BOND_KEYWORDS)


def build_rankings(
    dates: list[str],
    panel: dict[str, dict],
    kind: str,
    latest_year: str,
) -> list[dict]:
    end = dates[-1]
    rows = []
    for code, p in panel.items():
        rets = window_returns(p["px"], dates, latest_year)
        if kind == "etf" and is_bond_etf(p["name"]):
            continue
        if p["amt"].get(end, 0.0) < MIN_AMOUNT[kind]:
            continue
        if all(v is None for v in rets.values()):
            continue
        rows.append({
            "code": code,
            "name": p["name"],
            **rets,
            "amount": round(p["amt"].get(end, 0.0)),
        })
    return rows


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def build_sectors(dates: list[str], etf_panel: dict[str, dict], latest_year: str) -> list[dict]:
    end = dates[-1]
    members: dict[str, list[dict]] = {}
    for code, p in etf_panel.items():
        if is_bond_etf(p["name"]):
            continue
        avg_amt = statistics.mean(p["amt"].values()) if p["amt"] else 0.0
        if avg_amt < SECTOR_MIN_AVG_AMOUNT:
            continue
        rets = window_returns(p["px"], dates, latest_year)
        for sector, keywords in SECTOR_KEYWORDS:
            if any(k in p["name"] for k in keywords):
                members.setdefault(sector, []).append({
                    "code": code, "name": p["name"], "avgAmount": avg_amt, **rets,
                })
                break  # 一只 ETF 只归入第一个命中的板块

    sectors = []
    for sector, items in members.items():
        if len(items) < 2:
            continue
        rep = max(items, key=lambda x: x["avgAmount"])
        row = {"name": sector, "count": len(items),
               "repCode": rep["code"], "repName": rep["name"]}
        for key in ("ret1w", "ret1m", "ret3m", "retYtd"):
            vals = [it[key] for it in items if it.get(key) is not None]
            row[key] = round(median_or_none(vals), 4) if vals else None
            row[f"rep{key[0].upper()}{key[1:]}"] = rep.get(key)
        sectors.append(row)
    sectors.sort(key=lambda r: (r.get("ret3m") is None, -(r.get("ret3m") or 0)))
    return sectors


def round_rows(rows: list[dict]) -> list[dict]:
    for r in rows:
        for key in ("ret1w", "ret1m", "ret3m", "retYtd"):
            if r.get(key) is not None:
                r[key] = round(r[key], 4)
    return rows


def run(data_dir: Path) -> int:
    archive_dir = data_dir / "archive"
    if not archive_dir.exists():
        raise SystemExit(f"archive dir not found: {archive_dir}")

    dates, stocks_by_date, etfs_by_date = load_snapshots(archive_dir)
    if len(dates) < 2:
        raise SystemExit(f"not enough trading days: {len(dates)}")
    latest_year = dates[-1][:4]

    stock_panel = build_panel(dates, stocks_by_date, "stock")
    etf_panel = build_panel(dates, etfs_by_date, "etf")

    stocks = round_rows(build_rankings(dates, stock_panel, "stock", latest_year))
    etfs = round_rows(build_rankings(dates, etf_panel, "etf", latest_year))
    sectors = build_sectors(dates, etf_panel, latest_year)

    payload = {
        "generatedAt": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "latestDate": dates[-1],
        "windowStart": window_start_dates(dates, latest_year),
        "stocks": stocks,
        "etfs": etfs,
        "sectors": sectors,
    }
    out_path = data_dir / "leaderboard.json"
    write_json_atomic(out_path, payload)
    print(f"leaderboard written: {out_path}")
    print(f"  trading days: {len(dates)} ({dates[0]} -> {dates[-1]})")
    print(f"  stocks: {len(stocks)}, etfs: {len(etfs)}, sectors: {len(sectors)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build stage leaderboard JSON for jiucaiquan web.")
    parser.add_argument("--data-dir", default=os.environ.get("JCQ_DATA_DIR") or str(DEFAULT_DATA_DIR))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(Path(parse_args().data_dir).resolve()))
