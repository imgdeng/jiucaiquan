# 26.10.1 独立审计（us-104 / us-105 / us-106）

> 审计角色：审计（独立于原交付角色） | 日期：2026-11-08
> 目的：验证 [roadmap-gap-analysis.md](file:///Users/gdeng/work/jiucaiquan/docs/roadmap-gap-analysis.md#L56-L56) 对 26.10.1「部分交付」的判断，给出「现在能不能收口」的硬结论。
> 约束：未改业务代码、未 push；临时验证脚本与本地 D1 均在 `/tmp/jcq-audit/`，本地服务已停止。

---

## 〇、结论速览

| 项 | 结论 |
|----|------|
| AC 三态统计 | **通过 18 / 不通过 0 / 无法判定 0** |
| Q1 | **真实缺口是「文档与收口手续缺失」，不是功能未实现。** |
| Q2 | **能现在收口。** 只需补 1 份 `03_deliver.md` + 更新 1 张迭代卡，无代码改动。 |
| Q3 | 不适用（Q2 已可收口）；若选择暂不收口，next best action 仍是补收口文档，不是补实现或删 AC。 |
| P0 | **0 项**。 |

---

## 一、验证方法（先说明证据从哪来）

| 环节 | 做法 | 结果 |
|------|------|------|
| 构建 | `npm --workspace apps/web run build`（`astro check` + `astro build`） | 0 errors，6 页构建成功（4.56s） |
| 本地运行时 | `wrangler pages dev apps/web/dist` + 本地 D1（`--d1=DB`、`REPORT_KEY=auditkey`） | 6 个路由 200，函数路由实际执行 |
| 数据构造 | 向本地 D1 注入历史脏数据：`sh600519`/`600519` 并存、`asset=etf` 误标、`copy`/`copy_click`/`copy_fail` | 用于复现 us-104 与 us-105 的聚合口径 |
| UI 实测 | Playwright（Chromium）+ 1440/393/375 三档视口 | 选标的→出结果→复制成功/失败、热词点击、移动端溢出全部实测 |
| 线上核对 | `https://jiucaiquan.com/api/top-items`、`/api/top-searches`、`/api/report` | 200/200(HTML fallback)/403，结构见下 |
| us-104 回归 | `node --experimental-strip-types tests/test-symbol.ts` | `74 passed, 0 failed` |
| us-106 | 交付物为文档，逐份核对内容与结构 | 6 项全部命中 |

**限制**：线上 `REPORT_KEY` 不可得，无法读取线上真实漏斗；AC-2「report funnel 可见三类事件」改用**同一份代码路径的本地 D1 端到端**验证（前端真实上报 → `/api/track` 入库 → `/api/report` 聚合）。真实用户剪贴板失败率无法回溯，但那属于诊断结论的可信度问题，不影响 AC 判定。

**临时改动声明**：仅重建了 `apps/web/dist`（`.gitignore` 已忽略）；验证脚本、截图、本地 D1 均写入 `/tmp/jcq-audit/`；未修改任何 `src/`/`functions/`/需求文档；未 push。

---

## 二、AC 逐条判定

### 2.1 us-104（[00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-104/00_card.md#L32-L38)，5 条）

| AC | 判定 | 运行时证据 |
|----|------|-----------|
| AC-1 同一标的唯一 code，全链路统一 | ✅ 通过 | 浏览器表单值为 `sh510300`，实际入库为 `510300`（前端归一化生效）；D1 同时存在 `sh600519` 与 `600519` 时，`/api/report` 合并为**单条** `600519`，`calc=7`（3+4）、`users=6`（跨写法 sid 去重） |
| AC-2 600519 asset=stock，510300=etf | ✅ 通过 | `/api/report` 输出 `600519 asset=stock`、`510300 asset=etf`；线上 `/api/top-items` 同口径（600519 stock、512480 etf） |
| AC-3 topCodes 无重复 + 历史口径可回溯/已标注 | ✅ 通过 | `topCodes` 仅一条 600519；响应含 `topCodesNote`「code 归一化为 6 位码…原始明细保留带前缀写法，可回溯」；D1 原始 `sh600519` 行未被改写 |
| AC-4 新增回归用例并覆盖指定样本 | ✅ 通过 | `74 passed, 0 failed`，含 `600519/sh600519/sz300308/sh511360` 与前后端镜像一致性断言 |
| AC-5 不扩大改动范围 | ✅ 通过 | `7a6ecb3` 仅 6 个文件：`symbol.ts`×2、`ConditionOrderTool.tsx`、`report.ts`、`track.ts`、`tests/test-symbol.ts`；funnel/daily/terms/countries 逻辑未动（本地 report 输出与改前结构一致） |

### 2.2 us-105（[01_req.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/01_req.md#L109-L115)，7 条）

| AC | 判定 | 运行时证据 |
|----|------|-----------|
| AC-1 `02_eng.md` 产出诊断，明确主因 a/b/c 并附证据 | ✅ 通过 | [02_eng.md §一](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/02_eng.md#L6-L22) 给出排序 **(b) > (c) > (a)**；`git show 7ca27e1^` 证实旧 `copyResult()` 无 try/catch、旧 `buildCopyText` 仅 4 个价格字段无买卖方向/基准价——两项代码证据可复现 |
| AC-2 `copy_click`/`copy_fail` 与 `copy` 三段，report funnel 可见 | ✅ 通过 | 本地端到端：`funnel` 同时出现 `copy_click 5/5`、`copy 3/3`、`copy_fail 3/3`；前端 beacon 实际载荷 `copy_fail {asset,code,name,reason:"not_allowed"}` |
| AC-3 `copyResult()` try/catch + fallback + 失败反馈 | ✅ 通过 | 强制 `writeText` reject 且 `execCommand=false`：按钮显示「复制失败，请手动选中」，上报 `copy_fail`，未误报 `copy`；正常路径显示「已复制到剪贴板」 |
| AC-4 复制文案含买卖方向、基准价、≥/≤ 映射、合规声明 | ✅ 通过 | 读取剪贴板实测 8 行：买入（低吸）/卖出（高抛）/小观察价/大观察价/基准价/`券商App条件单以"价格≥/≤"设置`/「不构成投资建议」全部存在 |
| AC-5 `/api/top-items` 无鉴权，返回 `{items,since,days,source}`，空数据 200 | ✅ 通过 | 本地：200，`{items:[...],since,days:30,source:"calculate"}`；空库：200 `{items:[]}`；线上 `jiucaiquan.com/api/top-items` 200 且结构一致；无需 `?key=` |
| AC-6 计算器页热词区块、点击填入过滤、空态不报错 | ✅ 通过（口径已变更） | 页面渲染「近 30 天计算最多」4 个标签；点击「贵州茅台」→ 搜索框=`贵州茅台`，列表已过滤；空数据态显示「近 30 天暂无计算记录」，`pageerror=0`。标题按 26.11.1 us-112 改名，AC 原文「热门标的」已过期（见 P2-1） |
| AC-7 不影响 calculate/copy/select_quote/search 与历史连续性 | ✅ 通过 | 本地 D1 实际收到 `page_view`/`search`（term=半导）/`select_quote`/`calculate`/`copy_click`/`copy`/`copy_fail`；`copy` 仍代表成功语义；us-104 74 条断言全绿 |

### 2.3 us-106（[00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-106/00_card.md#L32-L40)，6 条）

| AC | 判定 | 证据 |
|----|------|------|
| AC-1 产出 10-09 周报并使用模板结构 | ✅ 通过（含必要增补） | [weekly-report-2026-10-09.md](file:///Users/gdeng/work/jiucaiquan/ops/data/weekly-report-2026-10-09.md) 存在；模板六节齐全，另按 AC-3 增补「事件漏斗/地域分布/关键发现」三节（模板本身无漏斗与地域，二者由 AC-3 强制要求） |
| AC-2 30 天窗口 + 显著标注窗口与样本量 | ✅ 通过 | 标题「2026-09-10 ~ 2026-10-09（30 天窗口）」+ §一顶部 ⚠️ 窗口说明 + 155 sid |
| AC-3 含漏斗全表、topTerms、topCodes（asset 错分标注）、地域 | ✅ 通过 | 漏斗 10 行；topTerms 4 行；topCodes 7 行，其中 600519/sh600519 标 `⚠️`；地域 8 个 |
| AC-4 09-29 周报顶部修正注记 | ✅ 通过 | [周报 L3](file:///Users/gdeng/work/jiucaiquan/ops/data/weekly-report-2026-09-29.md#L3-L3) 修正注记存在（措辞含 9 sid 与 89/79 对照） |
| AC-5 更新 26.9.4：状态/勾选/复盘/过程问题 | ✅ 通过 | [26.9.4.md](file:///Users/gdeng/work/jiucaiquan/docs/sprints/26.9.4.md) 状态「✅ 已完成」；4 行全 ✅；验收清单 4/4 勾选；复盘含 3 条过程问题 |
| AC-6 下周优先级指向 us-104/105 | ✅ 通过 | 周报 §八 第 1/2 项分别为 us-104 和 us-105 |

### 2.4 统计

| US | 通过 | 不通过 | 无法判定 |
|----|------|--------|----------|
| us-104 | 5 | 0 | 0 |
| us-105 | 7 | 0 | 0 |
| us-106 | 6 | 0 | 0 |
| **合计** | **18** | **0** | **0** |

---

## 三、三个问题（结论句）

### Q1：真实缺口是「功能未实现」还是「仅文档与收口手续缺失」？

**结论：是「仅文档与收口手续缺失」，功能已实现并已上线。**

决定性证据：us-105 的 7 条 AC 中，6 条工程 AC（AC-2~AC-7）全部通过**本地端到端 + 线上接口**实测——`copy_click/copy/copy_fail` 三段在 `/api/report` funnel 同时出现，`/api/top-items` 线上 200 且 schema 正确，复制成功/失败两条路径的 UI 与埋点均可用；唯一「缺」的是 AC-1 所要求的文档已存在于 `02_eng.md`，而**唯一真正缺失的文件是 `03_deliver.md`**，迭代卡的「进行中」同样是状态未回填。没有任何一条 AC 因为功能缺失而不通过。

### Q2：能不能现在就收口？最小动作清单

**结论：能，现在就收口；零代码改动。**

| # | 动作 | 文件 | 工作量 |
|---|------|------|--------|
| 1 | 新建 us-105 交付记录：AC-1~7 逐条判定 + 证据 + 遗留 P1/P2 + 归档日期 | `team/us/us-105/03_deliver.md` | 约 1 小时 |
| 2 | 迭代卡收口：状态改「✅ 已完成」、3 行 ⏳→✅、4 项验收清单勾选、补复盘（三问：归一化是否归零 / copy-calculate 是否变化 / 2 天救火根因） | `docs/sprints/26.10.1.md` | 约 30~45 分钟 |
| 3 | 追加口径注记：AC-6 的「热门标的」已被 us-112 改为「近 N 天计算最多」，注明以该变更为准，避免下次审计再判冲突 | `team/us/us-105/01_req.md` AC-6 行下 | 约 15 分钟 |
| 4 | 把本审计的 P1/P2 登记进 03_deliver 的遗留项（不阻塞收口） | 同第 1 项 | 含在第 1 项内 |

合计约 **0.3 人日（≈2 小时）**，全部为文档动作；不需要改代码、不需要重新部署、不需要补数据。收口后同步把 `roadmap-gap-analysis.md` 中 26.10.1 的「部分交付、未收口」改为「已交付」。

### Q3：如果不能现在收口，next best action 是什么？

**结论：不适用（Q2 已判定可收口）。** 若用户仍选择暂不收口，next best action 是**补 03_deliver + 迭代卡（纯文档）**，而不是补实现、降级范围或删除 AC——因为不存在未实现的功能。

---

## 四、缺陷分级

### P0（用户可见功能错误 / 合规问题）

**无。** 计算器主路径、复制、热词、移动端均正常；合规声明在页面与复制文案中均存在；禁用词「热门标的/大家都在搜」在计算器页与构建产物中 0 命中。

### P1（不阻塞上线，建议下迭代补）

| # | 问题 | 证据 | 影响 | 建议 |
|---|------|------|------|------|
| P1-1 | `copy_fail` 的 `reason` 未落库 | beacon 载荷含 `reason:"not_allowed"`，但 [track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts#L82-L99) 的 INSERT 无 reason 列，[schema.sql](file:///Users/gdeng/work/jiucaiquan/services/telemetry/schema.sql) 也无该列 | funnel 只能看失败次数，无法区分「权限拒绝/无手势/未知」，FR-2 的诊断价值缩水 | 26.11.2 增加 D1 迁移与写入；不阻塞本迭代收口 |
| P1-2 | 热词跨资产点击：默认 ETF 标签下点股票热词（如「贵州茅台」）→ 列表显示「无匹配」 | Playwright 实测：query 被填入，但标的列表为空；需用户手动切「股票」 | 用户可见的预期落差；不报错、可手动输入兜底 | 下迭代按 `item.asset` 自动切 tab 或在标签上标注品类；本迭代 AC 明确沿用 us-102 行为，不判不通过 |

### P2（仅记录）

| # | 问题 | 说明 |
|---|------|------|
| P2-1 | us-105 01_req AC-6 文案过期 | AC 写「热门标的」「暂无热门标的」，现实现为「近 N 天计算最多」「近 N 天暂无计算记录」（us-112 `963a598d` 决策）。建议按 Q2 第 3 项补注记，不改代码 |
| P2-2 | us-106 周报数字与顾问实测存在 ±1~2 差异 | 周报 page_view 171/155、leaderboard 65/47；卡片记录 170/154、63/46。差异小且周报未注明取数时刻，建议后续周报固定标注「取数时间」。不影响 AC-3 的「关键事实齐全」判定 |
| P2-3 | 周报结构比模板多 3 节 | 模板 6 节，周报 8 节；多出的漏斗/地域/关键发现是 AC-3 强制要求，属合理增补，仅提示「严格使用模板结构」措辞与实际口径需统一 |

---

## 五、顺带核查：旧文案与 AC 冲突表述

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 计算器页可见文本 | ✅ 干净 | 页面实际文本无「大家都在搜」「热门标的」；显示「近 30 天计算最多」 |
| 构建产物 | ⚠️ 仅历史页残留 | `apps/web/dist` 中只有 `/log` 页 2 处「大家都在搜」，均为**历史变更叙述**：10-11 条写「把『大家都在搜』换成近 30 天计算次数 Top5」（描述变更，正确）；09-29 条写「计算器页加了『大家都在搜』Top5」（当时事实，作为日志可接受） |
| 旧接口 | ✅ 已删除 | 线上 `GET /api/top-searches` → 200 `text/html`（SPA 回退，非旧 JSON）；仓库无 `functions/api/top-searches.ts` |
| 其它页面 | ✅ 无冲突 | `/`、`/tools/backtest/`、`/strategies/condition-order/` 文本均无旧热词文案 |

结论：**计算器页与构建产物没有与 us-105 AC 冲突的旧文案**；唯一残留是 `/log` 的历史日志引用，不建议改动（改历史记录反而失真）。

---

## 六、关键证据索引

| 主题 | 文件 / 命令 |
|------|-------------|
| us-104 交付记录 | [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-104/03_deliver.md) |
| us-105 工程记录（含诊断） | [02_eng.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/02_eng.md) |
| us-106 交付记录 | [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-106/03_deliver.md) |
| 迭代卡（未收口） | [26.10.1.md](file:///Users/gdeng/work/jiucaiquan/docs/sprints/26.10.1.md#L5-L45) |
| 计算器组件 | [ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx#L227-L250) |
| 剪贴板兜底 | [clipboard.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/clipboard.ts#L38-L45) |
| 复制文案 | [condition-order.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts#L97-L113) |
| 热词接口 | [top-items.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/top-items.ts) |
| 埋点入库 | [track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts#L82-L99) |
| 周报 | [weekly-report-2026-10-09.md](file:///Users/gdeng/work/jiucaiquan/ops/data/weekly-report-2026-10-09.md) |
| 旧周报修正 | [weekly-report-2026-09-29.md](file:///Users/gdeng/work/jiucaiquan/ops/data/weekly-report-2026-09-29.md#L3-L3) |

复现要点（本地）：
```
npm --workspace apps/web run build
wrangler pages dev apps/web/dist --d1=DB --binding REPORT_KEY=auditkey
# 本地 D1 注入 sh600519/600519 历史行后：
curl '/api/report?key=auditkey&days=30'   # funnel 三门事件 + topCodes 合并
curl '/api/top-items'                     # 200 {items,since,days,source}
node --experimental-strip-types tests/test-symbol.ts   # 74 passed
```

---

*审计 · 2026-11-08 · 未改业务代码、未 push*
