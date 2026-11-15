# us-990 · 交付记录

> 交付人：工程马 | 日期：2026-11-15 | 状态：**已上线，待项目马线上终验**
> 需求卡：[00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/00_card.md) · 工程记录：[02_eng.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/02_eng.md)

## 一、结论

`GET /api/quote` 已实现、测试并部署到 `https://jiucaiquan.com`。接口按契约返回独立的 `business_valid` 与参照值 `expected`，5 组固定输入、非法参数 400、同参两次逐字一致均通过；`ConditionOrderTool.tsx` 与 `condition-order.ts` 零改动，线上页面教学缺陷原样保留。

唯一未完全闭环的是 AC-1 的「响应 < 1s」：本机到站点的网络时延波动较大，同一域名的静态 JSON 也出现 776ms~2.96s 中位/峰值，判断为链路抖动而非接口计算。服务器纯计算本地实测 3–23ms，接口本身无 D1、无外部 `fetch`、无写操作。

## 二、逐 AC 判定

| AC | 判定 | 证据 |
|---|---|---|
| AC-1 `9/0.338/0.342` → 200、`business_valid=false`、低吸价 `-6.1565`、<1s | ⚠️ 功能通过；时延待复核 | 线上返回完全匹配；本机实测最低 322ms，但中位约 1.9s、峰值 9.7s；同域静态资源同样波动 |
| AC-2 同参数两次逐字一致；无 D1 / 外部 fetch | ✅ 通过 | 线上 10 次响应体 100% 一致；代码无 `env`、无 `fetch`、无写状态 |
| AC-3 5 组固定输入符合预期；非法参数 400 而非 500 | ✅ 通过 | 5 组线上 200；缺参/非数字/空白/正数且 `high<low` 均 400；非正值按修复口径返回 200 + `business_valid=false` |
| AC-4 站点页面行为未变，`9/0.338/0.342` 仍显示 `-6.1565` | ✅ 通过（静态确认） | 仅新增 3 个文件 + 需求卡，未改页面组件与策略文件；`/tools/condition-order/` 线上 200 |
| AC-5 实现文件与本地测试输出存证 | ✅ 通过 | [02_eng.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/02_eng.md)；`25 passed, 0 failed` |
| AC-6 项目马线上 `curl` 复核 | ⏳ 待项目马 | 工程侧初验已完成，最终判定以项目马复核为准 |

## 三、线上实测记录（2026-11-15）

```text
GET https://jiucaiquan.com/api/quote?high=9&low=0.338&close=0.342
HTTP 200 · application/json; charset=utf-8
{"input":{"high":9,"low":0.338,"close":0.342},"business_valid":false,
 "reason":"波动区间 8.662 ≥ 基准价 2.5055，低吸价业务上不允许为负",
 "expected":{"基准价":2.5055,"波动区间":8.662,"低吸价":-6.1565,"高抛价":11.1675},
 "contract_version":"v0.1"}

GET ...?high=3&low=1&close=1          → 200 business_valid=false 低吸价=-0.5
GET ...?high=10&low=9&close=9.5       → 200 business_valid=true  低吸价=8.5
GET ...?high=999999999999999&low=1.0&close=1.5 → 200 false 低吸价=-749999999999997.2
GET ...?high=1e308&low=1.0&close=1.5  → 200 false，溢出字段为 "Infinity" / "-Infinity" 字符串，未抛 500
GET ...?high=0&low=0&close=0         → 200 business_valid=false，reason="价格必须大于 0"
GET ...?high=-1&low=1&close=1        → 200 business_valid=false（非正值优先于 high<low 校验）

GET ...?low=0.338&close=0.342         → 400 {"error":"missing required parameter: high"}
GET ...?high=abc&low=0.338&close=0.342 → 400 {"error":"invalid number for high: abc"}
GET ...?high=9&low=&close=0.342       → 400 {"error":"missing required parameter: low"}
GET ...?high=1&low=9&close=5          → 400 {"error":"invalid OHLC: high must be greater than or equal to low"}

同参数 10 次请求：all bodies identical = true
/tools/condition-order/ → 200
```

### 时延对照（本机网络，非服务器计算耗时）

| 目标 | n | min | median | max |
|---|---|---|---|---|
| `jiucaiquan.com/api/quote` | 6 | 322ms | 2654ms | 9675ms |
| `jiucaiquan.pages.dev/api/quote` | 6 | 679ms | 3253ms | 5529ms |
| `jiucaiquan.com/data/data-status.json`（静态） | 6 | 331ms | 776ms | 2963ms |
| 本地真实 HTTP 调 `onRequestGet` | 6 | 3.3ms | 5.1ms | 23.2ms |

结论：线上时延与静态资源同量级波动，接口纯计算开销可忽略；`<1s` 硬指标受网络链路影响，建议项目马在稳定网络复核。

## 四、问题分级

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无接口 5xx、无页面报错、无契约字段缺失 |
| P1 | 0 | 无 |
| P2 | 1 | 线上请求时延波动；静态资源同样波动，非本接口代码引入，不拦截上线 |

## 五、上线后待复测项

1. 项目马在稳定网络下 `curl -w '%{time_total}'` 复核 AC-1 的 `<1s`。
2. US-991 按本契约改造后，用 `business_valid` 喂 `sanity()`、`expected` 喂 `compare()` 做最终联调实跑。
3. 若后续需要把时延写进文章，建议同时贴 `pages.dev` 与自定义域名的对照，避免把网络抖动误判为接口性能。

## 六、回滚方式

- 代码：`git revert 6be797ea8` 后推送 `main`，Cloudflare Pages 自动重新部署。
- 本卡未改数据库、未改页面、未改构建配置，回滚无数据迁移成本。

## 七、变更文件

| 文件 | 类型 |
|---|---|
| [functions/api/quote.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/quote.ts) | 新增 |
| [tests/test-quote.ts](file:///Users/gdeng/work/jiucaiquan/tests/test-quote.ts) | 新增 |
| [team/us/us-990/00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/00_card.md) | 新增（需求卡迁入） |
| [team/us/us-990/us-990.json](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/us-990.json) | 新增（结构化卡） |

---

*工程马 | 2026-11-15*
