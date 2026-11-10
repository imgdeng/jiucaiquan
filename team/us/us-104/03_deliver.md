# us-104 · 交付验收

> 负责人：项目马 | 日期：2026-10-09 | 阶段：交付

## 验收结论

✅ **通过**（AC-1 ~ AC-5 全部通过）

## 验收项（对照 00_card.md）

| 编号 | 验收标准 | 结果 | 验证依据 |
|------|---------|------|---------|
| AC-1 | 同一标的在埋点与报表中只有唯一 code（全链路统一） | ✅ | `normalizeCode` 在三处统一去前缀为 6 位码：①前端 [ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) L169/183/210/227 埋点；②[track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts) L83 入库防御；③[report.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/report.ts) L140 查询聚合。回归测试断言 `sh600519`/`600519` 均输出 `600519` |
| AC-2 | 贵州茅台 600519 asset=stock，510300 为 etf | ✅ | [symbol.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/symbol.ts) L34-41 `classifyAsset` 用 ETF 白名单判定：`600519` 不在白名单→`stock`，`510300` 在白名单→`etf`。report.ts L158 查询时对历史行同样重分类。测试 `clsCases` 断言 10 条全绿 |
| AC-3 | topCodes 聚合后不再出现重复标的，历史口径可回溯或已标注 | ✅ | report.ts 改 JS 按 `normalizeCode` 聚合（L140），`600519`+`sh600519` 合并为一行，`users` 用 `Set<sid>` 跨写法去重。D1 原始明细保留带前缀写法不回写（可回溯）。JSON 输出 `topCodesNote`（L196）标注口径 |
| AC-4 | 新增回归用例，断言归一化函数对 600519/sh600519/sz300308/sh511360 等样本输出正确 | ✅ | [test-symbol.ts](file:///Users/gdeng/work/jiucaiquan/tests/test-symbol.ts) 74 条断言全绿（`74 passed, 0 failed`）。覆盖卡片全部样本 + 大小写/空白/边界 + 前后端镜像一致性 |
| AC-5 | 不扩大改动范围：只修归一化与聚合口径，不重构报表其他逻辑 | ✅ | 仅新增 symbol.ts 模块 + 改 track 入库 code + report topCodes 聚合。funnel/daily/terms/countries 报表逻辑、计算器计算逻辑、watchlist 存储均未改 |

## 代码审查

| 检查项 | 结果 |
|--------|------|
| 归一化口径 | 去前缀 6 位码（确定性操作，不用启发式），遵顾问建议 ✅ |
| 资产归类 | ETF 白名单为准（1685 只），非 ETF 即 stock，无启发式 ✅ |
| 三道防线 | ①前端埋点即归一化+分类 ②track.ts 入库再归一化 ③report.ts 查询时聚合+重分类 ✅ |
| 历史数据 | D1 原始明细保留可回溯，报表层做归一化与重分类，topCodesNote 标注口径 ✅ |
| 前后端镜像 | 两份同源实现，回归测试加镜像一致性断言防漂移 ✅ |
| 构建验证 | `astro build` 0 errors + `tsc --noEmit` 0 errors + 74 tests passed ✅ |
| Git 提交 | `7a6ecb3` feat + `f656b30` docs + `b36c0af` 补充验证 ✅ |

## 遗留问题

- 历史明细中 `sh600519` 仍存于 D1（按设计保留可回溯，不回写）。若后续需物理归一可在低峰期跑一次性 UPDATE，但非本卡范围。
- 前后端 symbol 模块为镜像双份（架构边界所致），后续若引入 workspace 共享可合并为单份。

## 归档

- 归档日期：2026-10-09

---

*项目马 | 2026-10-09*
