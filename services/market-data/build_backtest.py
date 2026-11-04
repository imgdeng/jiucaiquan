"""us-110 回测 MVP 预计算脚本。

- 复用 build_leaderboard.py 的 archive 读取与前复权实现，不新建数据源；
- 按 P-1 结论剔除 8 个非交易日假快照，代入 P-1 证据池（60 只，成交额降序）；
- 按 01_req.md §4 冻结口径计算 3m 档胜率 / 累计收益率 / 最大回撤；
- 输出契约：index.json（≤150KB）+ summary/{code}.json（≤20KB）；
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
OUT_DIR_NAME = "backtest"

SCHEMA_VERSION = 1
POOL_MIN_TOTAL = 50
POOL_MIN_PER_ASSET = 25
FORCED_CODES = (("510300", "etf"), ("600519", "stock"))

# 档位名义窗口、最低交易日门槛、3m 档最低可用门槛（01_req.md §3.1/§3.2）
# (key, label, 名义交易日数, 最低门槛, 3m 专属最低门槛)
WINDOWS: tuple[tuple[str, str, int, int], ...] = (
    ("3m", "近 3 个月", 60, 20),
    ("6m", "近 6 个月", 120, 120),
    ("12m", "近 12 个月", 240, 240),
)
UNAVAILABLE_REASON = "数据积累中"
# 货币/现金类 ETF 不得入池（名称命中即排除，并在构建末尾做泄漏断言）
MONEY_ETF_KEYWORDS = ("货币", "日利", "添利", "现金")

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
        "note": "6m/12m 未达门槛时 available=false，reason=“数据积累中”；3m 未达 20 日时 reason=“数据不足”",
    },
    "poolItem": {
        "required": ["code", "name", "asset", "amount", "summary"],
        "note": "code 为不带市场前缀的 6 位码；pool 默认按末日成交额降序；amount 仅用于排序，不展示为热度",
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
        "sampleInsufficient": "trades < 3 时为 true",
    },
    "notGenerated": "逐笔明细与权益曲线按 D1 不生成、不展示、前端不请求",
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


def panel_by_norm_code(panel: dict[str, dict]) -> dict[str, tuple[str, dict]]:
    """{归一化 6 位码: (archive 原始码, 面板数据)}，同码保留首个。"""
    out: dict[str, tuple[str, dict]] = {}
    for raw_code, item in panel.items():
        code = normalize_code(raw_code)
        if code and code not in out:
            out[code] = (raw_code, item)
    return out


def build_pool(evidence: dict, leaderboard: dict) -> list[dict]:
    """固定标的池：代入 P-1 证据池，显式排除货币/现金类 ETF，并按末日成交额降序。

    P-1 已完成成交额头部筛选、异常标的剔除与“不足 60 日”剔除；这里只做代入与校验，
    不重新推导，避免与书面结论产生第二套口径。
    """
    if not MONEY_ETF_KEYWORDS:
        raise SystemExit("货币 ETF 排除关键词缺失，拒绝构建")

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
        if asset == "etf" and any(keyword in name for keyword in MONEY_ETF_KEYWORDS):
            print(f"[backtest] 排除货币/现金类 ETF：{code} {name}", file=sys.stderr)
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

    # 构建断言：货币/现金类 ETF 命中即退出
    leaked = [item for item in pool if item["asset"] == "etf" and any(k in item["name"] for k in MONEY_ETF_KEYWORDS)]
    if leaked:
        detail = ", ".join(f"{item['code']} {item['name']}" for item in leaked)
        raise SystemExit(f"货币/现金类 ETF 仍在池内：{detail}")
    return pool


def build_windows(dates: list[str]) -> list[dict]:
    """按 01_req.md §3.1/§3.2 计算档位可用性与实际生效区间（回补后自动开放）。"""
    total = len(dates)
    end = dates[-1]
    windows: list[dict] = []
    for key, label, nominal_days, min_days in WINDOWS:
        # 3m 无 60 日硬门槛：不足 3 个月时按实际区间展示，但需 ≥20 个交易日
        available = total >= min_days
        span = min(nominal_days, total)
        if available:
            start_idx = total - span
            windows.append(
                {
                    "key": key,
                    "label": label,
                    "minTradingDays": min_days,
                    "available": True,
                    "start": dates[start_idx],
                    "end": end,
                    "tradingDays": total - start_idx,
                    "reason": None,
                }
            )
        else:
            windows.append(
                {
                    "key": key,
                    "label": label,
                    "minTradingDays": min_days,
                    "available": False,
                    "start": None,
                    "end": None,
                    "tradingDays": None,
                    "reason": "数据不足" if key == "3m" else UNAVAILABLE_REASON,
                }
            )
    return windows


def build_index(dates: list[str], pool: list[dict], generated_at: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "latestDate": dates[-1],
        "dataStart": dates[0],
        "tradingDays": len(dates),
        "strategy": STRATEGY_META,
        "windows": build_windows(dates),
        "poolStats": {
            "total": len(pool),
            "etf": sum(1 for item in pool if item["asset"] == "etf"),
            "stock": sum(1 for item in pool if item["asset"] == "stock"),
        },
        "pool": pool,
    }


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


def simulate_window(series: dict[str, dict], dates: list[str], window: dict, asset: str) -> dict:
    """按 01_req.md §4 的冻结规则执行串行单仓模拟。

    样本末段前瞻窗口不足 holdDays 的信号无法完整结算，直接跳过，不虚构平仓价。
    """
    if not window["available"]:
        return {
            "available": False,
            "start": None,
            "end": None,
            "tradingDays": None,
            "trades": 0,
            "wins": 0,
            "winRate": None,
            "cumReturn": 0.0,
            "maxDrawdown": 0.0,
            "sampleInsufficient": True,
            "reason": window.get("reason"),
        }

    start_idx = dates.index(window["start"])
    end_idx = dates.index(window["end"])
    hold = STRATEGY_META["holdDays"]
    digits = price_digits(asset)

    trades: list[dict] = []
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
        for j in range(i + 1, i + hold + 1):
            if series[dates[j]]["high"] >= sell:
                exit_idx = j
                exit_price = sell
                break

        pnl = NOTIONAL_PER_TRADE * (exit_price / buy - 1)
        trades.append(
            {
                "entry_idx": i + 1,
                "exit_idx": exit_idx,
                "buy": buy,
                "sell": exit_price,
                "pnl": pnl,
            }
        )
        i = max(i + 1, exit_idx)

    wins = sum(1 for trade in trades if trade["pnl"] > 0)
    trades_count = len(trades)
    win_rate = round(wins / trades_count * 100, 1) if trades_count else None
    cum_return = round(sum(trade["pnl"] for trade in trades) / NOTIONAL_PER_TRADE * 100, 2)

    # 逐日权益 = 初始资金 1 万 + 已实现盈亏 + 持仓浮动盈亏；峰值从 1 万起算
    trades_by_exit: dict[int, list[dict]] = {}
    for trade in trades:
        trades_by_exit.setdefault(trade["exit_idx"], []).append(trade)
    realized = 0.0
    peak = NOTIONAL_PER_TRADE
    max_drawdown = 0.0
    last_close: float | None = None
    for idx in range(start_idx, end_idx + 1):
        for trade in trades_by_exit.get(idx, []):
            realized += trade["pnl"]
        candidate = next((t for t in trades if t["entry_idx"] <= idx < t["exit_idx"]), None)
        day = dates[idx]
        if day in series:
            last_close = series[day]["close"]
        floating = 0.0
        if candidate is not None and last_close is not None:
            floating = NOTIONAL_PER_TRADE * (last_close / candidate["buy"] - 1)
        equity = NOTIONAL_PER_TRADE + realized + floating
        peak = max(peak, equity)
        drawdown = 1 - equity / peak if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    return {
        "available": True,
        "start": window["start"],
        "end": window["end"],
        "tradingDays": window["tradingDays"],
        "trades": trades_count,
        "wins": wins,
        "winRate": win_rate,
        "cumReturn": cum_return,
        "maxDrawdown": round(max_drawdown * 100, 2),
        "sampleInsufficient": trades_count < 3,
        "reason": None,
    }


def build_summary(
    item: dict,
    dates: list[str],
    windows: list[dict],
    series: dict[str, dict],
    generated_at: str,
) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "code": item["code"],
        "name": item["name"],
        "asset": item["asset"],
        "latestDate": dates[-1],
        "strategy": STRATEGY_META,
        "windows": {
            window["key"]: simulate_window(series, dates, window, item["asset"])
            for window in windows
        },
    }


def dump_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def assert_budget(payload: object, limit: int, label: str) -> None:
    size = len(dump_bytes(payload))
    if size > limit:
        raise SystemExit(f"{label} 体积超预算：{size}B > {limit}B")


def run_build(data_dir: Path, index_only: bool) -> int:
    evidence = require_gate()

    archive_dir = data_dir / "archive"
    if not archive_dir.exists():
        raise SystemExit(f"archive dir not found: {archive_dir}")

    dates, stocks_by_date, etfs_by_date = load_snapshots(archive_dir)
    fake_dates = set(evidence.get("range", {}).get("nonTradingSnapshots", []))
    if fake_dates:
        dates = [day for day in dates if day not in fake_dates]
        stocks_by_date = {day: value for day, value in stocks_by_date.items() if day not in fake_dates}
        etfs_by_date = {day: value for day, value in etfs_by_date.items() if day not in fake_dates}

    expected = evidence.get("range", {})
    actual = (dates[0] if dates else None, dates[-1] if dates else None, len(dates))
    wanted = (expected.get("dataStart"), expected.get("dataEnd"), expected.get("tradingDays"))
    if actual != wanted:
        raise SystemExit(f"交易日历与 P-1 不一致：actual={actual}, p1={wanted}")
    print(f"[backtest] 交易日过滤：{len(dates)} 天（剔除 {len(fake_dates)} 个非交易日假快照）")

    leaderboard = load_leaderboard(data_dir)
    if dates[-1] != leaderboard.get("latestDate"):
        raise SystemExit(f"结果末日与 leaderboard.latestDate 不一致：{dates[-1]} vs {leaderboard.get('latestDate')}")

    stock_panel = build_panel(dates, stocks_by_date, "stock")
    etf_panel = build_panel(dates, etfs_by_date, "etf")
    pool = build_pool(evidence, leaderboard)

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    index = build_index(dates, pool, generated_at)
    assert_budget(index, INDEX_MAX_BYTES, "index.json")

    out_dir = data_dir / OUT_DIR_NAME
    summary_dir = out_dir / "summary"

    if index_only:
        write_json_atomic(out_dir / "index.json", index)
        print(f"backtest index written: {out_dir / 'index.json'} ({len(dump_bytes(index))}B)")
        print(f"  pool: {index['poolStats']}")
        print(f"  windows: {[(w['key'], w['available'], w['tradingDays']) for w in index['windows']]}")
        print("  mode: --index-only（未生成单标的摘要，未输出任何回测指标）")
        return 0

    bars = build_bars(pool, dates, stocks_by_date, etfs_by_date, stock_panel, etf_panel)
    summaries: dict[str, dict] = {}
    for item in pool:
        summary = build_summary(item, dates, index["windows"], bars[item["code"]], generated_at)
        assert_budget(summary, SUMMARY_MAX_BYTES, f"{item['code']} summary")
        summaries[item["code"]] = summary

    # 全部构建成功后再落盘，避免半成品
    write_json_atomic(out_dir / "index.json", index)
    written_paths = {summary_dir / f"{code}.json" for code in summaries}
    for code, summary in summaries.items():
        write_json_atomic(summary_dir / f"{code}.json", summary)
    for stale in summary_dir.glob("*.json"):
        if stale not in written_paths:
            stale.unlink()

    sample = summaries.get("510300") or next(iter(summaries.values()))
    sample_result = sample["windows"]["3m"]
    print(f"backtest written: {out_dir} ({len(dump_bytes(index))}B index + {len(summaries)} summaries)")
    print(f"  data: {index['dataStart']} ~ {index['latestDate']} / {index['tradingDays']} 交易日")
    print(f"  windows: {[(w['key'], w['available'], w['start'], w['tradingDays']) for w in index['windows']]}")
    print(f"  pool: {index['poolStats']}")
    print(
        "  sample 510300: "
        f"trades={sample_result['trades']} wins={sample_result['wins']} "
        f"winRate={sample_result['winRate']}% cumReturn={sample_result['cumReturn']}% "
        f"maxDrawdown={sample_result['maxDrawdown']}%"
    )
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
                "windows": [
                    {"key": key, "label": label, "nominalTradingDays": nominal, "minTradingDays": threshold}
                    for key, label, nominal, threshold in WINDOWS
                ],
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
    raise SystemExit(run_build(data_dir, args.index_only))
