# us-105 · 交付验收（26.10.1 收口）

> 负责人：项目马 | 验收依据：独立审计 [audit-26.10.1.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/audit-26.10.1.md) | 归档日期：2026-11-08

## 验收结论

✅ **通过**（AC-1 ~ AC-7 全部通过；运行时实测，非自测声明）

> 说明：本卡功能于 2026-10-09 上线，但 `03_deliver.md` 与迭代卡状态一直未回填。2026-11-08 由独立审计按本地 `astro build` + `wrangler pages dev` + 本地 D1 + Playwright 三档视口重新实测，并用线上接口交叉核对；18 条 AC（us-104 5 + us-105 7 + us-106 6）全部通过。本文件引用审计报告中的运行时证据，不重复空写"通过"。

## 验收项（对照 01_req.md）

| 编号 | 验收标准 | 结果 | 运行时证据（审计报告） |
|------|---------|------|----------------------|
| AC-1 | `02_eng.md` 产出诊断，明确 2/89 主因排序并附数据或代码证据 | ✅ | [02_eng.md §一](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/02_eng.md#L6-L22) 给出 **(b) > (c) > (a)**；`git show 7ca27e1^` 可复现旧 `copyResult()` 无 try/catch、旧 `buildCopyText` 仅 4 个价格字段无买卖方向/基准价 |
| AC-2 | 新增 `copy_click`/`copy_fail`，与 `copy` 三段在 `/api/report` funnel 同时可见 | ✅ | 本地端到端（前端真实上报 → `/api/track` 入库 → `/api/report` 聚合）：`funnel` 同时出现 `copy_click 5/5`、`copy 3/3`、`copy_fail 3/3`；beacon 实际载荷 `copy_fail {asset,code,name,reason:"not_allowed"}` |
| AC-3 | `copyResult()` 加 try/catch + fallback + 失败反馈 | ✅ | 强制 `writeText` reject 且 `execCommand=false`：按钮显示「复制失败，请手动选中」、上报 `copy_fail`、未误报 `copy`；正常路径显示「已复制到剪贴板」 |
| AC-4 | 复制文案含买卖方向、基准价、≥/≤ 映射、合规声明 | ✅ | 读取剪贴板实测 8 行：买入（低吸）/卖出（高抛）/小观察价/大观察价/基准价/`券商App条件单以"价格≥/≤"设置`/「不构成投资建议」全部存在 |
| AC-5 | `/api/top-items` 无鉴权，返回 `{items,since,days,source}`，空数据 200 | ✅ | 本地 200：`{items:[...],since,days:30,source:"calculate"}`；空库 200 `{items:[]}`；线上 `jiucaiquan.com/api/top-items` 200 且结构一致；无需 `?key=` |
| AC-6 | 计算器页热词区块、点击填入过滤、空态不报错 | ✅（口径已变更） | 页面渲染「近 30 天计算最多」标签（实测 4 个）；点击「贵州茅台」→ 搜索框=`贵州茅台`、列表已过滤；空态显示「近 30 天暂无计算记录」，`pageerror=0`。AC 原文「热门标的」已按 us-112 变更，见 [01_req.md AC-6 注记](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/01_req.md#L117-L117) |
| AC-7 | 不影响 calculate/copy/select_quote/search 与历史连续性 | ✅ | 本地 D1 实收 `page_view`/`search(term=半导)`/`select_quote`/`calculate`/`copy_click`/`copy`/`copy_fail`；`copy` 仍代表成功语义；us-104 回归 `74 passed, 0 failed` |

## 运行时环境（审计可复现）

- 构建：`npm --workspace apps/web run build`（`astro check` + `astro build`）→ 0 errors，6 页；
- 本地：`wrangler pages dev apps/web/dist --d1=DB --binding REPORT_KEY=auditkey`，6 个路由 200；
- 数据构造：本地 D1 注入 `sh600519`/`600519` 并存、`asset=etf` 误标、`copy`/`copy_click`/`copy_fail`；
- UI：Chromium + Playwright，1440/393/375 三档视口；
- 线上：`/api/top-items` 200、`/api/top-searches` 已删除（HTML 回落）、`/api/report` 403（`REPORT_KEY` 不可得）。

## 遗留项（审计 P1 / P2）

### P1-1 `copy_fail.reason` 未落库

- **事实**：beacon 已携带 `reason:"not_allowed"`，但 [track.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/track.ts#L82-L99) 的 INSERT 无 `reason` 列，[schema.sql](file:///Users/gdeng/work/jiucaiquan/services/telemetry/schema.sql#L6-L18) 亦无该列，入库时被静默丢弃。
- **影响**：不阻断上线。funnel 仍能统计失败次数，但无法区分「权限拒绝 / 无用户手势 / 未知」，FR-2 的诊断价值缩水；属于**可观测性缺口**，不影响用户侧复制兜底行为。
- **修复成本**：约 **0.5 人日**。① schema 增加 `reason TEXT` 并执行一次 D1 `ALTER TABLE`；② `track.ts` 增加 `reason` 白名单（`not_allowed`/`no_user_gesture`/`unknown`）与 INSERT 列；③ 如需在报表呈现，`report.ts` 增加 `copyFailReasons` 聚合（约 0.2 人日）。无前端改动（前端已上报）。
- **处置意见**：并入 **26.11.2 埋点修复批次**（与 `/api/track` 403 同批做 D1 变更，减少一次迁移窗口）；本迭代收口不阻塞。

### P1-2 默认 ETF 标签下点击股票热词显示「无匹配」

- **事实**：热词点击仅执行 `setQuery(it.name)`（[ConditionOrderTool.tsx L329](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx#L323-L333)），未切换 `assetType`；默认 ETF 下点「贵州茅台」→ 搜索框已填入、列表为空，需手动切「股票」。`/api/top-items` 已返回 `item.asset`（[top-items.ts L115-L122](file:///Users/gdeng/work/jiucaiquan/functions/api/top-items.ts#L115-L122)），修复所需字段现成。
- **影响**：用户可见预期落差；不报错、可手动切 tab 兜底；本迭代 AC 沿用 us-102 行为，审计未判不通过。
- **修复成本**：约 **0.2~0.3 人日**（点击时按 `it.asset` 自动 `setAssetType`，补一条 Playwright 回归 + 构建部署），**≤1 人日**。
- **处置意见**：**并入 26.11.2**；若 26.11.2 排期紧张，可降级为在热词标签上标注「ETF/股票」品类，成本更低。

### P2（仅记录，不处置）

| # | 问题 | 说明 |
|---|------|------|
| P2-1 | 01_req AC-6 文案过期 | 已在 [01_req.md AC-6](file:///Users/gdeng/work/jiucaiquan/team/us/us-105/01_req.md#L117-L117) 补口径注记，完成 |
| P2-2 | us-106 周报数字与顾问实测 ±1~2 | 不影响 AC 判定；建议后续周报固定标注「取数时间」 |
| P2-3 | 周报比模板多 3 节 | 为 AC-3 强制要求，合理增补；仅提示模板措辞与实际口径需统一 |

## 归档

- 归档日期：2026-11-08
- 代码改动：无（本次仅补文档与收口手续）
- 相关提交：`7a6ecb3`（us-104 归一化）、us-105 功能提交见 `02_eng.md`；本文件为收口文档

---

*项目马 | 2026-11-08（依据独立审计收口）*
