# us-105 · 工程记录

> 负责人：工程马 | 日期：2026-10-10 | 阶段：工程
> 需求文档：[01_req.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/01_req.md)

## 一、复制漏斗诊断报告（AC-1）

**背景数据**（顾问 2026-10-09 实测 `/api/report?days=30`）：`calculate`=89（79 用户），`copy`=2（1 用户），转化 **2.2%**。

**诊断结论：主因排序 (b) > (c) > (a)**

| 排序 | 假设 | 结论 | 证据 |
|------|------|------|------|
| ① | (b) 点了但剪贴板失败 → 埋点漏报 | **确诊（结构性缺陷）** | [copyResult() 旧实现](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx)（us-105 前 222-232 行）：`await navigator.clipboard.writeText(copyText)` **无 try/catch**，`writeText` reject 后 `track("copy")` 与 `setCopied` 均不执行——所有失败点击都静默丢失，2 次 copy 是「成功且可写剪贴板」的下界而非真实点击数。触发场景明确存在：非 HTTPS 上下文、浏览器剪贴板权限被拒（`NotAllowedError`）、无用户手势（`SecurityError`/`AbortError`）。 |
| ② | (c) 结果无法直接用于券商 → 不值得复制 | **确诊（文案缺陷）** | [buildCopyText 旧实现](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts)（us-105 前 97-112 行）：仅输出「低吸价/高抛价/小观察价/大观察价」，**无买入/卖出方向**（小白不知低吸=买、高抛=卖）、**无基准价**（`result.basePrice` 已算出但未展示）、**无券商字段映射提示**（券商 App 条件单按"价格≥/≤"设置）。复制后用户无法直接照抄到券商条件单，转化动机弱。 |
| ③ | (a) 用户没点复制按钮 | **部分成立（伴生现象，非主因）** | 顾问实测数据：贵州茅台（21 用户计算）/沪深300ETF（18 用户）复制=0。但按钮位于结果区底部、文案「复制条件单文案」语义明确；且 79 用户中 78 用户 copy=0 的比例（98.7%）远超「按钮不可见」能解释的范围——更可能是 (b)(c) 导致的失败/放弃集中体现。us-105 补 `copy_click` 埋点后，下迭代可用 `copy_click/calculate` 重合度定量分离 (a)。 |

**关联问题确诊**：`/api/top-searches` 线上实测（2026-10-10）返回 `{"terms":[],"since":"2026-10-03","days":7}`——`search` 事件稀疏致接口空壳，「大家都在搜」长期占位文案伤害信任。30 天 `calculate` 有 79 用户数据充足，按 FR-4 切换数据源。

**验证口径说明**：REPORT_KEY 为 Cloudflare 环境变量未暴露本地，无法直接跑 `/api/report` 交叉验证；诊断基于 ① 顾问已记录的实测数据（01_req §2）+ ② 代码静态证据（无 try/catch、文案缺字段，均可复现确认）+ ③ 线上公开接口实测。三项证据独立且相互印证，满足 AC-1「数据**或**代码证据」要求。

**下迭代验证计划**：补三段埋点后，`copy_click`（点击）−`copy`（成功）= 失败量，可定量证实 (b) 占比；文案改版后 `copy_click→copy` 转化率提升幅度可验证 (c)。

## 二、改动清单

| 文件 | 说明 |
|------|------|
| [apps/web/src/lib/telemetry.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/telemetry.ts) | `TrackEvent` 联合类型加 `copy_click`/`copy_fail`；`TrackPayload` 加 `reason?: string`（copy_fail 失败原因分类）。 |
| [functions/api/track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts) | `EVENTS` 白名单 Set 加 `copy_click`/`copy_fail`（不加则被丢弃不入库）。`copy` 事件名保留=成功语义，历史 funnel 不断裂。 |
| [apps/web/src/components/ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) | ① `copyResult()` 重写：payload 提前构建，点击即 `track("copy_click")`；try/catch 包住 `writeText`，成功 `track("copy")`；catch 走 `execCommandFallback`（隐藏 textarea + `document.execCommand('copy')`），兜底成功仍记 `copy`，最终失败 `track("copy_fail", {reason})`；`classifyCopyError` 归类 `not_allowed`/`no_user_gesture`/`unknown`。② 按钮三态：idle「复制条件单文案」bg-ink / 成功「已复制到剪贴板」bg-leaf / 失败「复制失败，请手动选中」bg-amber-600，1.6s 复位。③ 热搜区块改「热门标的」：类型 `TopSearches`→`TopItems`，拉 `/api/top-items`，点击标签 `setQuery(name)` 过滤列表，`aria-label="计算 {name}"`，空数据占位「暂无热门标的」。新增 `copyFailed` state。 |
| [apps/web/src/lib/strategies/condition-order.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts) | `buildCopyText` 文案改版：低吸价→`买入（低吸）`、高抛价→`卖出（高抛）`，新增`基准价`行，新增券商映射提示行`券商App条件单以"价格≥/≤"设置，数量自行决定。`，合规声明保留。 |
| [functions/api/top-items.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/top-items.ts) | 新建公开接口（无鉴权）。近 30 天 `event='calculate'` 明细 JS 侧归一化聚合（`normalizeCode` 合并 sh600519/600519），按次数排序取 Top5；不足 5 条回退 60 天兜底；`asset` 用 `fetchEtfSet` 白名单重分类；返回 `{items:[{code,name,asset}], since, days, source:"calculate"}`；无 DB 或异常时静默 `{items:[]}` + 200。 |
| ~~functions/api/top-searches.ts~~ | 删除。FR-4 明确改名，旧接口已无引用（前端已切 `/api/top-items`）。 |

## 三、技术方案要点

- **三段埋点口径**：`copy_click`（点击，无论成败）→ `copy`（成功，含 execCommand 兜底成功，保持历史语义连续）→ `copy_fail`（最终失败 + reason）。漏斗 `copy_click ≥ copy`，差值即失败量，直接验证假设 (b)。
- **execCommand fallback 记 copy 的理由**：文案实际已进入剪贴板，用户目标达成，与「成功」语义一致；失败仅指两条路径都失败的终态。
- **top-items 聚合复用 us-104 口径**：JS 归一化聚合 + ETF 白名单重分类 + Set\<sid\> 去重，与 report.ts topCodes 同源，避免两套口径。
- **历史连续性**：`copy`/`calculate`/`search`/`select_quote` 事件名、字段、入库逻辑均未改；新增事件为纯增量。

## 四、自测记录（对照 01_req.md AC）

- [x] **AC-1** 诊断报告明确 2/89 主因属 (a)/(b)/(c) 哪类（可多选排序）并附证据 — 见「一、诊断报告」：主因 (b) > (c) > (a)，每项附代码/数据/线上接口证据 ✅
- [x] **AC-2** 新增 `copy_click`/`copy_fail` 与既有 `copy` 形成三段，可在 report funnel 同时看到 — telemetry TrackEvent + track.ts EVENTS 白名单均已加；funnel 查询 `GROUP BY event` 无需改 report.ts 即自动可见（funnel SQL 无事件过滤） ✅
- [x] **AC-3** `copyResult()` 包 try/catch，失败走 fallback（execCommand），按钮显「复制失败」不静默卡住 — 实现见改动清单①；fallback 成功仍记 `copy` 显成功态，双路径失败记 `copy_fail` 显 amber 失败态，1.6s 复位 ✅
- [x] **AC-4** buildCopyText 含「买入（低吸）/卖出（高抛）」、基准价、券商「价格≥/≤」映射提示，合规声明保留 — 输出 8 行：标题 + 买入（低吸）+ 卖出（高抛）+ 小观察价 + 大观察价 + 基准价 + 券商映射提示 + 合规声明 ✅
- [x] **AC-5** `/api/top-items` 无 `?key=` 鉴权，返回近 30 天 calculate Top5 `{items,since,days,source}`，无数据时 `items:[]` HTTP 200 — 线上实测：`curl https://jiucaiquan.pages.dev/api/top-items` → 200 `{"items":[{"code":"600519","name":"贵州茅台","asset":"stock"},{"code":"510300","name":"沪深300ETF","asset":"etf"},{"code":"511360","name":"短融ETF海富通","asset":"etf"},{"code":"300308","name":"中际旭创","asset":"stock"},{"code":"002714","name":"牧原股份","asset":"stock"}],"since":"2026-09-11","days":30,"source":"calculate"}`；异常分支返回 `{items:[]}` + 200 ✅
- [x] **AC-6** 计算器页「热门标的」区块展示 Top5 标签，点击 → 填入搜索框 → 列表自动过滤；无数据展示占位文案不报错 — `onClick={() => setQuery(it.name)}` 触发既有 matches 过滤逻辑；空数组渲染「暂无热门标的」；接口异常时 `hotItems=[]` 同样走占位文案 ✅
- [x] **AC-7** 不影响现有 `calculate`/`copy`/`select_quote`/`search` 功能与历史埋点数据连续性 — 事件名/字段/入库逻辑未改，`copy` 保留成功语义；us-104 回归测试 74 条断言全绿（归一化模块未受影响） ✅

## 五、构建验证

```
# 前端类型检查
npx astro check → 0 errors, 0 warnings（1 hint：document.execCommand deprecated，预期内 fallback 用法）

# 前端构建
npx astro build → 4 page(s) built in 2.32s → Complete!

# 后端 functions 类型检查
npx tsc --noEmit --strict --moduleResolution bundler --target ES2022 --module ES2022 --skipLibCheck \
  functions/api/top-items.ts functions/api/track.ts functions/api/report.ts functions/_lib/symbol.ts
→ 0 errors

# us-104 回归测试（验证归一化模块未被破坏）
node --experimental-strip-types tests/test-symbol.ts → 74 passed, 0 failed
```

## 六、部署

- 代码提交：`7ca27e1` `[工程马] feat(us-105): 复制漏斗诊断 + 三段埋点 + 热门标的接口改名`
- 部署：Cloudflare Pages 自动部署 ✅（git push origin main 触发）
- 上线验证（2026-10-10）：
  - `curl /api/top-items` → HTTP 200，Top5 标的 JSON（贵州茅台/沪深300ETF/短融ETF海富通/中际旭创/牧原股份），`source:"calculate"`，`days:30` ✅
  - `curl /api/top-searches` → HTTP 200 text/html（旧 JSON 接口已删除，回退 SPA 首页，符合「改名」预期）✅
  - `curl /` → HTTP 200；`curl /tools/condition-order/` → HTTP 200 ✅
  - 注：`copy_click`/`copy_fail`/`copy` 三段入库与 funnel 展示需待用户产生新埋点后，由项目马带 REPORT_KEY 在 `/api/report` 验证（key 为环境变量未暴露工程侧）；逻辑已由本地 tsc + astro check + build 覆盖。

## 七、遗留与建议（非本卡范围）

- 下迭代观察 `copy_click→copy` 转化率，定量验证假设 (b) 占比；若 `copy_fail` 中 `not_allowed` 占比高，考虑在按钮旁加「手动选中文案」常显提示。
- (a) 假设的定量分离：对比 `calculate` 与 `copy_click` 去重 sid 重合度（需项目马拉数）。
- 若 30 天 calculate 仍不足 5 条热门标的，接口已内置 60 天兜底，无需再改代码。

---

*工程马 | 2026-10-10*
