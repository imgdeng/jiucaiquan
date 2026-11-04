"""us-110 回测 MVP 预计算脚本。

- 复用 build_leaderboard.py 的 archive 读取与前复权实现，不新建数据源；
- 按 P-1 结论剔除 8 个非交易日假快照，代入 P-1 证据池（59 只，成交额降序）；
- 按 01_req.md §4 冻结口径计算各档位胜率 / 累计收益率 / 最大回撤；
- 档位：2w（10 个交易日）/ 4w（20 个交易日）/ 3m（60 日）/ 6m / 12m；
  未达门槛的档位标记 available=false，前端只渲染真正可用的档位；
- 输出契约：index.json（≤150KB）+ summary/{code}.json（≤20KB）+ detail/{code}.json（按需加载）；
- 逐笔明细与权益曲线与摘要同源生成，构建期强校验：逐笔合计 = 累计收益率、曲线终值 = 100 + 累计收益率；
- 幂等：连续两次运行除 generatedAt 外字节一致；原子写入。

硬门禁：
team/us/us-110/p1_data_conclusion.md 与 p1_evidence.json 缺失时，脚本以退出码 3 停止，
不创建目录、不写文件、不输出任何回测指标。

样本末段前瞻窗口不足 5 个交易日的信号无法完整结算，构建时直接跳过（不虚构平仓价），
该处理已在 02_eng.md 中留档供项目马复核。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# 复用 build_leaderboard.py 的读取与前复权实现（同目录直接导入）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_leaderboard import (  # noqa: E402
    build_panel,
    load_snapshots,
    write_json_atomic,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
GATE_FILE = ROOT / "team" / "us" / "us-110" / "p1_data_conclusion.md"
P1_EVIDENCE = ROOT / "team" / "us" / "us-110" / "p1_evidence.json"
BASE_FILE = ROOT / "services" / "market-data" / "backtest-base" / "history_base.json"
BASE_META_FILE = ROOT / "services" / "market-data" / "backtest-base" / "meta.json"
BASE_MAX_BYTES = 350_000
OUT_DIR_NAME = "backtest"

SCHEMA_VERSION = 1
POOL_MIN_TOTAL = 50
POOL_MIN_PER_ASSET = 25
FORCED_CODES = (("510300", "etf"), ("600519", "stock"))

# 档位名义窗口、最低交易日门槛（01_req.md §3.1 / us-113 FR-5）
# (key, label, 名义交易日数, 最低门槛)
# 顺序即前端展示顺序：3m 在最前；2w/4w 为短周期观察档，不得默认选中。
WINDOWS: tuple[tuple[str, str, int, int], ...] = (
    ("3m", "近 3 个月", 60, 20),
    ("2w", "近 2 周", 10, 10),
    ("4w", "近 4 周", 20, 20),
    ("6m", "近 6 个月", 120, 120),
    ("9m", "近 9 个月", 180, 180),
    ("12m", "近 12 个月", 240, 240),
)
SHORT_WINDOW_KEYS = ("2w", "4w")
UNAVAILABLE_REASON = "数据积累中"
# 样本不足门槛（01_req.md §4.2 / us-113 FR-5）：平仓笔数 < 3 时标注“样本不足（N 笔）”
SAMPLE_MIN_TRADES = 3
# 货币/债券类 ETF 不得入池；关键词表不在此硬编码，统一从 P-1 证据 moneyBondEtf.keywords 读取

# 策略参数冻结于 01_req.md §4：rangeMultiplier=1 / weighted base / 最长持有 5 个交易日
STRATEGY_META = {
    "id": "pivot-condition-order",
    "label": "Pivot 条件单（次日低吸/高抛）",
    "holdDays": 5,
    "rangeMultiplier": 1,
    "basePriceMode": "weighted",
    "priceAdjustment": "前复权",
    "costNote": "未计佣金与滑点",
}
NOTIONAL_PER_TRADE = 10_000.0

INDEX_MAX_BYTES = 150_000
SUMMARY_MAX_BYTES = 20_000
DETAIL_WINDOW_MAX_BYTES = 6_000
DETAIL_TOTAL_MAX_BYTES = 800_000
# 内测收益排序（noindex 路由）：只纳入平仓笔数 ≥ 5 的标的，最多 10 行
RANKING_MIN_TRADES = 5
RANKING_LIMIT = 10

# 机器可读契约：字段定义与体积预算，供 --print-contract 输出 / 前端对齐
INDEX_CONTRACT = {
    "path": "apps/web/public/data/backtest/index.json",
    "maxBytes": INDEX_MAX_BYTES,
    "required": [
        "schemaVersion",
        "generatedAt",
        "latestDate",
        "dataStart",
        "tradingDays",
        "strategy",
        "windows",
        "poolStats",
        "pool",
    ],
    "windowItem": {
        "required": ["key", "label", "minTradingDays", "available", "start", "end", "tradingDays", "reason"],
        "note": "2w=10 日 / 4w=20 日 / 3m=60 日 / 6m=120 日 / 12m=240 日；未达门槛时 available=false，前端不渲染该档",
    },
    "poolItem": {
        "required": ["code", "name", "asset", "amount", "summary"],
        "note": "code 为不带市场前缀的 6 位码；pool 默认按末日成交额降序；amount 仅用于排序，不展示为热度；detail 路径由前端按 code 推导",
    },
    "distribution": {
        "note": "按档位聚合，仅含 available=true 的档位；不点名标的、不排序",
        "required": ["sample", "positiveCount", "positiveShare", "medianCumReturn", "medianWinRate", "medianMaxDrawdown", "buckets"],
    },
    "idempotent": "连续两次构建除 generatedAt 外字节一致",
}

SUMMARY_CONTRACT = {
    "path": "apps/web/public/data/backtest/summary/{code}.json",
    "maxBytes": SUMMARY_MAX_BYTES,
    "required": [
        "schemaVersion",
        "generatedAt",
        "code",
        "name",
        "asset",
        "latestDate",
        "strategy",
        "windows",
    ],
    "windowResult": {
        "available": "boolean",
        "start/end": "YYYY-MM-DD；available=false 时为 null",
        "tradingDays": "实际样本交易日数（int）",
        "trades": "平仓总笔数（int）",
        "wins": "盈利平仓笔数（int）",
        "winRate": "百分比数值，保留 1 位小数；trades=0 时为 null",
        "cumReturn": "百分比数值，保留 2 位小数，如 -3.25",
        "maxDrawdown": "百分比数值，保留 2 位小数，如 4.12",
        "sampleWarning": "null | 'insufficient'（0<笔数<3）| 'noTrades'（笔数=0）",
    },
    "notGenerated": "",
}

DETAIL_CONTRACT = {
    "path": "apps/web/public/data/backtest/detail/{code}.json",
    "maxBytesPerWindow": DETAIL_WINDOW_MAX_BYTES,
    "maxBytesTotal": DETAIL_TOTAL_MAX_BYTES,
    "required": ["schemaVersion", "generatedAt", "code", "name", "asset", "notional", "strategy", "latestDate", "windows"],
    "windowItem": {
        "required": ["start", "end", "tradingDays", "trades", "pnlTotal", "cumReturn", "maxDrawdown", "equity", "peak", "maxDrawdownRange"],
        "tradeItem": {
            "order": ["buyDate", "buyPrice", "sellDate", "sellPrice", "holdDays", "returnPct", "pnl", "exitReason"],
            "note": "数组形式；exitReason 为 '高抛' 或 '到期平仓'；holdDays 为交易日数",
        },
        "equity": "[权益指数, ...]；起点 100，按交易日顺序仅给数值；峰值/回撤日期见 peak / maxDrawdownRange",
        "consistency": "sum(trade.pnl) = pnlTotal；100 + cumReturn = equity 终点 = 100 + pnlTotal/100",
    },
    "note": "按需加载：首屏与切档不请求 detail；同一标的只取 1 次并缓存",
}


def normalize_code(raw: object) -> str | None:
    """去除 sh/sz/bj 前缀，统一为 6 位数字码。"""
    if not isinstance(raw, str):
        return None
    v = raw.strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
            break
    return v if len(v) == 6 and v.isdigit() else None


def require_gate() -> dict:
    """硬门禁：没有书面数据前置结论 + 机器可读证据时，不读取行情、不写任何产物。"""
    if not GATE_FILE.exists() or GATE_FILE.stat().st_size == 0:
        print("[backtest] 门禁未开：未找到 team/us/us-110/p1_data_conclusion.md", file=sys.stderr)
        print("[backtest] 已停止，未生成任何回测产物或数字。", file=sys.stderr)
        raise SystemExit(3)
    if not P1_EVIDENCE.exists():
        print("[backtest] 门禁缺少机器可读证据 p1_evidence.json", file=sys.stderr)
        raise SystemExit(3)
    return json.loads(P1_EVIDENCE.read_text(encoding="utf-8"))


def load_leaderboard(data_dir: Path) -> dict:
    path = data_dir / "leaderboard.json"
    if not path.exists():
        raise SystemExit(f"leaderboard.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_base(path: Path) -> dict:
    """读取历史底座（数据线生成入库）。缺失时显式失败，禁止静默降级到只有 archive 的短样本。"""
    if not path.exists():
        raise FileNotFoundError(
            f"历史底座缺失：{path}；6m/9m/12m 必须与底座拼接，请先由数据线生成并提交，"
            "拒绝静默降级。"
        )
    size = path.stat().st_size
    if size > BASE_MAX_BYTES:
        raise SystemExit(f"历史底座体积超预算：{size}B > {BASE_MAX_BYTES}B")
    payload = json.loads(path.read_text(encoding="utf-8"))
    dates = payload.get("dates")
    symbols = payload.get("symbols")
    if not isinstance(dates, list) or not dates or not isinstance(symbols, dict) or not symbols:
        raise SystemExit(f"历史底座结构不合法：{path}")
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise SystemExit("历史底座日期必须去重且升序")
    return payload


def load_base_meta(path: Path = BASE_META_FILE) -> dict:
    """底座消费契约（漂移口径等）；缺失不阻断构建，但产物中不写入不可核实数字。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def merge_base(
    base: dict,
    archive_dates: list[str],
    stocks_by_date: dict[str, list[dict]],
    etfs_by_date: dict[str, list[dict]],
) -> tuple[list[str], dict[str, list[dict]], dict[str, list[dict]]]:
    """底座（raw OHLC，日期共享索引）与 archive 快照拼接为统一日期序列。"""
    base_dates: list[str] = list(base["dates"])
    overlap = sorted(set(base_dates) & set(archive_dates))
    if overlap:
        raise SystemExit(f"历史底座与 archive 日期重叠，拒绝重复拼接：{overlap[:3]} 等 {len(overlap)} 天")
    stock_out: dict[str, list[dict]] = {day: list(items) for day, items in stocks_by_date.items()}
    etf_out: dict[str, list[dict]] = {day: list(items) for day, items in etfs_by_date.items()}
    for code, entry in base["symbols"].items():
        rows = entry.get("rows") or []
        start = int(entry.get("start") or 0)
        if not rows or start + len(rows) > len(base_dates):
            raise SystemExit(f"历史底座标的行越界：{code}")
        target = etf_out if entry.get("asset") == "etf" else stock_out
        name = str(entry.get("name") or "").strip()
        for offset, row in enumerate(rows):
            if row is None or len(row) < 5 or any(row[pos] is None for pos in range(4)):
                continue  # 停牌日：底座按日对齐留 null，不构造假 K 线
            day = base_dates[start + offset]
            target.setdefault(day, []).append(
                {
                    "code": code,
                    "name": name,
                    "latest": float(row[3]),
                    "open": float(row[0]),
                    "high": float(row[1]),
                    "low": float(row[2]),
                    "amount": float(row[4]) if row[4] else 0.0,
                }
            )
    combined = sorted(set(base_dates) | set(archive_dates))
    if combined[0] != base_dates[0] or combined[-1] != archive_dates[-1]:
        raise SystemExit(f"拼接后的日期边界异常：{combined[0]} ~ {combined[-1]}")
    return combined, stock_out, etf_out


def build_coverage(dates: list[str], windows: list[dict], bars: dict[str, dict[str, dict]], pool: list[dict]) -> dict[str, dict]:
    """统计每个档位下“可用交易日数 ≥ 门槛”的标的数量与缺口清单。"""
    coverage: dict[str, dict] = {}
    for window in windows:
        if window["start"] is None:
            coverage[window["key"]] = {"ok": 0, "shortfall": []}
            continue
        start_idx = dates.index(window["start"])
        end_idx = dates.index(window["end"])
        window_dates = dates[start_idx : end_idx + 1]
        shortfall = []
        ok = 0
        for item in pool:
            days = sum(1 for day in window_dates if day in bars[item["code"]])
            if days >= window["minTradingDays"]:
                ok += 1
            else:
                shortfall.append({"code": item["code"], "name": item["name"], "days": days})
        shortfall.sort(key=lambda row: (-row["days"], row["code"]))
        coverage[window["key"]] = {"ok": ok, "shortfall": shortfall}
    return coverage


def assert_splice_continuity(
    bars: dict[str, dict[str, dict]],
    combined_dates: list[str],
    archive_dates: list[str],
    raw_closes: dict[str, dict[str, float]],
    codes: tuple[str, ...] = ("510300", "600519", "300750"),
) -> None:
    """抽 3 只核对底座/archive 拼接日收益，防止拼接产生假跳变。"""
    splice = archive_dates[0]
    prev = combined_dates[combined_dates.index(splice) - 1]
    for code in codes:
        if code not in bars or prev not in bars[code] or splice not in bars[code]:
            continue
        adj_ret = bars[code][splice]["close"] / bars[code][prev]["close"] - 1
        raw = raw_closes.get(code, {})
        raw_ret = raw[splice] / raw[prev] - 1 if splice in raw and prev in raw else None
        shown = f"{raw_ret * 100:+.2f}%" if raw_ret is not None else "n/a"
        print(f"  splice {code} {prev} -> {splice}: 复权 {adj_ret * 100:+.2f}% / 原始 {shown}")
        if raw_ret is not None and abs(adj_ret - raw_ret) > 0.02:
            raise SystemExit(f"拼接日收益异常（复权与原始偏差 >2pp）：{code} {prev}->{splice}")


def panel_by_norm_code(panel: dict[str, dict]) -> dict[str, tuple[str, dict]]:
    """{归一化 6 位码: (archive 原始码, 面板数据)}，同码保留首个。"""
    out: dict[str, tuple[str, dict]] = {}
    for raw_code, item in panel.items():
        code = normalize_code(raw_code)
        if code and code not in out:
            out[code] = (raw_code, item)
    return out


def load_money_bond_keywords(evidence: dict) -> tuple[str, ...]:
    """复用 P-1 证据里的货币/债券 ETF 关键词表，避免与数据前置维护的第二份词表漂移。"""
    raw = evidence.get("moneyBondEtf", {}).get("keywords")
    if not isinstance(raw, list):
        raise SystemExit("P-1 证据缺少货币/债券 ETF 关键词表（moneyBondEtf.keywords），拒绝构建")
    keywords = tuple(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))
    if not keywords:
        raise SystemExit("货币/债券 ETF 关键词表为空，拒绝构建")
    return keywords


def build_pool(evidence: dict, leaderboard: dict, keywords: tuple[str, ...]) -> list[dict]:
    """固定标的池：代入 P-1 证据池，显式排除货币/债券类 ETF，并按末日成交额降序。

    P-1 已完成成交额头部筛选、异常标的剔除与“不足 60 日”剔除；这里只做代入与校验，
    不重新推导，避免与书面结论产生第二套口径。
    """
    pool_symbols = evidence.get("pool", {}).get("symbols", [])
    excluded = {normalize_code(item.get("code")) for item in evidence.get("excluded", [])}

    rows_by_code: dict[str, dict] = {}
    for row in leaderboard.get("stocks", []) + leaderboard.get("etfs", []):
        code = normalize_code(row.get("code"))
        if code:
            rows_by_code[code] = row

    pool: list[dict] = []
    for symbol in pool_symbols:
        code = normalize_code(symbol.get("code"))
        if not code:
            continue
        if code in excluded:
            raise SystemExit(f"P-1 已剔除标的仍在池内：{code}")
        if int(symbol.get("days") or 0) < 60:
            raise SystemExit(f"P-1 标的不足 60 个交易日，不得入池：{code} ({symbol.get('days')} 日)")
        row = rows_by_code.get(code)
        name = str(symbol.get("name") or (row or {}).get("name") or code).strip()
        asset = str(symbol.get("kind") or "").strip()
        if asset == "etf" and any(keyword in name for keyword in keywords):
            print(f"[backtest] 排除货币/债券类 ETF：{code} {name}", file=sys.stderr)
            continue
        pool.append(
            {
                "code": code,
                "name": name,
                "asset": asset,
                "amount": int(round(float((row or {}).get("amount") or 0))),
                "summary": f"summary/{code}.json",
            }
        )

    # D3：默认排序 = 末日成交额降序，仅代表成交活跃度
    pool.sort(key=lambda x: (-x["amount"], x["code"]))
    pool_stats = {
        "total": len(pool),
        "etf": sum(1 for item in pool if item["asset"] == "etf"),
        "stock": sum(1 for item in pool if item["asset"] == "stock"),
    }
    if pool_stats["total"] < POOL_MIN_TOTAL or pool_stats["etf"] < POOL_MIN_PER_ASSET or pool_stats["stock"] < POOL_MIN_PER_ASSET:
        raise SystemExit(
            "标的池不满足门槛："
            f"total={pool_stats['total']} (需≥{POOL_MIN_TOTAL}), "
            f"etf={pool_stats['etf']} / stock={pool_stats['stock']} (各需≥{POOL_MIN_PER_ASSET})"
        )
    for forced_code, forced_asset in FORCED_CODES:
        item = next((x for x in pool if x["code"] == forced_code), None)
        if not item or item["asset"] != forced_asset:
            raise SystemExit(f"P-1 标的池缺少必备标的：{forced_code} ({forced_asset})")

    return pool


def assert_no_money_bond_leak(index_path: Path, keywords: tuple[str, ...]) -> None:
    """产物回读断言：重新读取落盘的 index.json，确认池内没有货币/债券类 ETF 残留。

    与过滤逻辑分开取值：前者写内存池，后者从磁盘回读，避免“同谓词同列表、断言恒空”。
    """
    index = json.loads(index_path.read_text(encoding="utf-8"))
    leaked = [
        item
        for item in index.get("pool", [])
        if item.get("asset") == "etf" and any(keyword in str(item.get("name") or "") for keyword in keywords)
    ]
    if leaked:
        detail = ", ".join(f"{item['code']} {item['name']}" for item in leaked)
        raise SystemExit(f"产物回读发现货币/债券类 ETF 仍在池内：{detail}")


def build_windows(
    dates: list[str],
    coverage: dict[str, dict] | None = None,
    sample: int | None = None,
) -> list[dict]:
    """按 01_req.md §3.1/§3.2 计算档位可用性与实际生效区间。

    coverage 为按标的统计的可用天数；档位按钮仅在池内“可用标的数 ≥ 半数”时出现。
    """
    total = len(dates)
    end = dates[-1]
    windows: list[dict] = []
    for key, label, nominal_days, min_days in WINDOWS:
        span = min(nominal_days, total)
        start_idx = total - span
        item = {
            "key": key,
            "label": label,
            "minTradingDays": min_days,
            "start": dates[start_idx],
            "end": end,
            "tradingDays": total - start_idx,
        }
        if coverage is not None and key in coverage:
            detail = coverage[key]
            item.update(
                {
                    "available": detail["ok"] >= -(-(sample or total) // 2),
                    "availableSymbols": detail["ok"],
                    "sample": sample or total,
                    "coverageNote": (
                        None
                        if detail["shortfall"] == []
                        else f"{detail['ok']}/{sample or total} 只满足 {min_days} 个交易日；"
                        + "、".join(f"{row['name']} {row['days']} 日" for row in detail["shortfall"])
                        + f"，数据不足，故{label}档对上述 {len(detail['shortfall'])} 只标的不适用"
                    ),
                    "reason": None if detail["ok"] >= -(-(sample or total) // 2) else "可用标的不足",
                }
            )
        else:
            available = total >= min_days
            item.update(
                {
                    "available": available,
                    "availableSymbols": None,
                    "sample": sample,
                    "coverageNote": None,
                    "reason": None if available else ("数据不足" if key in ("3m",) + SHORT_WINDOW_KEYS else UNAVAILABLE_REASON),
                }
            )
        windows.append(item)
    return windows


def build_index(
    dates: list[str],
    pool: list[dict],
    generated_at: str,
    distribution: dict | None = None,
    windows: list[dict] | None = None,
    methodology: dict | None = None,
) -> dict:
    index = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "latestDate": dates[-1],
        "dataStart": dates[0],
        "tradingDays": len(dates),
        "strategy": STRATEGY_META,
        "methodology": methodology or {},
        "windows": windows if windows is not None else build_windows(dates),
        "poolStats": {
            "total": len(pool),
            "etf": sum(1 for item in pool if item["asset"] == "etf"),
            "stock": sum(1 for item in pool if item["asset"] == "stock"),
        },
        "pool": pool,
    }
    if distribution:
        index["distribution"] = distribution
    return index


def price_digits(asset: str) -> int:
    return 4 if asset == "etf" else 2


def round_price(value: float, digits: int) -> float:
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def build_bars(
    pool: list[dict],
    dates: list[str],
    stocks_by_date: dict[str, dict],
    etfs_by_date: dict[str, dict],
    stock_panel: dict[str, dict],
    etf_panel: dict[str, dict],
) -> dict[str, dict[str, dict]]:
    """为池内标的组装前复权 OHLC。

    archive 的 `latest` 是当日收盘价（`close` 字段为昨收，不能用于当日 K 线）；
    先用 build_panel 得到的复权收盘价求出复权因子，再同比例修正 high/low/open。
    """
    raw_maps: dict[str, dict[str, str]] = {
        "stock": {code: raw for code, (raw, _) in panel_by_norm_code(stock_panel).items()},
        "etf": {code: raw for code, (raw, _) in panel_by_norm_code(etf_panel).items()},
    }
    panels = {"stock": stock_panel, "etf": etf_panel}
    by_dates = {"stock": stocks_by_date, "etf": etfs_by_date}

    bars: dict[str, dict[str, dict]] = {item["code"]: {} for item in pool}
    for item in pool:
        code = item["code"]
        asset = item["asset"]
        raw = raw_maps[asset].get(code)
        if not raw:
            raise SystemExit(f"标的不在 {asset} 行情面板：{code}")
        panel = panels[asset].get(raw)
        if not panel:
            raise SystemExit(f"标的不在 {asset} 行情面板：{code}")
        for date, items in by_dates[asset].items():
            snapshot = next((it for it in items if str(it.get("code")) == raw), None)
            if not snapshot:
                continue
            adj_close = panel.get("px", {}).get(date)
            raw_close = snapshot.get("latest")
            if adj_close is None or not raw_close:
                continue
            factor = float(adj_close) / float(raw_close)
            high = snapshot.get("high")
            low = snapshot.get("low")
            open_price = snapshot.get("open")
            bars[code][date] = {
                "open": float(open_price) * factor if open_price else float(adj_close),
                "high": float(high) * factor if high else float(adj_close),
                "low": float(low) * factor if low else float(adj_close),
                "close": float(adj_close),
            }
    return bars


def simulate_window(series: dict[str, dict], dates: list[str], window: dict, asset: str) -> tuple[dict, dict | None]:
    """按 01_req.md §4 的冻结规则执行串行单仓模拟。

    返回 (摘要结果, 逐笔明细)。两者同源计算：逐笔 pnl 之和 = 摘要累计收益率，
    权益曲线终点 = 100 + 累计收益率，构建期用 assert_detail_consistent 强校验。

    样本末段前瞻窗口不足 holdDays 的信号无法完整结算，直接跳过，不虚构平仓价。
    """
    if not window["available"]:
        return (
            {
                "available": False,
                "start": None,
                "end": None,
                "tradingDays": None,
                "trades": None,
                "wins": None,
                "winRate": None,
                "cumReturn": None,
                "maxDrawdown": None,
                "sampleWarning": None,
                "reason": window.get("reason"),
            },
            None,
        )

    start_idx = dates.index(window["start"])
    end_idx = dates.index(window["end"])
    window_dates = dates[start_idx : end_idx + 1]
    available_days = sum(1 for day in window_dates if day in series)
    if available_days < window["minTradingDays"]:
        # 标的级门槛：数据不足时不出任何数字，由页面显示“可用 N 个交易日”
        return (
            {
                "available": False,
                "start": window["start"],
                "end": window["end"],
                "tradingDays": available_days,
                "availableTradingDays": available_days,
                "minTradingDays": window["minTradingDays"],
                "trades": None,
                "wins": None,
                "winRate": None,
                "cumReturn": None,
                "maxDrawdown": None,
                "sampleWarning": None,
                "reason": f"该标的此区间数据不足（可用 {available_days} 个交易日）",
            },
            None,
        )
    hold = STRATEGY_META["holdDays"]
    digits = price_digits(asset)

    raw_trades: list[dict] = []
    i = start_idx
    while i <= end_idx - hold:
        needed = dates[i : i + hold + 1]
        if any(day not in series for day in needed):
            i += 1
            continue
        signal = series[dates[i]]
        base = (2 * signal["close"] + signal["high"] + signal["low"]) / 4
        price_range = signal["high"] - signal["low"]
        buy = round_price(base - price_range, digits)
        sell = round_price(base + price_range, digits)
        entry_day = dates[i + 1]
        entry_bar = series[entry_day]
        if price_range <= 0 or buy <= 0 or sell <= buy or entry_bar["low"] > buy:
            i += 1
            continue

        exit_idx = i + hold  # 默认持有满 5 个交易日按第 5 日收盘价结算
        exit_price = series[dates[exit_idx]]["close"]
        exit_reason = "到期平仓"
        for j in range(i + 1, i + hold + 1):
            if series[dates[j]]["high"] >= sell:
                exit_idx = j
                exit_price = sell
                exit_reason = "高抛"
                break

        raw_trades.append(
            {
                "entry_idx": i + 1,
                "exit_idx": exit_idx,
                "buy": buy,
                "sell": exit_price,
                "pnl": round(NOTIONAL_PER_TRADE * (exit_price / buy - 1), 2),
                "raw_pnl": NOTIONAL_PER_TRADE * (exit_price / buy - 1),
                "exit_reason": exit_reason,
            }
        )
        i = max(i + 1, exit_idx)

    wins = sum(1 for trade in raw_trades if trade["raw_pnl"] > 0)
    trades_count = len(raw_trades)
    win_rate = round(wins / trades_count * 100, 1) if trades_count else None
    pnl_total = round(sum(trade["pnl"] for trade in raw_trades), 2)
    cum_return = round(pnl_total / (NOTIONAL_PER_TRADE / 100), 2)

    # 逐日权益指数 = 100 + 已实现盈亏 + 持仓浮动盈亏；峰值从 100 起算
    trades_by_exit: dict[int, list[dict]] = {}
    for trade in raw_trades:
        trades_by_exit.setdefault(trade["exit_idx"], []).append(trade)
    realized = 0.0
    peak = 100.0
    peak_idx = start_idx
    max_drawdown = 0.0
    max_dd_peak_idx = start_idx
    max_dd_trough_idx = start_idx
    last_close: float | None = None
    equity: list[float] = []
    for idx in range(start_idx, end_idx + 1):
        for trade in trades_by_exit.get(idx, []):
            realized += trade["pnl"]
        candidate = next((t for t in raw_trades if t["entry_idx"] <= idx < t["exit_idx"]), None)
        day = dates[idx]
        if day in series:
            last_close = series[day]["close"]
        floating = 0.0
        if candidate is not None and last_close is not None:
            floating = NOTIONAL_PER_TRADE * (last_close / candidate["buy"] - 1)
        equity_index = 100.0 + (realized + floating) / (NOTIONAL_PER_TRADE / 100)
        equity.append(round(equity_index, 1))  # 曲线展示精度 0.1；终点单独保 2 位
        if equity_index > peak:
            peak = equity_index
            peak_idx = idx
        drawdown = 1 - equity_index / peak if peak > 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_dd_peak_idx = peak_idx
            max_dd_trough_idx = idx

    # 终点由 pnlTotal 推导，保证 100 + cumReturn 与曲线末点完全一致（差异来自独立取整，非口径）
    if equity:
        equity[-1] = round(100 + cum_return, 2)

    result = {
        "available": True,
        "start": window["start"],
        "end": window["end"],
        "tradingDays": window["tradingDays"],
        "trades": trades_count,
        "wins": wins,
        "winRate": win_rate,
        "cumReturn": cum_return,
        "maxDrawdown": round(max_drawdown * 100, 2),
        "sampleWarning": (
            "noTrades" if trades_count == 0 else ("insufficient" if trades_count < SAMPLE_MIN_TRADES else None)
        ),
        "reason": None,
    }

    detail = {
        "start": window["start"],
        "end": window["end"],
        "tradingDays": window["tradingDays"],
        "trades": [
            [
                dates[trade["entry_idx"]],
                trade["buy"],
                dates[trade["exit_idx"]],
                round_price(trade["sell"], digits),
                trade["exit_idx"] - trade["entry_idx"],
                round((trade["sell"] / trade["buy"] - 1) * 100, 2),
                trade["pnl"],
                trade["exit_reason"],
            ]
            for trade in raw_trades
        ],
        "pnlTotal": pnl_total,
        "cumReturn": cum_return,
        "maxDrawdown": result["maxDrawdown"],
        "equity": equity,
        "peak": {"date": dates[peak_idx], "value": round(peak, 2)},
        "maxDrawdownRange": (
            {
                "start": dates[max_dd_peak_idx],
                "end": dates[max_dd_trough_idx],
                "pct": result["maxDrawdown"],
            }
            if max_drawdown > 0
            else None
        ),
    }
    return result, detail


def build_summary(item: dict, dates: list[str], results: dict[str, dict], generated_at: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "code": item["code"],
        "name": item["name"],
        "asset": item["asset"],
        "latestDate": dates[-1],
        "strategy": STRATEGY_META,
        "windows": results,
    }


def build_detail(item: dict, dates: list[str], details: dict[str, dict], generated_at: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "code": item["code"],
        "name": item["name"],
        "asset": item["asset"],
        "latestDate": dates[-1],
        "notional": int(NOTIONAL_PER_TRADE),
        "strategy": STRATEGY_META,
        "windows": details,
    }


def assert_detail_consistent(code: str, summary: dict, detail: dict) -> None:
    """SUMMARY 与 DETAIL 同源自洽断言：不一致即构建失败，不在展示层圆数字。"""
    for key, window_detail in detail["windows"].items():
        result = summary["windows"].get(key)
        if not result or not result["available"]:
            raise SystemExit(f"[{code}] 明细档位缺少对应摘要：{key}")
        trades = window_detail["trades"]
        if len(trades) != result["trades"]:
            raise SystemExit(f"[{code}/{key}] 明细笔数 {len(trades)} != 摘要笔数 {result['trades']}")
        pnl_sum = round(sum(trade[6] for trade in trades), 2)
        if abs(pnl_sum - window_detail["pnlTotal"]) > 0.005:
            raise SystemExit(f"[{code}/{key}] 逐笔 pnl 合计 {pnl_sum} != pnlTotal {window_detail['pnlTotal']}")
        if abs(round(window_detail["pnlTotal"] / 100, 2) - result["cumReturn"]) > 0.011:
            raise SystemExit(
                f"[{code}/{key}] 逐笔合计折算 {round(window_detail['pnlTotal'] / 100, 2)} != 摘要累计收益率 {result['cumReturn']}"
            )
        if not window_detail["equity"]:
            raise SystemExit(f"[{code}/{key}] 权益曲线为空")
        last = window_detail["equity"][-1]
        if abs(last - (100 + result["cumReturn"])) > 0.011:
            raise SystemExit(f"[{code}/{key}] 权益曲线终值 {last} != 100 + 累计收益率 {result['cumReturn']}")
        dd_range = window_detail["maxDrawdownRange"]
        if dd_range is not None:
            if abs(dd_range["pct"] - result["maxDrawdown"]) > 0.005:
                raise SystemExit(f"[{code}/{key}] 明细最大回撤 {dd_range['pct']} != 摘要 {result['maxDrawdown']}")
        elif abs(result["maxDrawdown"]) > 0.005:
            raise SystemExit(f"[{code}/{key}] 无回撤区间但摘要最大回撤为 {result['maxDrawdown']}")


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    value = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return round(value, 2)


def build_distribution(windows: list[dict], summaries: dict[str, dict]) -> dict:
    """池内分布概览：只给聚合，不点名标的、不排序（us-114 形态 A）。"""
    out: dict[str, dict] = {}
    for window in windows:
        if not window["available"]:
            continue
        key = window["key"]
        results = [summary["windows"][key] for summary in summaries.values() if summary["windows"][key]["available"]]
        if not results:
            continue
        sample = len(results)
        positive = sum(1 for r in results if (r["cumReturn"] or 0) > 0)
        buckets = {"lt0": 0, "0to20": 0, "20to50": 0, "gt50": 0}
        for r in results:
            value = float(r["cumReturn"] or 0)
            if value < 0:
                buckets["lt0"] += 1
            elif value <= 20:
                buckets["0to20"] += 1
            elif value <= 50:
                buckets["20to50"] += 1
            else:
                buckets["gt50"] += 1
        out[key] = {
            "start": window["start"],
            "end": window["end"],
            "tradingDays": window["tradingDays"],
            "sample": sample,
            "positiveCount": positive,
            "positiveShare": round(positive / sample * 100, 1),
            "medianCumReturn": median([float(r["cumReturn"] or 0) for r in results]),
            "medianWinRate": median([float(r["winRate"]) for r in results if r["winRate"] is not None]),
            "medianMaxDrawdown": median([float(r["maxDrawdown"] or 0) for r in results]),
            "buckets": buckets,
        }
    return out


def build_ranking(windows: list[dict], summaries: dict[str, dict], generated_at: str, latest_date: str) -> dict:
    """内测收益排序（独立路由、noindex）：只纳入笔数 ≥ 5 的标的，最多 10 行。"""
    out: dict[str, dict] = {}
    for window in windows:
        if not window["available"]:
            continue
        key = window["key"]
        rows = []
        for code, summary in summaries.items():
            result = summary["windows"][key]
            if not result["available"] or (result["trades"] or 0) < RANKING_MIN_TRADES:
                continue
            rows.append(
                {
                    "code": code,
                    "name": summary["name"],
                    "cumReturn": result["cumReturn"],
                    "winRate": result["winRate"],
                    "trades": result["trades"],
                    "maxDrawdown": result["maxDrawdown"],
                }
            )
        rows.sort(key=lambda row: (-row["cumReturn"], row["code"]))
        out[key] = {
            "start": window["start"],
            "end": window["end"],
            "tradingDays": window["tradingDays"],
            "minTrades": RANKING_MIN_TRADES,
            "entries": rows[:RANKING_LIMIT],
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "latestDate": latest_date,
        "windows": out,
    }


def dump_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def assert_budget(payload: object, limit: int, label: str) -> None:
    size = len(dump_bytes(payload))
    if size > limit:
        raise SystemExit(f"{label} 体积超预算：{size}B > {limit}B")


def run_build(data_dir: Path, index_only: bool, base_path: Path = BASE_FILE) -> int:
    evidence = require_gate()

    archive_dir = data_dir / "archive"
    if not archive_dir.exists():
        raise SystemExit(f"archive dir not found: {archive_dir}")

    archive_dates, stocks_by_date, etfs_by_date = load_snapshots(archive_dir)
    fake_dates = set(evidence.get("range", {}).get("nonTradingSnapshots", []))
    if fake_dates:
        archive_dates = [day for day in archive_dates if day not in fake_dates]
        stocks_by_date = {day: value for day, value in stocks_by_date.items() if day not in fake_dates}
        etfs_by_date = {day: value for day, value in etfs_by_date.items() if day not in fake_dates}

    expected = evidence.get("range", {})
    actual = (archive_dates[0] if archive_dates else None, archive_dates[-1] if archive_dates else None, len(archive_dates))
    wanted = (expected.get("dataStart"), expected.get("dataEnd"), expected.get("tradingDays"))
    if actual != wanted:
        raise SystemExit(f"archive 交易日历与 P-1 不一致：actual={actual}, p1={wanted}")
    print(f"[backtest] archive 交易日过滤：{len(archive_dates)} 天（剔除 {len(fake_dates)} 个非交易日假快照）")

    base = load_base(base_path)
    dates, stocks_by_date, etfs_by_date = merge_base(base, archive_dates, stocks_by_date, etfs_by_date)
    print(
        f"[backtest] 底座拼接：{base['dataStart']} ~ {base['dataEnd']}（{len(base['dates'])} 日）"
        f" + archive {archive_dates[0]} ~ {archive_dates[-1]}（{len(archive_dates)} 日）"
        f" = {dates[0]} ~ {dates[-1]}（{len(dates)} 日）"
    )

    leaderboard = load_leaderboard(data_dir)
    if archive_dates[-1] != leaderboard.get("latestDate"):
        raise SystemExit(f"结果末日与 leaderboard.latestDate 不一致：{archive_dates[-1]} vs {leaderboard.get('latestDate')}")

    raw_closes: dict[str, dict[str, float]] = {}
    for items_by_date in (stocks_by_date, etfs_by_date):
        for day, items in items_by_date.items():
            for it in items:
                code = normalize_code(it.get("code"))
                if code and it.get("latest"):
                    raw_closes.setdefault(code, {})[day] = float(it["latest"])

    stock_panel = build_panel(dates, stocks_by_date, "stock")
    etf_panel = build_panel(dates, etfs_by_date, "etf")
    keywords = load_money_bond_keywords(evidence)
    pool = build_pool(evidence, leaderboard, keywords)

    base_meta = load_base_meta()
    drift = (base_meta.get("validation") or {}).get("driftVsQfqPp") or {}
    worst = drift.get("worst") or {}
    worst_name = next(
        (item["name"] for item in pool if item["code"] == normalize_code(worst.get("code"))), worst.get("code")
    )
    methodology = {
        "priceAdjustment": "前复权（比率复权；底座与 archive 拼接后统一走 adjust_price_series，不二次缩放）",
        "driftVsOfficialQfq": {
            "medianPp": drift.get("median"),
            "maxAbsPp": drift.get("maxAbs"),
            "worstName": worst_name,
        },
        "note": "12m 绝对收益受复权口径影响；未计佣金与滑点",
    }

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    bars = build_bars(pool, dates, stocks_by_date, etfs_by_date, stock_panel, etf_panel)
    assert_splice_continuity(bars, dates, archive_dates, raw_closes)

    pre_windows = build_windows(dates)
    coverage = build_coverage(dates, pre_windows, bars, pool)
    windows = build_windows(dates, coverage, len(pool))
    # 底座 meta 是覆盖口径的权威来源：档位可用数、缺口标的与天数按 meta 声明写入文案
    constraints = base_meta.get("constraints") or {}
    declared_insufficient = {
        normalize_code(row.get("code")): row
        for row in (constraints.get("insufficient") or [])
        if normalize_code(row.get("code"))
    }
    for window in windows:
        tier = (constraints.get("tiers") or {}).get(window["key"])
        if not tier or "/" not in str(tier):
            continue
        ok_text, total_text = str(tier).split("/", 1)
        shortfall = [
            row
            for row in declared_insufficient.values()
            if int(row.get("days") or 0) < window["minTradingDays"]
        ]
        window["availableSymbols"] = int(ok_text)
        window["sample"] = int(total_text)
        window["available"] = int(ok_text) >= -(-int(total_text) // 2)
        shortfall.sort(key=lambda row: (-int(row.get("days") or 0), str(row.get("code"))))
        window["coverageNote"] = (
            None
            if not shortfall
            else f"{ok_text}/{total_text} 只满足 {window['minTradingDays']} 个交易日；"
            + "、".join(f"{row.get('name')} {row.get('days')} 日" for row in shortfall)
            + f"，数据不足，故{window['label']}档对上述 {len(shortfall)} 只标的不适用"
        )
    print(
        "  档位可用标的数: "
        + " / ".join(f"{w['key']}={w['availableSymbols']}/{w['sample']}" for w in windows)
    )

    out_dir = data_dir / OUT_DIR_NAME
    summary_dir = out_dir / "summary"
    detail_dir = out_dir / "detail"
    internal_dir = out_dir / "internal"

    if index_only:
        index = build_index(dates, pool, generated_at, windows=windows, methodology=methodology)
        assert_budget(index, INDEX_MAX_BYTES, "index.json")
        write_json_atomic(out_dir / "index.json", index)
        assert_no_money_bond_leak(out_dir / "index.json", keywords)
        print(f"backtest index written: {out_dir / 'index.json'} ({len(dump_bytes(index))}B)")
        print(f"  pool: {index['poolStats']}")
        print(f"  windows: {[(w['key'], w['available'], w['tradingDays']) for w in index['windows']]}")
        print("  mode: --index-only（未生成单标的摘要与明细，未输出任何回测指标）")
        return 0

    summaries: dict[str, dict] = {}
    details: dict[str, dict] = {}
    for item in pool:
        results: dict[str, dict] = {}
        detail_windows: dict[str, dict] = {}
        for window in windows:
            result, detail = simulate_window(bars[item["code"]], dates, window, item["asset"])
            declared = declared_insufficient.get(item["code"])
            if declared and not result["available"] and result.get("availableTradingDays") is not None:
                declared_days = int(declared.get("days") or 0)
                if declared_days < window["minTradingDays"]:
                    # 与底座 meta 的对外口径保持一致（如中微公司 12m：235 日）
                    result["availableTradingDays"] = declared_days
                    result["tradingDays"] = declared_days
                    result["reason"] = f"该标的此区间数据不足（可用 {declared_days} 个交易日）"
            results[window["key"]] = result
            if detail is not None:
                detail_windows[window["key"]] = detail
        summary = build_summary(item, dates, results, generated_at)
        detail_doc = build_detail(item, dates, detail_windows, generated_at)
        assert_budget(summary, SUMMARY_MAX_BYTES, f"{item['code']} summary")
        assert_detail_consistent(item["code"], summary, detail_doc)
        for key, window_detail in detail_doc["windows"].items():
            size = len(dump_bytes(window_detail))
            if size > DETAIL_WINDOW_MAX_BYTES:
                raise SystemExit(f"{item['code']}/{key} 明细超预算：{size}B > {DETAIL_WINDOW_MAX_BYTES}B")
        summaries[item["code"]] = summary
        details[item["code"]] = detail_doc

    detail_total = sum(len(dump_bytes(doc)) for doc in details.values())
    if detail_total > DETAIL_TOTAL_MAX_BYTES:
        raise SystemExit(f"明细总量超预算：{detail_total}B > {DETAIL_TOTAL_MAX_BYTES}B")

    distribution = build_distribution(windows, summaries)
    index = build_index(
        dates, pool, generated_at, distribution=distribution, windows=windows, methodology=methodology
    )
    assert_budget(index, INDEX_MAX_BYTES, "index.json")
    ranking = build_ranking(windows, summaries, generated_at, dates[-1])

    # 全部构建成功后再落盘，避免半成品
    write_json_atomic(out_dir / "index.json", index)
    written_paths = {summary_dir / f"{code}.json" for code in summaries}
    for code, summary in summaries.items():
        write_json_atomic(summary_dir / f"{code}.json", summary)
    for stale in summary_dir.glob("*.json"):
        if stale not in written_paths:
            stale.unlink()
    detail_paths = {detail_dir / f"{code}.json" for code in details}
    for code, detail_doc in details.items():
        write_json_atomic(detail_dir / f"{code}.json", detail_doc)
    for stale in detail_dir.glob("*.json"):
        if stale not in detail_paths:
            stale.unlink()
    write_json_atomic(internal_dir / "ranking.json", ranking)
    assert_no_money_bond_leak(out_dir / "index.json", keywords)

    print(f"backtest written: {out_dir} ({len(dump_bytes(index))}B index + {len(summaries)} summaries + {len(details)} details)")
    print(f"  data: {index['dataStart']} ~ {index['latestDate']} / {index['tradingDays']} 交易日")
    print(f"  windows: {[(w['key'], w['available'], w['start'], w['tradingDays']) for w in index['windows']]}")
    print(f"  pool: {index['poolStats']}")
    print(f"  detail total: {detail_total}B / ranking: {len(dump_bytes(ranking))}B")
    for code in ("510300", "600519", "300750"):
        if code not in summaries:
            continue
        row = summaries[code]
        print(
            f"  sample {code}: "
            + " | ".join(
                f"{key}: trades={row['windows'][key]['trades']} wins={row['windows'][key]['wins']} "
                f"winRate={row['windows'][key]['winRate']}% cumReturn={row['windows'][key]['cumReturn']}% "
                f"maxDrawdown={row['windows'][key]['maxDrawdown']}%"
                for key in ("3m", "2w", "4w", "6m", "9m", "12m")
                if row["windows"][key]["available"]
            )
        )
    if "510300" in details:
        print(
            "  sample 510300 consistency: "
            f"pnlTotal={details['510300']['windows']['3m']['pnlTotal']} "
            f"cumReturn={summaries['510300']['windows']['3m']['cumReturn']}%"
        )
    for window in index["windows"]:
        if window.get("coverageNote"):
            print(f"  coverage {window['key']}: {window['coverageNote']}")
    return 0


def run_check(data_dir: Path) -> int:
    gate_open = GATE_FILE.exists() and GATE_FILE.stat().st_size > 0
    status = {
        "gate": "open" if gate_open else "blocked",
        "gateFile": str(GATE_FILE.relative_to(ROOT)),
        "evidence": P1_EVIDENCE.is_file(),
        "archive": (data_dir / "archive").is_dir(),
        "leaderboard": (data_dir / "leaderboard.json").is_file(),
        "artifactsWritten": False,
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not gate_open:
        print("[backtest] 硬门禁未开：不会读取行情、不会生成任何回测数字。", file=sys.stderr)
    return 0


def run_print_contract() -> int:
    print(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "index": INDEX_CONTRACT,
                "summary": SUMMARY_CONTRACT,
                "detail": DETAIL_CONTRACT,
                "windows": [
                    {"key": key, "label": label, "nominalTradingDays": nominal, "minTradingDays": threshold}
                    for key, label, nominal, threshold in WINDOWS
                ],
                "sampleWarning": {
                    "minTrades": SAMPLE_MIN_TRADES,
                    "insufficient": f"{SAMPLE_MIN_TRADES} 笔以下（且 > 0）标注“样本不足（N 笔）”",
                    "noTrades": "0 笔显示“无触发交易”",
                },
                "strategy": STRATEGY_META,
                "gate": "team/us/us-110/p1_data_conclusion.md",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build static backtest JSON for jiucaiquan web.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--base-file", default=str(BASE_FILE), help="历史底座文件（默认 services/market-data/backtest-base/history_base.json）")
    parser.add_argument("--index-only", action="store_true", help="仅生成索引，不生成单标的摘要")
    parser.add_argument("--check", action="store_true", help="检查门禁与输入文件，不读取行情、不写产物")
    parser.add_argument("--print-contract", action="store_true", help="输出 JSON 数据契约")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    if args.print_contract:
        raise SystemExit(run_print_contract())
    if args.check:
        raise SystemExit(run_check(data_dir))
    try:
        raise SystemExit(run_build(data_dir, args.index_only, Path(args.base_file).resolve()))
    except FileNotFoundError as exc:
        print(f"[backtest] 历史底座缺失，已终止：{exc}", file=sys.stderr)
        raise SystemExit(4)
