# us-105 · 复制漏斗诊断 + 埋点补齐 — 需求文档

> 负责人：产品马 | 日期：2026-10-09 | 阶段：需求 | 优先级：P0

---

## 1. 用户故事

> **作为** 韭菜圈的数据负责人，
> **我希望** 查清"89 次计算只换来 2 次复制"的真实原因、补齐复制埋点盲区、并落地一项复制体验修复，
> **以便** 让"计算→复制→券商条件单"的核心转化漏斗可观测、可信任、可改善，而不是对着 2.2% 的失真数字空转。

## 2. 背景与问题

顾问 2026-10-09 实测 `/api/report?days=30`：`calculate`=89（79 用户），`copy`=2（1 用户），转化 **2.2%**。`tasks/task_qna.md` 早已将其列为关键问题但未诊断。

三个已暴露的疑点：

| 疑点 | 证据 | 指向的假设 |
|------|------|-----------|
| 复制埋点只在成功后上报 | [ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) `copyResult()` 无 try/catch，`writeText` 失败则 `track("copy")` 不执行、`setCopied` 不执行 | (b) 点了但剪贴板失败 → 埋点漏报，真实转化更高 |
| 复制文案缺买卖方向/券商字段映射 | [buildCopyText](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts) 只输出"低吸价/高抛价/小观察价/大观察价"，无"买入/卖出"、无基准价、无券商字段提示 | (c) 结果无法直接用于券商条件单 |
| 茅台(21 用户)/沪深300ETF(18 用户)复制=0 | 顾问实测数据 | (a) 用户算完就丢，结果不满足需求或不知能复制 |

同时存在一个关联数据问题：us-102 上线的 `/api/top-searches` 取近 7 天 `search` 事件，但 `search` 事件稀疏（周报曾显示 0），接口自 10-03 起返回 `{"terms":[]}`，「大家都在搜」长期占位文案伤害信任。**30 天 `calculate` 有 79 用户、数据充足**，应切到该数据源。

## 3. 目标与非目标

### 3.1 目标

- 给出 2/89 主因的**书面诊断**（a/b/c 分类 + 数据/代码证据）；
- 补齐复制"点击→成功→失败"三段埋点，让漏斗可观测；
- 落地 1 项本迭代可交付的复制体验修复（可用性 + 文案）；
- 顺手把 `/api/top-searches` 的空壳修掉（切到 `calculate` 30 天数据源）。

### 3.2 非目标

- 多策略计算器（归 us-107）；
- 回测（归 us-110）；
- 引入用户账号体系；
- 复制文案完全对齐每家券商（v1 通用格式，不做券商专属模板）；
- 重做整个计算器结果区布局（v1 只优化复制按钮与文案）。

## 4. 功能需求

### FR-1 复制漏斗诊断（定性 + 证据）

产品马给出初步假设与代码证据线索，**工程马在工程阶段跑数据确诊**，在 `02_eng.md` 产出诊断报告：

| 假设 | 代码/数据证据线索 | 确诊方法 |
|------|------------------|---------|
| (a) 用户没点复制按钮 | 顾问数据：茅台/300ETF 复制=0；按钮在结果区底部，文案"复制条件单文案" | 跑 `/api/report?days=30` 看 `calculate` 用户中 `copy`/`copy_click` 的去重 sid 重合度 |
| (b) 点了但剪贴板失败 | [ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) `copyResult()` 无 try/catch，`writeText` reject 后静默 | 补 `copy_click`+`copy_fail` 埋点后，对比 `copy_click` 与 `copy`（成功）差值 |
| (c) 结果无法直接用于券商 | [buildCopyText](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts) 缺买卖方向/基准价/券商字段映射 | 静态代码分析 + 文案优化后对比转化 |

> 诊断报告归 `02_eng.md`，需明确主因属 a/b/c 哪类（可多选并排序），每项附证据。AC-1 据此验收。

### FR-2 补齐复制三段埋点

- `copy_click`：用户点击「复制条件单文案」按钮时上报（无论后续成败）；
- `copy`（保留事件名=成功）：`writeText` 成功后上报（现有逻辑，**历史数据连续**）；
- `copy_fail`：`writeText` 失败时上报，字段 `{asset, code, name, reason}`（reason 如 `not_allowed`/`no_user_gesture`/`unknown`）；
- 三段写入 D1 `events` 表，`/api/report` funnel 自动可见；
- 埋点字段沿用现有 `track(name, {...})` 模式（见 `lib/telemetry`）。

### FR-3 复制可用性修复（bug + 文案）

**3a. try/catch + fallback（修假设 b）**：
- `copyResult()` 包 try/catch；
- 失败时 fallback `document.execCommand('copy')`（选中隐藏 textarea）或提示「复制失败，请手动选中上方文案」；
- 失败时按钮反馈「复制失败」而非卡住，并上报 `copy_fail`。

**3b. 复制文案优化（修假设 c）**：将 [buildCopyText](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts) 输出改为：

```
{name}({code}) 次日条件单参考：
· 买入（低吸）：{buyPrice}
· 卖出（高抛）：{sellPrice}
· 小观察价：{smallWatchPrice}
· 大观察价：{bigWatchPrice}
· 基准价：{basePrice}
券商App条件单以"价格≥/≤"设置，数量自行决定。
（仅供学习研究，不构成投资建议，独立判断）
```

- 加"买入/卖出"方向，小白可知低吸=买、高抛=卖；
- 补基准价（`result.basePrice` 已有，原文案未展示）；
- 加券商字段映射提示"价格≥/≤"；
- 合规声明保留。

### FR-4 top-searches 空壳修复（切数据源）

- 接口**改名** `/api/top-searches` → `/api/top-items`（语义准确：热门标的，非搜索词）；
- 查询从 `event='search'` 近 7 天 → `event='calculate'` 近 30 天 Top5，返回 `{items:[{code,name,asset}], since, days, source:"calculate"}`；
- 参照 [report.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/report.ts) 第 84-91 行的 codes 查询逻辑（已有 code/name/asset 聚合），去掉 `?key=` 鉴权；
- 计算器页区块：标题"大家都在搜"→"**热门标的**"，标签点击 → `setQuery(name)` 过滤标的列表（与 us-102 点击行为一致，v1 不自动 selectQuote）；
- 无数据时占位文案"暂无热门标的"（calculate 30 天有 79 用户，预期有数据）。

## 5. UI/UE 细节

- 复制按钮：保持现有位置（结果区底部），失败态文案"复制失败，请手动选中"（amber 色），成功态"已复制到剪贴板"（leaf 色，1.6s 复位）；
- 热门标的标签：样式同 us-102（`rounded-full border border-line bg-rice px-3 py-1`），移动端 393px 换行；
- 标签 `aria-label="计算 {name}"`。

## 6. 验收标准（AC）

| 编号 | 验收标准 | 责任主体 |
|------|---------|---------|
| AC-1 | `02_eng.md` 产出诊断报告，明确 2/89 主因属 (a)/(b)/(c) 哪类（可多选排序），每项附 `/api/report?days=30` 数据或代码证据 | 工程马 |
| AC-2 | 新增 `copy_click`（点击时）与 `copy_fail`（失败时）事件，与既有 `copy`（成功）形成三段，可在 `/api/report` funnel 同时看到三类事件 | 工程马 |
| AC-3 | `copyResult()` 包 try/catch，`writeText` 失败时走 fallback（execCommand 或手动复制提示），按钮显示"复制失败"反馈，不再静默卡住 | 工程马 |
| AC-4 | `buildCopyText` 输出含"买入（低吸）/卖出（高抛）"、基准价、券商"价格≥/≤"映射提示，合规声明保留 | 工程马 |
| AC-5 | 新接口 `/api/top-items` 无 `?key=` 鉴权，返回近 30 天 `calculate` Top5 标的 `{items, since, days, source}`，无数据时 `items:[]` HTTP 200 | 工程马 |
| AC-6 | 计算器页"热门标的"区块展示 Top5 标的标签，点击 → 填入搜索框 → 标的列表自动过滤；无数据时展示占位文案不报错 | 工程马 |
| AC-7 | 不影响现有 `calculate`/`copy`/`select_quote`/`search` 功能与历史埋点数据连续性 | 工程马 |

## 7. 技术备注（给工程马）

- 核心改动文件：
  - [ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx)（`copyResult` 加 try/catch + 三段埋点 + 热门标的区块）
  - [condition-order.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/condition-order.ts)（`buildCopyText` 文案改版）
  - [functions/api/report.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/strategies/../../../../../functions/api/report.ts)（参照第 84-91 行 codes 查询，新建 `/api/top-items`）
- `copy` 事件名保留（成功），避免历史 funnel 断裂；
- 诊断报告（AC-1）归 `02_eng.md`，不归本文件——产品马只定义诊断框架，工程马跑数据确诊；
- 文案改版后建议下一迭代观察 `copy_click` → `copy` 转化率验证 (b) 假设；
- `/api/top-items` 若 30 天 `calculate` 仍不足 5 条，可回退到 60 天（在接口内做兜底，AC 不强制）。

## 8. 合规

- 复制文案加"买入/卖出"方向是说明字段含义，**非荐股指令**，保留"不构成投资建议，独立判断"声明；
- 埋点匿名（sid），不采集身份信息；
- 热门标的来自匿名 `calculate` 事件聚合，非推荐榜单。

---

*产品马 | 2026-10-09*

> *需求已确认 · 产品马 | 2026-10-09*
