"""us-110 P-1 数据前置门禁审计（archive 口径）。

只读 apps/web/public/data/archive，输出可复核的关键数字：
可用交易日、覆盖率、资产归类冲突、复权残留异常、候选标的池及其 qfq 校准偏差。

用法：
    python services/market-data/audit_archive_availability.py
    # 结果写入 team/us/us-110/p1_evidence.json，并打印摘要
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import akshare as ak

SERVICE_DIR = Path(__file__).resolve().parent
ROOT = SERVICE_DIR.parents[1]
DATA_DIR = ROOT / "apps" / "web" / "public" / "data"
EVIDENCE_PATH = ROOT / "team" / "us" / "us-110" / "p1_evidence.json"

sys.path.insert(0, str(SERVICE_DIR))
from build_leaderboard import adjust_price_series, price_limit  # noqa: E402

# 货币/债券类 ETF 名称关键词（比 build_leaderboard.is_bond_etf 更全，含货币基金常见命名）
MONEY_BOND_KEYWORDS = (
    "债", "货币", "现金", "添益", "理财", "短融", "国债",
    "日利", "添利", "保证金", "收益快线", "快线", "财富宝", "存单",
    "政金", "金融债", "利率债", "信用债", "可转债", "转债",
)
LEGACY_MONEY_BOND_KEYWORDS = ("债", "货币", "现金", "添益", "理财", "短融", "国债")

MIN_DAYS_3M = 60
DRIFT_LIMIT_PP = 3.0
GAP_LIMIT = 0.05
# ETF 固定 29 只：剔除货币类 511880 后不递补，避免冻结期引入新标的
POOL_LIMITS = {"etf": 29, "stock": 30}


def matched_keywords(name: str, keywords: tuple[str, ...]) -> list[str]:
    return [k for k in keywords if k in name]


def is_money_bond_etf(name: str) -> bool:
    return bool(matched_keywords(name, MONEY_BOND_KEYWORDS))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_archive():
    """按真实快照日去重，返回 (交易日列表, 节假日假快照, {date: (stocks, etfs)})。"""
    cal = [str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"]]
    cal_set = set(cal)
    snaps = {}
    for folder in sorted(d for d in DATA_DIR.joinpath("archive").iterdir() if d.is_dir()):
        stocks = read_json(folder / "stock-latest.json")
        etfs = read_json(folder / "etf-latest.json")
        if not stocks:
            continue
        day = str(stocks[0].get("snapshotAt", ""))[:10]
        snaps[day] = (stocks, etfs)
    days = sorted(snaps)
    real = [d for d in days if d in cal_set]
    fake = [d for d in days if d not in cal_set]
    return real, fake, snaps


def build_series(real, snaps, kind_index: int):
    series = {}
    names = {}
    for d in real:
        for item in snaps[d][kind_index]:
            px = item.get("latest")
            if not px:
                continue
            code = str(item.get("code") or "")
            series.setdefault(code, {})[d] = float(px)
            names[code] = str(item.get("name") or "").strip()
    return series, names


def fetch_qfq(code: str, kind: str, start: str, end: str):
    start_s, end_s = start.replace("-", ""), end.replace("-", "")
    if kind == "etf":
        df = ak.fund_etf_hist_em(symbol=code[2:], period="daily", start_date=start_s, end_date=end_s, adjust="qfq")
    else:
        df = ak.stock_zh_a_hist(symbol=code[2:], period="daily", start_date=start_s, end_date=end_s, adjust="qfq")
    return {str(rec["日期"])[:10]: float(rec["收盘"]) for rec in df.to_dict("records") if rec.get("收盘")}


def main() -> int:
    real, fake, snaps = load_archive()
    stocks, stock_names = build_series(real, snaps, 0)
    etfs, etf_names = build_series(real, snaps, 1)
    start, end = real[0], real[-1]

    both = sorted(set(stocks) & set(etfs))
    insufficient = (
        [{"code": c, "name": stock_names[c], "kind": "stock", "days": len(p)}
         for c, p in stocks.items() if len(p) < MIN_DAYS_3M]
        + [{"code": c, "name": etf_names[c], "kind": "etf", "days": len(p)}
           for c, p in etfs.items() if len(p) < MIN_DAYS_3M]
    )

    # 复权后仍超涨跌幅上限的标的（build_leaderboard 比率复权残留）
    residual = []
    for kind, series, names in (("stock", stocks, stock_names), ("etf", etfs, etf_names)):
        for code, px in series.items():
            adj = adjust_price_series(real, px, code, names[code], kind)
            lim = price_limit(code, names[code], kind)
            worst = max((abs(adj[real[i]] / adj[real[i - 1]] - 1)
                         for i in range(1, len(real)) if real[i] in adj and real[i - 1] in adj),
                        default=0.0)
            if worst > lim + 0.02:
                residual.append({"code": code, "name": names[code], "kind": kind,
                                 "maxDailyRet": round(worst, 4)})

    # 候选池：末日成交额降序（ETF 先剔除货币/债券类）
    last = snaps[real[-1]]
    stock_pool = sorted([x for x in last[0] if x.get("amount")], key=lambda x: -x["amount"])
    etf_universe = sorted([x for x in last[1] if x.get("amount")], key=lambda x: -x["amount"])
    money_bond_all = [{"code": x["code"], "name": x["name"], "amount": x.get("amount")}
                      for x in etf_universe if is_money_bond_etf(x["name"])]
    newly_caught = [{"code": x["code"], "name": x["name"], "amount": x.get("amount")}
                    for x in etf_universe
                    if is_money_bond_etf(x["name"])
                    and not matched_keywords(x["name"], LEGACY_MONEY_BOND_KEYWORDS)]
    legacy_top = [x for x in etf_universe
                  if not matched_keywords(x["name"], LEGACY_MONEY_BOND_KEYWORDS)][:30]
    removed_from_pool = [{"code": x["code"], "name": x["name"]}
                         for x in legacy_top if is_money_bond_etf(x["name"])]
    etf_pool = [x for x in etf_universe if not is_money_bond_etf(x["name"])]
    pool_rows, excluded = [], []
    for kind, items, series, names in (("etf", etf_pool, etfs, etf_names),
                                       ("stock", stock_pool, stocks, stock_names)):
        taken = 0
        for item in items:
            if taken >= POOL_LIMITS[kind]:
                break
            code, name = item["code"], str(item.get("name") or "").strip()
            px = series.get(code, {})
            days = len(px)
            if days < MIN_DAYS_3M:
                excluded.append({"code": code, "name": name, "kind": kind, "days": days,
                                 "reason": "数据不足60个交易日"})
                continue
            try:
                qfq = fetch_qfq(code, kind, start, end)
                time.sleep(0.04)
            except Exception as exc:  # noqa: BLE001
                excluded.append({"code": code, "name": name, "kind": kind,
                                 "reason": f"qfq 抓取失败: {type(exc).__name__}"})
                continue
            common = sorted(set(px) & set(qfq))
            if len(common) < MIN_DAYS_3M:
                excluded.append({"code": code, "name": name, "kind": kind,
                                 "reason": f"可对齐交易日仅{len(common)}个"})
                continue
            adj = adjust_price_series(real, px, code, name, kind)
            ratio_ret = adj[common[-1]] / adj[common[0]] - 1
            qfq_ret = qfq[common[-1]] / qfq[common[0]] - 1
            drift = round((ratio_ret - qfq_ret) * 100, 2)
            gap = round(max(abs(adj[d] / qfq[d] - 1) for d in common), 4)
            reason = None
            if abs(drift) > DRIFT_LIMIT_PP:
                reason = f"复权口径偏差{drift}pp"
            elif gap > GAP_LIMIT:
                reason = f"价位差{gap:.1%}"
            if reason:
                excluded.append({"code": code, "name": name, "kind": kind,
                                 "driftPp": drift, "priceGap": gap, "reason": reason})
                continue
            pool_rows.append({"code": code, "name": name, "kind": kind, "days": days,
                              "driftPp": drift, "priceGap": gap,
                              "ret3mQfq": round(qfq_ret * 100, 2)})
            taken += 1

    pool_etf = [r for r in pool_rows if r["kind"] == "etf"]
    pool_stock = [r for r in pool_rows if r["kind"] == "stock"]
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "apps/web/public/data/archive（本地=远程 origin/main 285b486）",
        "range": {
            "dataStart": start,
            "dataEnd": end,
            "tradingDays": len(real),
            "archiveFolders": len(real) + len(fake),
            "nonTradingSnapshots": fake,
            "meets60Days": len(real) >= MIN_DAYS_3M,
            "meets120Days": len(real) >= 120,
            "meets240Days": len(real) >= 240,
        },
        "coverage": {
            "stockCodes": len(stocks),
            "etfCodes": len(etfs),
            "stockWith60Days": sum(1 for p in stocks.values() if len(p) >= MIN_DAYS_3M),
            "etfWith60Days": sum(1 for p in etfs.values() if len(p) >= MIN_DAYS_3M),
            "insufficientCount": len(insufficient),
        },
        "assetClassification": {
            "stockEtfOverlapCodes": both,
            "overlapCount": len(both),
            "sh600519InStock": "sh600519" in stocks,
            "sh600519InEtf": "sh600519" in etfs,
            "sh510300InEtf": "sh510300" in etfs,
        },
        "adjustment": {
            "method": "build_leaderboard.adjust_price_series（涨跌幅上限识别份额折算/除权）",
            "residualJumpCount": len(residual),
            "residualJumpSamples": residual[:10],
            "qfqDriftPp": {
                "poolMedian": round(statistics.median([abs(r["driftPp"]) for r in pool_rows]), 2)
                if pool_rows else None,
                "poolMax": max((abs(r["driftPp"]) for r in pool_rows), default=None),
            },
        },
        "pool": {
            "rule": "ETF 按末日成交额降序、剔除货币/债券类后取前 29 只（511880 剔除后不递补）；个股按末日成交额降序取前 30 只",
            "etfCount": len(pool_etf),
            "stockCount": len(pool_stock),
            "total": len(pool_rows),
            "symbols": pool_rows,
        },
        "moneyBondEtf": {
            "keywords": list(MONEY_BOND_KEYWORDS),
            "excludedCount": len(money_bond_all),
            "newlyCaughtCount": len(newly_caught),
            "newlyCaught": newly_caught,
            "removedFromPreviousPool": removed_from_pool,
            "excludedCodes": money_bond_all,
        },
        "excluded": excluded,
        "insufficientSymbols": insufficient,
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"可用区间 {start} ~ {end}，真实交易日 {len(real)}（≥60: {len(real) >= 60}）")
    print(f"假快照日 {len(fake)}：{fake}")
    print(f"个股 {len(stocks)} 只，≥60 日 {payload['coverage']['stockWith60Days']}；"
          f"ETF {len(etfs)} 只，≥60 日 {payload['coverage']['etfWith60Days']}")
    print(f"资产错分（股票/ETF 代码重叠）：{len(both)}；600519 in stock={payload['assetClassification']['sh600519InStock']}")
    print(f"复权后仍超限标的：{len(residual)}")
    print(f"货币/债券类 ETF：排除 {len(money_bond_all)} 只，新命中 {len(newly_caught)} 只，"
          f"本次从池中移除 {len(removed_from_pool)} 只")
    print(f"候选池：ETF {len(pool_etf)} + 个股 {len(pool_stock)} = {len(pool_rows)}；剔除 {len(excluded)}")
    print(f"证据写入 {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
