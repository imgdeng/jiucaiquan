# us-104 · 工程记录

> 负责人：工程马 | 日期：2026-10-09 | 阶段：工程
> 说明：本卡无独立需求阶段，技术方案与自测直接写入本文件（见 00_card.md「当前负责人」注）。

## 改动清单

| 文件 | 说明 |
|------|------|
| [apps/web/src/lib/symbol.ts](file:///Users/gdeng/work/jiucaiquan/apps/web/src/lib/symbol.ts) | 新建。归一化纯函数模块：`normalizeCode`（去 sh/sz/bj 前缀→6 位码）、`classifyAsset`（ETF 白名单判定 stock/etf）、`buildEtfSet`（从带前缀代码构建白名单）。前端与 functions/ 各保留一份同源实现。 |
| [functions/_lib/symbol.ts](file:///Users/gdeng/work/jiucaiquan/functions/_lib/symbol.ts) | 新建。前端模块的镜像（functions/ 与 apps/web 分目录独立构建，各存一份；由回归测试保证一致）。 |
| [apps/web/src/components/ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) | `useMemo` 从 `etfQuotes` 构建 `etfSet`；`calculate`/`copy`/`select_quote`/`watch_add`/`watch_remove` 埋点改用 `normalizeCode` 输出 code、`classifyAsset` 判定 asset（覆盖 toggle 启发式）；计算去重键改用归一化 code，使 sh600519/600519 只记一次。 |
| [functions/api/track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts) | 入库前 `normalizeCode(data.code)` 防御，sh600519/600519 统一存 600519，非法码存 NULL；移除冗余 `cleanCode`。 |
| [functions/api/report.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/report.ts) | `topCodes` 不再 SQL `GROUP BY code`，改为取原始明细行在 JS 按 `normalizeCode` 聚合（合并 sh600519/600519），`users` 用 `Set<sid>` 跨写法去重；`asset` 用 `fetchEtfSet`（拉 /data/etf-latest.json）白名单重分类修正历史脏值，拉取失败降级沿用历史值；新增 `topCodesNote` 口径标注。 |
| [tests/test-symbol.ts](file:///Users/gdeng/work/jiucaiquan/tests/test-symbol.ts) | 新建。74 条断言：normalizeCode 样本（600519/sh600519/sz300308/sh511360/510300 等）、classifyAsset（茅台 stock / 510300 etf）、前后端镜像一致性。 |

## 技术方案

- **归一化口径**：统一为「不带前缀 6 位数字码」（`sh600519`→`600519`、`600519`→`600519`）。去前缀是确定性操作；加前缀需按代码段猜市场（启发式），与顾问「不用启发式」建议冲突，故选去前缀方向。
- **资产归类**：以 `/data/etf-latest.json`（1685 只 ETF）白名单为准——归一化后命中白名单为 `etf`，否则为 `stock`。A 股 6 位码非 ETF 即股票，此判定对项目范围（A 股 stock/ETF）完备且无启发式。
- **三道防线**：① 前端埋点即归一化+分类（源头）；② track.ts 入库再归一化（防御）；③ report.ts 查询时按归一化聚合+重分类（修正历史脏数据）。
- **历史数据**：D1 原始明细保留带前缀写法不回写（可回溯），报表层做归一化与重分类，并在 `topCodesNote`/HTML 注记标注口径。

## 自测记录（对照 00_card.md AC）

- [x] **AC-1** 同一标的在埋点与报表中只有唯一 code（全链路统一） — `normalizeCode` 在前端（ConditionOrderTool 埋点）、track.ts（入库）、report.ts（聚合）三处统一去前缀为 6 位码；回归测试断言 `sh600519`/`600519` 均输出 `600519` ✅
- [x] **AC-2** 贵州茅台 600519 asset=stock，510300 etf — 前端 `classifyAsset("600519", etfSet)` 返回 `stock`（不在 ETF 白名单）、`classifyAsset("510300", etfSet)` 返回 `etf`；report.ts 查询时对历史行同样重分类；回归测试 `clsCases` 断言 ✅
- [x] **AC-3** topCodes 聚合后不再出现重复标的，历史数据口径可回溯或已标注 — report.ts 改 JS 按 `normalizeCode` 聚合，`600519`+`sh600519` 合并为一行（`users` 用 Set 去重）；D1 原始明细保留带前缀写法可回溯；JSON 输出 `topCodesNote` + HTML 注记标注口径 ✅
- [x] **AC-4** 新增回归用例，断言归一化函数对 600519/sh600519/sz300308/sh511360 等样本输出正确 — `tests/test-symbol.ts` 74 条断言全绿（`node --experimental-strip-types tests/test-symbol.ts` → `74 passed, 0 failed`），覆盖卡片全部样本 + 大小写/空白/边界 ✅
- [x] **AC-5** 不扩大改动范围：只修归一化与聚合口径，不重构报表其他逻辑 — 仅新增归一化模块 + 改 track 入库 code 字段 + report 的 topCodes 聚合；funnel/daily/terms/countries 报表逻辑、ConditionOrderTool 计算逻辑、watchlist 存储/去重行为均未改 ✅

## 构建验证

```
# 前端类型检查 + 构建
npm run build
→ astro check 0 errors
→ 4 page(s) built in 2.15s → Complete!

# 后端 functions 类型检查（独立于 astro check）
npx tsc --noEmit --strict --lib es2022,webworker --skipLibCheck \
  functions/api/track.ts functions/api/report.ts functions/_lib/symbol.ts functions/api/top-searches.ts
→ 0 errors

# 回归测试
node --experimental-strip-types tests/test-symbol.ts
→ 74 passed, 0 failed
```

## 部署

- 代码提交：`7a6ecb3` `[工程马] feat(us-104): 标的归一化修复 + 回归用例`
- 部署：Cloudflare Pages 自动部署（git push 触发）
- 上线验证（待 push 后）：`/api/report?key=...&days=30` 的 `topCodes` 中贵州茅台应合并为单行 `code=600519 asset=stock`；`topCodesNote` 字段存在；新埋点写入 D1 后 `code` 列均为不带前缀 6 位码。

## 遗留问题

- 历史明细中 `sh600519` 写法仍存于 D1（按设计保留可回溯，不回写）；若后续需物理归一，可在低峰期跑一次性 `UPDATE events SET code=...`，但非本卡范围。
- 前后端 symbol 模块为镜像双份（架构边界所致）；回归测试已加镜像一致性断言防漂移，后续若引入 workspace 共享可合并为单份。
