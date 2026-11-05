#!/usr/bin/env python3
"""26.11.1 UI 冒烟与截图（Playwright + Chromium）。

前置：同 api-smoke.py 起本地 Pages dev（含 D1，供首页工具台读取产物）。
用法：
  python3 docs/sprints/26.11.1/scripts/ui-smoke.py
环境变量：BASE（默认 http://127.0.0.1:4390）、OUT（截图目录）
"""
import json, os, re, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:4390")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
OUT = os.environ.get("OUT", os.path.join(ROOT, "docs/sprints/26.11.1/screenshots"))
BANNED = ["荐股", "带单", "牛股", "稳赚", "稳赢", "保证收益", "必涨", "翻倍",
          "推荐", "最优", "首选", "抄底", "热门"]
PAGES = [("/", "home"), ("/tools/backtest", "backtest"),
         ("/tools/condition-order", "condition-order"), ("/log", "log"),
         ("/labs/backtest-top", "labs")]
EXPECT_TITLE = {
    "/": "韭菜圈 | A 股条件单工具箱",
    "/tools/backtest": "回测 · 历史表现 | 韭菜圈",
    "/tools/condition-order": "条件单计算器 | 韭菜圈",
    "/log": "迭代日志 | 韭菜圈",
    "/labs/backtest-top": "回测收益排序（内测） | 韭菜圈",
}
res = {"routes": {}, "overflow": {}, "banned": {}, "notes": {}, "fail": []}

def shot(p, name):
    p.screenshot(path=os.path.join(OUT, name + ".png"), full_page=True)

def ov(p):
    r = p.evaluate("()=>({s:document.documentElement.scrollWidth,i:window.innerWidth})")
    if r["s"] != r["i"]:
        res["fail"].append(f"overflow {r}")
    return r

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN",
                        permissions=["clipboard-read", "clipboard-write"])
    p = ctx.new_page()
    tracks = []
    p.route("**/api/track", lambda r: (tracks.append(r.request.post_data), r.fulfill(status=204, body=""))[1])
    for path, name in PAGES:
        r = p.goto(BASE + path, wait_until="load"); p.wait_for_timeout(1500)
        t = p.locator("body").inner_text()
        res["routes"][path] = {"status": r.status, "title": p.title()}
        if r.status != 200 or p.title() != EXPECT_TITLE[path]:
            res["fail"].append(f"route {path} {r.status} {p.title()}")
        res["banned"][path] = [w for w in BANNED if w in t]
        if res["banned"][path]:
            res["fail"].append(f"banned {path} {res['banned'][path]}")
        res["overflow"]["1440" + path] = ov(p)
        shot(p, f"{name}-1440-default")

    # 回测交互
    p.goto(BASE + "/tools/backtest", wait_until="load"); p.wait_for_timeout(1500)
    grp = 'div[role="group"][aria-label="回测区间"] button'
    res["notes"]["windows"] = [p.locator(grp).nth(i).inner_text().replace("\n", "/")
                               for i in range(p.locator(grp).count())]
    res["notes"]["disabled"] = p.locator("button[disabled]").count()
    if res["notes"]["disabled"]:
        res["fail"].append("window buttons disabled")

    def pick(code, label):
        p.fill("#backtest-search", code); p.wait_for_timeout(300)
        p.locator("div.max-h-80 button", has_text=code).first.click(); p.wait_for_timeout(500)
        p.locator(grp, has_text=label).first.click(); p.wait_for_timeout(600)

    pick("688012", "近 12 个月")
    res["notes"]["12m_gap"] = "该标的此区间数据不足（可用 231 个交易日）" in p.locator("main").inner_text()
    shot(p, "backtest-1440-12m-gap")
    pick("510300", "近 2 周")
    res["notes"]["2w_sample"] = "样本不足（1 笔）" in p.locator("main").inner_text()
    shot(p, "backtest-1440-2w-sample")
    pick("510300", "近 4 周")
    res["notes"]["switch"] = "2026-09-30 ~ 2026-11-03" in p.locator("main").inner_text()
    shot(p, "backtest-1440-six-windows")
    pick("510300", "近 12 个月")
    p.locator("button", has_text="查看逐笔与权益曲线").click(); p.wait_for_timeout(900)
    res["notes"]["detail_rows"] = p.locator("table tbody tr").count()
    res["notes"]["detail_svg"] = p.locator("svg[role=img][aria-label*='权益曲线']").count()
    shot(p, "backtest-1440-detail-curve")
    p.locator("button", has_text="复制回测摘要").click(); p.wait_for_timeout(400)
    clip = p.evaluate("()=>navigator.clipboard.readText()")
    need9 = ["510300", "回测摘要", "近 12 个月", "区间：", "个交易日", "胜率：",
             "累计收益率：", "最大回撤：", "规则：", "历史表现不代表未来收益"]
    res["notes"]["copy9"] = all(x in clip for x in need9)
    if not res["notes"]["copy9"]:
        res["fail"].append("copy 9 elements")
    shot(p, "backtest-1440-copy-success")
    p.evaluate("()=>{navigator.clipboard.writeText=()=>Promise.reject(new DOMException('denied','NotAllowedError'));document.execCommand=()=>false}")
    p.locator("button", has_text="复制回测摘要").click(); p.wait_for_timeout(400)
    res["notes"]["copy_fail"] = "复制失败，请手动选中" in p.locator("main").inner_text()
    res["notes"]["track"] = [x for x in tracks if x and "backtest_copy" in x]

    # labs
    p.goto(BASE + "/labs/backtest-top", wait_until="load"); p.wait_for_timeout(1000)
    res["notes"]["labs_rows"] = p.locator("table tbody tr").count()
    sec = p.locator("section", has_text="近 12 个月").last
    cells = [[c.strip() for c in sec.locator("table tbody tr").nth(i).locator("td").all_inner_texts()]
             for i in range(sec.locator("table tbody tr").count())]
    trades = [int(c[-1]) for c in cells if c and c[-1].isdigit()]
    res["notes"]["labs_12m_min"] = min(trades) if trades else None
    res["notes"]["labs_noindex"] = 'name="robots" content="noindex, nofollow"' in p.content()

    for w, tag in [(393, "393"), (375, "375")]:
        c = b.new_context(viewport={"width": w, "height": 844}, locale="zh-CN")
        q = c.new_page()
        for path, name in PAGES:
            q.goto(BASE + path, wait_until="load"); q.wait_for_timeout(1200)
            res["overflow"][f"{tag}{path}"] = ov(q)
            if w == 393:
                if path != "/labs/backtest-top":
                    shot(q, f"{name}-393-default")
                if path == "/tools/backtest":
                    q.fill("#backtest-search", "510300"); q.wait_for_timeout(300)
                    q.locator("div.max-h-80 button", has_text="510300").first.click(); q.wait_for_timeout(500)
                    q.locator(grp, has_text="近 12 个月").first.click(); q.wait_for_timeout(600)
                    q.locator("button", has_text="查看逐笔与权益曲线").click(); q.wait_for_timeout(900)
                    res["overflow"]["393/backtest-detail"] = ov(q)
                    shot(q, "backtest-393-detail-curve")
                if path == "/labs/backtest-top":
                    shot(q, "labs-393-cards")
            hs = q.locator("button, a").evaluate_all(
                "els=>els.filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0})"
                ".map(e=>Math.round(e.getBoundingClientRect().height))")
            res["notes"].setdefault(f"touch_min_{tag}", {})[path] = min(hs) if hs else None
        c.close()
    b.close()

print(json.dumps(res, ensure_ascii=False, indent=1))
sys.exit(1 if res["fail"] else 0)
