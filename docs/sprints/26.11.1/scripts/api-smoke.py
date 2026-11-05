#!/usr/bin/env python3
"""26.11.1 接口冒烟：Pages Functions + 静态产物。

前置：
  cd /Users/gdeng/work/jiucaiquan
  npx wrangler pages dev apps/web/dist --port 4390 \
    --d1 DB=jcq-telemetry --binding REPORT_KEY=testkey --persist-to /tmp/jcq-api/state

用法：
  python3 docs/sprints/26.11.1/scripts/api-smoke.py
  BASE=http://127.0.0.1:4390 KEY=testkey python3 ...
"""
import json, os, glob, sys, urllib.request, urllib.error

BASE = os.environ.get("BASE", "http://127.0.0.1:4390")
KEY = os.environ.get("KEY", "testkey")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
DATA = os.path.join(ROOT, "apps/web/public/data")
rows = []

def http(method, path, body=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers.get("content-type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read()

def case(name, method, path, body, expect_status, check=None):
    st, ct, raw = http(method, path, body)
    ok = st == expect_status
    detail = ""
    if check:
        try:
            js = json.loads(raw)
            ok = ok and check(js)
            detail = "JSON"
        except Exception:
            ok = False
            detail = "non-JSON"
    rows.append((name, f"{method} {path}", expect_status, st, "PASS" if ok else "FAIL"))
    return st, raw

sid = "a" * 32
ok_events = ["calculate", "backtest_view", "backtest_result", "backtest_copy",
             "backtest_copy_fail", "backtest_detail_expand", "backtest_detail_view", "search"]
for ev in ok_events:
    case(f"track {ev}", "POST", "/api/track",
         {"event": ev, "asset": "etf", "code": "510300", "term": "12m", "sid": sid}, 204)
case("track 非法事件", "POST", "/api/track", {"event": "paywall_click", "sid": sid}, 204)
case("track 空 body", "POST", "/api/track", "", 204)
case("track 空 JSON", "POST", "/api/track", "{}", 204)
case("track 缺 event", "POST", "/api/track", {"asset": "etf", "sid": sid}, 204)
case("track 非法 sid", "POST", "/api/track", {"event": "calculate", "sid": "xyz"}, 204)
case("track 超大 body", "POST", "/api/track", {"event": "calculate", "term": "x" * 3000}, 204)

case("report 无 key", "GET", "/api/report", None, 403,
     lambda j: j.get("error") == "unauthorized")
case("report 错 key", "GET", "/api/report?key=wrong", None, 403,
     lambda j: j.get("error") == "unauthorized")
_, rep = case("report days=1", "GET", f"/api/report?key={KEY}&days=1", None, 200,
              lambda j: j["days"] == 1 and set(j) >= {"funnel", "daily", "topTerms", "countries"})
_, rep90 = case("report days=999 clamp", "GET", f"/api/report?key={KEY}&days=999", None, 200,
                lambda j: j["days"] == 90)
case("report html", "GET", f"/api/report?key={KEY}&format=html", None, 200)

funnel = [x["event"] for x in json.loads(rep)["funnel"]]
need = ["backtest_view", "backtest_result", "backtest_copy", "backtest_copy_fail",
        "backtest_detail_expand", "backtest_detail_view"]
rows.append(("report 漏斗 4+2 事件", "GET /api/report", "含 6 事件", 
             "含 %d/6" % sum(e in funnel for e in need),
             "PASS" if all(e in funnel for e in need) else "FAIL"))
rows.append(("report 无 paywall", "GET /api/report", "0 命中",
             "0" if not any("paywall" in e for e in funnel) else "有",
             "PASS" if not any("paywall" in e for e in funnel) else "FAIL"))

case("top-items", "GET", "/api/top-items", None, 200,
     lambda j: "items" in j and j["days"] == 30 and "source" in j)

# 静态产物
idx = json.load(open(f"{DATA}/backtest/index.json"))
lib = json.load(open(f"{DATA}/leaderboard.json"))
st = json.load(open(f"{DATA}/data-status.json"))
cov = [w["availableSymbols"] for w in idx["windows"]]
rows.append(("index 覆盖六档", "local", "59/59/59/58/58/57", "/".join(map(str, cov)),
             "PASS" if cov == [59, 59, 59, 58, 58, 57] else "FAIL"))
rows.append(("index/leaderboard latestDate", "local", "一致", 
             f"{idx['latestDate']} / {lib['latestDate']}",
             "PASS" if idx["latestDate"] == lib["latestDate"] else "FAIL"))
rows.append(("index poolStats", "local", "59(29+30)", str(idx["poolStats"]),
             "PASS" if idx["poolStats"]["total"] == 59 else "FAIL"))
sm = glob.glob(f"{DATA}/backtest/summary/*.json")
rows.append(("summary 份数/最大体积", "local", "59 份 ≤20KB",
             f"{len(sm)} / {max(os.path.getsize(f) for f in sm)}B",
             "PASS" if len(sm) == 59 and max(os.path.getsize(f) for f in sm) <= 20 * 1024 else "FAIL"))

# /api/item 不存在：阻断候选
st_i, ct_i, _ = http("GET", "/api/item?code=510300")
rows.append(("/api/item", "GET /api/item", "200 JSON", f"{st_i} {ct_i.split(';')[0]}",
             "FAIL" if ct_i.startswith("text/html") else "PASS"))

width = max(len(r[0]) for r in rows)
for r in rows:
    print(f"{r[0]:<{width}}  {r[1]:<34} 期望 {r[2]:<12} 实际 {r[3]:<12} {r[4]}")
print("\nFAIL:", sum(r[4] == "FAIL" for r in rows), "/", len(rows))
sys.exit(1 if any(r[4] == "FAIL" for r in rows) else 0)
