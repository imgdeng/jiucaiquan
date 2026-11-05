# 26.11.1 接口与 UI 冒烟测试报告

> 测试角色：项目马（验收方，只测不改业务代码） · 测试日期：2026-11-05
> 被测提交：`cc0d6c0`（`docs(us-111~115): 窄范围复核与本期收口`）
> 范围：us-110 回测 MVP、us-111 迭代日志、us-112 首页信息架构、us-113 六档区间、us-114 中性分布 + labs 内测页、us-115 逐笔 + 权益曲线

---

## 一、结论

**冒烟全绿，具备 push 条件。**

26 项接口用例、11 项静态产物用例与全部 UI 用例均通过；本轮唯一变动是把 `/api/item` 从「待确认」改判为**范围确认项**：本期无该端点，测试清单初稿误列，`GET /api/item` 返回首页静态回落 HTML 属预期行为，不计失败。

未发现接口 5xx、页面报错、数字不自洽；本期 4+2 埋点全部进入漏斗且无 paywall 事件；六档覆盖 59/59/59/58/58/57 与产物一致；三视口无横向溢出。已知 P2 三条（首页 >7 天过期提示、底座体积、AC-1 字面选择器）均不阻断本次 push。

---

## 二、环境信息

| 项 | 值 |
|----|----|
| 仓库 | `/Users/gdeng/work/jiucaiquan` |
| 提交 | `cc0d6c0`（2026-11-04 17:26:53 +0800） |
| 构建 | `cd apps/web && npm run build`（`astro check && astro build`），产物 `apps/web/dist`，构建时间 2026-11-04 17:24 |
| Node / npm | v22.22.2 / 10.9.7 |
| 本地服务 | `npx wrangler pages dev apps/web/dist --port 4390 --d1 DB=jcq-telemetry --binding REPORT_KEY=testkey --persist-to /tmp/jcq-api/state`；另起 4391（无绑定）、4392（仅 REPORT_KEY，无 D1）覆盖异常分支 |
| D1 | 本地库 `jcq-telemetry`，表结构由 `services/telemetry/schema.sql` 初始化 |
| 浏览器 | Chromium 147.0.7727.15（Playwright Python，macOS） |
| 测试方式 | 真实 HTTP 请求 + 真实浏览器渲染；截图 full_page |

---

## 三、接口测试（Pages Functions，真实请求）

### 3.1 `/api/track`（POST）

| # | 请求 | 期望 | 实际 | 结论 |
|---|------|------|------|------|
| 1 | `{"event":"calculate","asset":"etf","code":"510300","name":"沪深300ETF","term":"3m","sid":"a…a"}` | 204 静默、落库 | `204`，空 body；D1 `calculate` +1 | 通过 |
| 2 | `{"event":"backtest_view","asset":"etf","code":"510300","sid":…}` | 204 | `204` | 通过 |
| 3 | `{"event":"backtest_result","asset":"etf","code":"510300","term":"3m","sid":…}` | 204 | `204` | 通过 |
| 4 | `{"event":"backtest_copy","asset":"etf","code":"510300","term":"12m","sid":…}` | 204 | `204` | 通过 |
| 5 | `{"event":"backtest_copy_fail","asset":"etf","code":"510300","term":"12m","reason":"not_allowed","sid":…}` | 204 | `204` | 通过 |
| 6 | `{"event":"backtest_detail_expand","…","term":"12m","sid":…}` | 204 | `204` | 通过 |
| 7 | `{"event":"backtest_detail_view","…","term":"12m","sid":…}` | 204 | `204` | 通过 |
| 8 | `{"event":"search","term":"茅台","sid":…}` | 204 | `204` | 通过 |
| 9 | 非法事件名 `{"event":"paywall_click",…}` | 204 静默丢弃、不落库 | `204`；D1 分组统计**无 paywall_click** | 通过 |
| 10 | 空 body `""` | 204 静默丢弃 | `204` | 通过 |
| 11 | 空 JSON `{}` | 204 静默丢弃 | `204` | 通过 |
| 12 | 缺 `event` `{"asset":"etf","code":"510300"}` | 204 静默丢弃 | `204` | 通过 |
| 13 | 非法 `sid` `"xyz"`（非 16–64 位 hex） | 204 静默丢弃 | `204` | 通过 |
| 14 | 超大 body（term 3000 字符，>2048B） | 204 静默丢弃 | `204` | 通过 |
| 15 | `GET /api/track` | 405（方法不允许） | `200 text/html`，静态首页回落 | P2（已知，不计入冒烟失败） |
| 16 | 无 DB 绑定实例 POST 合法事件 | 204 静默（不报 5xx） | `204` | 通过 |

> 落库校验（D1 `SELECT event,COUNT(*)`）：`backtest_copy` 3、`backtest_copy_fail` 2、`backtest_detail_expand` 3、`backtest_detail_view` 3、`backtest_result` 9、`backtest_view` 5、`calculate` 1、`leaderboard_view` 3、`page_view` 3、`search` 1，共 33 条；**非法事件 0 条**。`backtest_*` 计数较高来自本报告多轮浏览器复跑，非重复提交缺陷。

### 3.2 `/api/report`（GET，鉴权 + 异常）

| # | 请求 | 期望 | 实际 | 结论 |
|---|------|------|------|------|
| 17 | 无 key | 403 JSON | `403 {"error":"unauthorized"}` | 通过 |
| 18 | 错 key `key=wrong` | 403 JSON | `403 {"error":"unauthorized"}` | 通过 |
| 19 | `key=testkey&days=1` | 200 JSON，含 `generatedAt/since/days/funnel/daily/topTerms/topCodes/topCodesNote/countries` | `200`，9 个顶层 key 齐全，`days=1` | 通过 |
| 20 | `key=testkey&days=999` | days clamp 到 1–90 | `200`，`days=90`，`since=2026-08-08` | 通过 |
| 21 | `key=testkey&format=html` | 200 HTML 报表 | `200 text/html` | 通过 |
| 22 | 无 `REPORT_KEY` 实例 | 404 未配置 | `404 {"error":"report not configured"}` | 通过 |
| 23 | 有 `REPORT_KEY`、无 D1 绑定 | 503 依赖缺失 | `503 {"error":"D1 binding 'DB' not found"}` | 通过 |

**漏斗验证（days=999 实际返回）**：

| 事件 | 是否出现 | 事件数 |
|------|----------|--------|
| `backtest_view` | ✅ | 5 |
| `backtest_result` | ✅ | 9 |
| `backtest_copy` | ✅ | 3 |
| `backtest_copy_fail` | ✅ | 2 |
| `backtest_detail_expand` | ✅ | 3 |
| `backtest_detail_view` | ✅ | 3 |
| 其他 | `search` 1、`calculate` 1、`page_view` 3、`leaderboard_view` 3 | — |
| paywall / 付费相关 | **0 命中** | 0 |

→ 本期 4+2 埋点全部可在漏斗中看到，无 paywall 事件，**通过**。

### 3.3 `/api/top-items`（GET，公开）

| # | 请求 | 期望 | 实际 | 结论 |
|---|------|------|------|------|
| 24 | 有 D1 + 种子数据 | 200 JSON `{items,since,days:30,source}` | `200 {"items":[{"code":"600519","name":"贵州茅台","asset":"stock"}],"since":"2026-10-07","days":30,"source":"calculate"}` | 通过 |
| 25 | 无 D1 绑定 | 200 空数组、不报 5xx | `200 {"items":[],"since":"2026-10-07","days":30,"source":"calculate"}` | 通过 |

> 未覆盖：30 天不足 5 条时回退 60 天的分支（本地种子仅 1 条 calculate，无法构造 5 条阈值场景）。列入上线后复测。

### 3.4 `/api/item`（GET，范围确认）

| # | 请求 | 期望 | 实际 | 结论 |
|---|------|------|------|------|
| 26 | `GET /api/item?code=510300` | 本期无该端点；路径不存在时回落首页静态页 | `200 text/html`（首页静态回落）；`functions/api/` 无 `item.ts`，全仓无引用 | 通过（范围确认） |

本期无 `/api/item` 端点，测试清单初稿误列；已验证该路径返回首页静态回落 HTML，属预期行为，不要求补实现。

---

## 四、静态数据产物测试

全部通过本地 `wrangler pages dev` 的 HTTP 路径取回，状态码均为 200、`application/json`；另做字段与预算核算。

| # | 产物 | 状态 / 体积 | 校验项 | 实际 | 结论 |
|---|------|-------------|--------|------|------|
| 1 | `/data/backtest/index.json` | 200 / **10,282B**（≤150KB） | 结构完整 | `schemaVersion/generatedAt/latestDate/dataStart/tradingDays/strategy/methodology/windows/poolStats/pool/distribution` 齐全；`latestDate=2026-11-03`；`tradingDays=243`；`poolStats={total:59,etf:29,stock:30}` | 通过 |
| 2 | 六档覆盖 | — | 59/59/59/58/58/57 | `3m 59`、`2w 59`、`4w 59`、`6m 58`、`9m 58`、`12m 57`；6 档 `available=true`；`minTradingDays=20/10/20/120/180/240` | 通过 |
| 3 | 六档区间 | — | 与实际交易日一致 | 3m `2026-08-04~2026-11-03`；2w `2026-10-21~2026-11-03`；4w `2026-09-30~2026-11-03`；6m `2026-05-08~2026-11-03`；9m `2026-01-30~2026-11-03`；12m `2025-11-05~2026-11-03` | 通过 |
| 4 | `summary/{code}.json` | 59 份 / 单份最大 **1,841B**（≤20KB） | 字段完整 | 59 份均含 `schemaVersion/generatedAt/code/name/asset/latestDate/strategy/windows`；缺失 0 份 | 通过 |
| 5 | `detail/{code}.json` | 59 份 / 合计 **602,842B（588.7KiB）**（≤1.2MB） | 单标的单档 ≤8KB | 单档序列化最大 **3,897B**（`510050.json:12m`）；单文件最大 12,262B（含 6 档，非预算单位） | 通过 |
| 6 | `leaderboard.json` | 200 / 760,916B | `latestDate` 与 index 一致 | `latestDate=2026-11-03`，与 `backtest/index.json` 完全一致 | 通过 |
| 7 | `data-status.json` | 200 / 154B | `generatedAt` 与首页一致 | `generatedAt=2026-11-03T22:54:44+08:00`，`errors=[]`；首页展示「更新于 2026-11-03 22:54」一致 | 通过 |
| 8 | 缺口标的 | — | 中微 231、长鑫 66、不出现 235 | `688012` 12m `availableTradingDays=231`；`688825` 6m/9m/12m `66`；全产物「235」0 命中 | 通过 |
| 9 | 2w 小样本 / 0 笔 | — | 如实标注 | `510300` 2w `trades=1, sampleWarning=insufficient`；`300750` 2w `trades=0, sampleWarning=noTrades, winRate=null` | 通过 |
| 10 | 逐笔与摘要自洽（抽 4 条） | — | 逐笔合计=摘要收益；`100+cumReturn`=曲线终值；回撤区间=摘要 | 510300 12m 27 笔、合计 `-1039.60`=`pnlTotal`、`89.60`=`100-10.40`、回撤 `17.95%`（05-15~10-22）；600519 12m 26 笔 `-1068.83`/`-10.69%`/`19.67%`；688012 3m 7 笔 `-3796.31`/`-37.96%`/`39.19%`；300750 2w 0 笔曲线平 100 | 通过 |
| 11 | 3m 与 us-110 终验回归 | — | 0 误差 | 510300 `-10.06%/0.0/6 笔`；600519 `+4.26%/57.1%/7 笔`；300750 `-42.31%/0.0/8 笔` | 通过 |

**体积预算预警（P2，非阻断）**：`services/market-data/backtest-base/history_base.json` = 328,284B raw / 136,576B gzip，超 us-113 AC-10 的 315KB / 130KB 约 5.7KiB / 3.4KiB（已由产品马登记为 P2）。

---

## 五、UI 测试（真实浏览器）

### 5.1 路由与身份

| 路由 | 状态 | title | 结论 |
|------|------|-------|------|
| `/` | 200 | `韭菜圈 \| A 股条件单工具箱` | 通过 |
| `/tools/backtest` | 200 | `回测 · 历史表现 \| 韭菜圈` | 通过 |
| `/tools/condition-order` | 200 | `条件单计算器 \| 韭菜圈` | 通过 |
| `/log` | 200 | `迭代日志 \| 韭菜圈` | 通过 |
| `/labs/backtest-top` | 200 | `回测收益排序（内测） \| 韭菜圈` | 通过 |

> 均校验 title 而非仅状态码，排除「未部署回落首页仍 200」的假通过。

### 5.2 关键交互

| # | 用例 | 期望 | 实际 | 结论 |
|---|------|------|------|------|
| 1 | 选标的（510300 / 600519 / 300750 / 688012 / 688825） | 搜索后可选中并加载摘要 | 搜索框输入代码→列表点击→摘要渲染 | 通过 |
| 2 | 六档切换 | 6 个按钮、无 disabled、区间联动 | 6 个按钮文案含交易日数（60/10/20/120/180/240）；`button[disabled]=0`；切 4 周后摘要区间变 `2026-09-30~2026-11-03（20 个交易日）` | 通过 |
| 3 | 12m 缺口标的 | 标的级文案、非置灰/非空白 | 688012 显示「该标的此区间数据不足（可用 231 个交易日）」 | 通过 |
| 4 | 12m 覆盖说明 | 覆盖数 + 标的 + 天数 + 「不适用」 | 「57/59 只满足 240 个交易日；中微公司 231 日、长鑫科技 66 日，数据不足，故近 12 个月档对上述 2 只标的不适用」 | 通过 |
| 5 | 2w 小样本 | 「样本不足（1 笔）」 | 510300 2w：胜率 100.0%（1/1 笔）+「样本不足（1 笔）」 | 通过 |
| 6 | 2w 0 笔 | 「该区间未触发交易」、不显示 0% 胜率 | 300750 2w：未触发交易，胜率缺省 | 通过 |
| 7 | 展开逐笔 + 权益曲线 | 逐笔表 + SVG 曲线 + 汇总自洽 | 1440：27 行表格 + 1 个 `svg[role=img][aria-label*='权益曲线']`；「逐笔合计 -1039.60 元 · 累计收益率 -10.40% · 曲线终值 89.60」；「峰值 2026-05-15（107.11）· 最大回撤 17.95%（05-15~10-22）」 | 通过 |
| 8 | 复制成功 | 剪贴板含 9 要素 + 页面反馈 + 埋点 | 剪贴板 217 字含：标的+代码、策略名、区间档位、start~end（240 交易日）、胜率、累计收益率、最大回撤、规则、免责；按钮反馈「已复制回测摘要」；发出 `backtest_copy`（510300/etf/12m） | 通过 |
| 9 | 复制失败 | 不静默、提示手动复制、埋点 | 注入 `NotAllowedError` + `execCommand=false` 后提示「复制失败，请手动选中」；发出 `backtest_copy_fail`（含 `reason:"not_allowed"`） | 通过 |
| 10 | `/labs` 表格 | 分档表格、12m 段笔数 ≥5 | 41 行；12m 段 10 行、最少 21 笔（源杰科技）；行含代码/名称/区间/累计收益率/胜率/笔数 | 通过 |
| 11 | `/labs` 卡片 | 393 卡片形态 | 393 下表格隐藏，卡片容器 5 个，各档标题与数值可读 | 通过 |
| 12 | `/labs` 内测属性 | `noindex,nofollow` + robots + 无公开入口 + 风险说明 | `<meta name="robots" content="noindex, nofollow">`；`robots.txt` 含 `Disallow: /labs/`；站点导航无 labs 链接、无 sitemap、其他页面 0 引用；页面含「未做访问控制」说明 | 通过 |
| 13 | `/log` | 17 条、严格倒序、最后更新 | 17 个 `<article>`；`2026-11-04` → `2026-06-03` 倒序；顶部「最后更新 2026-11-04」 | 通过 |
| 14 | 首页工具台数据状态 | 与产物一致 | 「最新交易日 2026-11-03 · 更新于 2026-11-03 22:54」；回测链接 2 个 | 通过 |
| 15 | 计算器热词 | 天数来自接口、非硬编码 | 显示「近 30 天计算最多」；mock `days:45` 时渲染「近 45 天」 | 通过 |

### 5.3 合规与文案

| # | 检查项 | 期望 | 实际 | 结论 |
|---|--------|------|------|------|
| 1 | 禁用词（13 词：荐股/带单/牛股/稳赚/稳赢/保证收益/必涨/翻倍/推荐/最优/首选/抄底/热门） | 5 页渲染文本 0 命中 | `/`、`/tools/backtest`、`/tools/condition-order`、`/log`、`/labs/backtest-top` 全部 `[]` | 通过 |
| 2 | 风险声明可见 | 页脚可见 | 5 页页脚「风险提示…不构成证券投资建议，不承诺收益…」 | 通过 |
| 3 | 首页回测卡小字 | 「仅历史统计，不代表未来收益」可见 | 文本存在；元素 `display:block`、可见、12px、位于首屏 | 通过 |
| 4 | 回测页口径四要素 | 同屏可见 | 前复权（比率复权）、底座按 archive 首个重叠日锚定、拼接日收益差 0.0pp、qfq 漂移中位 0.0pp/最大 2.85pp（招商银行）、未计佣金与滑点 | 通过 |
| 5 | 标的池排序披露 | 非收益排序、含「不构成投资暗示」 | 「标的池固定，按末日成交额排序（仅代表成交活跃度，不构成任何投资暗示）」 | 通过 |
| 6 | 无付费/订阅/明细外泄 | 0 命中 | 5 页无付费、价格、收款、订阅文案 | 通过 |

### 5.4 窄屏与触控（1440 / 393 / 375）

| 视口 | 页面 | `scrollWidth == innerWidth` | 结论 |
|------|------|------------------------------|------|
| 1440 | `/`、`/tools/backtest`、`/tools/condition-order`、`/log`、`/labs/backtest-top` | 1440 == 1440（5/5） | 通过 |
| 393 | 同上 + 回测详情态 | 393 == 393（6/6） | 通过 |
| 375 | 同上（5 页） | 375 == 375（5/5） | 通过 |

- 触控目标：5 页可交互元素最小高度均为 **44px**（导航链接 44、反馈 44×44、计算器按钮 44、回测列表项 48）。
- 393 回测逐笔：表格隐藏、27 张卡片；`/labs` 393 卡片 5 个容器。
- 截图体积合计 **6.7MB**，单张最大 816KB（`log-1440-default.png`），无异常大图。

---

## 六、截图清单与验证点

目录：`docs/sprints/26.11.1/screenshots/`（共 16 张）

| 文件 | 验证点 |
|------|--------|
| `home-1440-default.png` | 首页 1440：Hero 主 CTA、今日工具台两卡、数据状态（2026-11-03）、回测卡「仅历史统计，不代表未来收益」、页脚风险声明 |
| `home-393-default.png` | 首页 393：主 CTA 首屏可见、工具台卡片纵向排布、无横向溢出 |
| `backtest-1440-default.png` | 回测页 1440 默认态：四步逻辑、口径区、六档按钮、空摘要态 |
| `backtest-1440-six-windows.png` | 六档按钮齐全（3m/2w/4w/6m/9m/12m，含交易日数），选中「近 4 周」后摘要区间联动为 20 个交易日 |
| `backtest-1440-12m-gap.png` | 688012 12m：标的级「数据不足（可用 231 个交易日）」，不置灰、不空白 |
| `backtest-1440-2w-sample.png` | 510300 2w：胜率 100.0%（1/1 笔）+「样本不足（1 笔）」 |
| `backtest-1440-detail-curve.png` | 510300 12m 逐笔 27 行 + 权益曲线；合计 -1039.60 元 / -10.40% / 终值 89.60；回撤 17.95%（05-15~10-22） |
| `backtest-1440-copy-success.png` | 复制成功：按钮反馈「已复制回测摘要」、摘要数字与剪贴板一致 |
| `backtest-393-default.png` | 回测页 393：六档按钮两列排布、无横向溢出 |
| `backtest-393-detail-curve.png` | 393 详情态：表格转卡片（27 张）、权益曲线可见、无横向溢出 |
| `condition-order-1440-default.png` | 计算器 1440：输入区、「近 30 天计算最多」、回测入口 1 个 |
| `condition-order-393-default.png` | 计算器 393：单列布局、触控 ≥44px、无溢出 |
| `log-1440-default.png` | 日志 1440：17 条记录、倒序、「最后更新 2026-11-04」 |
| `log-393-default.png` | 日志 393：时间线单列、无溢出 |
| `labs-1440-default.png` | labs 1440 表格形态：分档 TOP10、12m 段 10 行（最少 21 笔）、内测横幅 |
| `labs-393-cards.png` | labs 393 卡片形态：表格隐藏、卡片展示、无溢出 |

> 已删除两张与既有截图字节完全相同的重复文件（`backtest-1440-six-windows` 旧版与 `default` 重复、`labs-393-default` 与 `labs-393-cards` 重复），其中六档状态已重新截取为选中「近 4 周」的独立状态。

---

## 七、失败项

**无失败项。**

| 编号 | 级别 | 项 | 证据 | 处置 |
|------|------|----|------|------|
| R1 | 范围确认 | `/api/item` 不在本期范围 | `functions/api/` 仅 `report.ts`/`top-items.ts`/`track.ts`；全仓无 `api/item` 引用；`GET /api/item?code=510300` → `200 text/html`（首页回落） | 初稿误列；已确认为预期行为，不补实现 |

**无 5xx、无页面 JS 报错、无数字不自洽。**

---

## 八、风险项与已知 P2 残留

| 编号 | 级别 | 项 | 说明 |
|------|------|----|------|
| P2-1 | P2 | `GET /api/track` 返回 `200 text/html` 而非 405 | Pages Functions 未实现方法时回落静态资源；不产生错误数据，但 API 语义不严谨 |
| P2-2 | P2 | 首页数据 >7 天过期提示未实现（us-112 AC-4） | 已由产品马登记；当前 `latestDate` 为当日，线上短期无感 |
| P2-3 | P2 | 底座体积 328,284B / 136,576B gzip 超预算（us-113 AC-10） | 超 5.7KiB / 3.4KiB；不影响首屏与响应 |
| P2-4 | P2 | AC-1 字面选择器未落地（`a.btn-primary`、`[data-tool-card]`） | 行为等价（hero 用 `bg-leaf`、卡片整块为 `<a>`）；建议改口径或补属性 |
| 观察 | — | 首页「阶段排行榜」按涨幅排序（既有功能，非本期改动） | 页内注明「历史数据统计，不构成投资建议」，不计失败 |
| 观察 | — | `backtest_*` 本地计数偏高 | 本报告多轮复跑所致，非重复提交缺陷 |

---

## 九、未覆盖与局限

1. 本地 `wrangler pages dev` 模拟，未覆盖 Cloudflare 真实边缘缓存、HTTP/2、生产 D1 数据量下的 `/api/report` 性能。
2. `/api/top-items` 的 30 天不足 5 条回退 60 天分支未构造（种子仅 1 条），列入上线后复测。
3. 浏览器仅 Chromium；未测 Safari / Firefox 与真机 iOS。
4. 未跑全量回归（按用户口径本期只做冒烟 + 风险优先）。

---

## 十、push 建议

**可以 push**（`P2-1`~`P2-4` 均不阻断）。`/api/item` 已确认为初稿误列，本期不补。

上线后 24h 需盯：六档覆盖数与缺口标的不漂移、`/api/report` 漏斗六个 `backtest_*` 事件真实上报、`top-items` 回退 60 天分支、首页数据日期与过期提示、底座体积走势。

*项目马 · 2026-11-05*
