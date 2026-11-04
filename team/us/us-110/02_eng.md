# us-110 开发与自测记录

- 迭代：26.11.1
- 负责：工程马
- 日期：2026-11-04（本轮：预验收 P0-1 / P0-2 / P1 修复）
- 状态：修复完成并全量重跑，待项目马复验 AC-2 / AC-4，AC-5 / AC-7 仍留项目马复核

## 一、冻结决策落地

- D1 不做付费墙：明细区不展示、无「订阅可见」、不接支付、无 paywall 埋点；逐笔明细与权益曲线不生成。
- D2 数据裁剪 B 级：只开 3m 档；6m/12m 保留入口并置灰「数据积累中」；回补后重跑脚本自动开放，前端零改动。
- D3 标的池默认按末日成交额降序；页面不出现「热门」，也不出现「推荐」字样。

## 二、产物

| 产物 | 路径 |
| --- | --- |
| 预计算脚本 | `services/market-data/build_backtest.py` |
| 索引 | `apps/web/public/data/backtest/index.json` |
| 单标的摘要 | `apps/web/public/data/backtest/summary/{code}.json`（59 个） |
| 页面 | `apps/web/src/pages/tools/backtest.astro` |
| 组件 | `apps/web/src/components/BacktestTool.tsx` |
| 复制工具 | `apps/web/src/lib/clipboard.ts` |
| 埋点 | `apps/web/src/lib/telemetry.ts`、`functions/api/track.ts` |
| 每日重建 | `.github/workflows/market-data.yml` |

构建命令：

```bash
python3 services/market-data/build_backtest.py
```

`--check` 只检查门禁与输入文件；`--print-contract` 输出 JSON 数据契约；`--index-only` 只生成索引。门禁文件或 `p1_evidence.json` 缺失时退出码 3，且不写任何文件。

## 三、数据与口径

- 直接代入 P-1：`dataStart=2026-06-08`、`dataEnd=2026-11-03`、`tradingDays=99`；剔除 8 个非交易日假快照；入池 **59 只（ETF 29 + 个股 30，含 510300、600519）**，按末日成交额降序。P-1 证据更新为 59 只后，脚本直接代入，不再产生额外剔除。
- 3m 实际区间 `2026-08-04 ~ 2026-11-03`，60 个交易日；6m/12m 未达 120/240 日门槛，`available=false`、`reason=数据积累中`。
- 价格读取复用 `build_leaderboard.py` 的 `load_snapshots / build_panel / adjust_price_series`，前复权。
- archive 的 `latest` 作为当日收盘价（`close` 字段是昨收，不用于当日 K 线）；用复权收盘价与 `latest` 的比值同比例修正 high/low/open。
- 策略按 01_req §4：`base=(2*close+high+low)/4`、`range=high-low`、`buy=base-range`、`sell=base+range`；D+1 低吸、达到高抛价卖出、最长持有 5 个交易日（第 5 日收盘价结算）；串行单仓。
- **货币/现金类 ETF 不入池**。在 `build_pool` 显式排除名称命中 `货币 / 日利 / 添利 / 现金` 的 ETF，并在池校验末尾做泄漏断言（命中即 `SystemExit`，关键词表为空也拒绝构建）。
- 指标：胜率=盈利笔数/平仓笔数；累计收益率=Σ单笔盈亏/10000；最大回撤按逐日权益（已实现盈亏 + 持仓浮动盈亏，初始资金 1 万元）。
- 样本末段前瞻窗口不足 5 个交易日的信号无法完整结算，构建时直接跳过，不虚构平仓价；该处理需项目马复核。

## 四、实测

- 构建耗时：1.29s user / 1.785s total（含 archive 读取、前复权、59 只模拟与写盘）。
- 幂等：连续两次构建，60 个 JSON 文件集合一致，去掉 `generatedAt` 后逐文件比对差异为空（`diff ignoring generatedAt: []`）。
- 体积：`index.json` 7,408B（预算 150KB）；59 个单标的摘要 944–964B（预算 20KB）；产物目录合计 244KB。
- 旧货币 ETF 摘要 `summary/511880.json` 已在重跑时被 orphan 清理删除，摘要数由 60 降为 59。
- 页面冷加载（本地 preview）：HTML 9,471B / 5.5ms；CSS 14,031B；JS gzip 约 63KB；索引 7,408B / 3.5ms；摘要约 950B / 1.3ms；合计远低于 500KB。
- 393px：`document.documentElement.scrollWidth = document.body.scrollWidth = 393`，无横向滚动。
- 375px：Chrome headless 实测 `innerWidth=375`、`scrollWidth=375`；搜索框 301×50、首个标的项 299×49、策略下拉 301×50、区间按钮 301×44~54、复制按钮 128×48，均 ≥44px。
- 切标的实测：510300 12.5ms、600519 12.8ms、300750 12.0ms（本地 preview），远低于 500ms；切区间为纯前端状态切换。
- 真实数据抽查（页面直接渲染 summary JSON，无运行时计算）：区间均为 `2026-08-04 ~ 2026-11-03（60 个交易日）`

| 标的 | 笔数 | 盈利笔数 | 胜率 | 累计收益率 | 最大回撤 |
| --- | --- | --- | --- | --- | --- |
| 510300 沪深300ETF华泰柏瑞 | 6 | 0 | 0.0% | -10.06% | 11.78% |
| 600519 贵州茅台 | 7 | 4 | 57.1% | +4.26% | 6.43% |
| 300750 宁德时代 | 8 | 0 | 0.0% | -42.31% | 49.08% |

## 五、AC 自测

| AC | 结论 | 证据 |
| --- | --- | --- |
| AC-1 入口 | 通过 | 首页 hero 与计算器页各 1 个 `/tools/backtest` 链接；页面标题含「回测」；`/tools/backtest` 可访问 |
| AC-2 标的池 | 通过（本轮重测） | 池 59 只（ETF 29 + 个股 30），满足 ≥50 且各类 ≥25；含 510300 / 600519；`amount` 单调递减校验 `desc: True`；名称命中「货币/日利/添利/现金」的 ETF 命中数为 0，511880 不在池；搜索可过滤；池外代码提示「暂未覆盖」；无「开始回测」入口 |
| AC-3 选择器 | 通过 | 策略下拉 1 个预置项；仅 3m 可选；6m/12m disabled 且显示「数据积累中」；无日期选择器 |
| AC-4 结果卡 | 通过（本轮重测） | 实际区间、60 个交易日、胜率（含 wins/trades）、收益率费用说明、最大回撤、规则两行、强制声明均展示；抽查三标的数字 = summary JSON（见 §四表格），结算口径修正为第 5 日；切换 12.0–12.8ms |
| AC-6 复制 | 部分通过 | 复制模板字段与顺序符合 FR-5；成功/失败反馈与 `backtest_copy` / `backtest_copy_fail` 已实现；headless 因 `Document is not focused` 无法完成剪贴板写入，需真实浏览器复核 |
| AC-8 移动端 | 通过 | 393px 与 375px 均无横向滚动；结果卡单列；搜索/标的项/策略/区间/复制按钮高度 44–54px |
| AC-9 产物与埋点 | 通过 | 除 `generatedAt` 外字节一致；结束日 = `leaderboard.latestDate`（2026-11-03）；索引 7,408B ≤150KB、摘要 944–964B ≤20KB；59 只池无货币 ETF、无 P-1 剔除标的；4 个事件已注册且无 paywall 事件 |

AC-5（静态/性能/体积）与 AC-7（合规）的最终结论留项目马复核。

## 六、本轮预验收回退项修复记录

### P0-1 结算日错位（AC-4）

- 根因：`simulate_window` 中默认结算写成 `exit_idx = i + hold - 1`，卖出扫描写 `range(i + 1, i + hold)`，实际只持有 4 个交易日；而同一函数上方的 `dates[i:i+hold+1]` 前瞻窗口与 `i <= end_idx - hold` 循环边界都按 5 日预留，内部自相矛盾。
- 修正：`exit_idx = i + hold`（按第 5 个交易日收盘价结算）、卖出扫描 `range(i + 1, i + hold + 1)`；末段窗口边界逻辑不变（不足 5 日前瞻的信号仍跳过）。
- 复测：三个标的与项目马期望值逐项一致（510300 6/0/-10.06/11.78；600519 7/4/57.1/+4.26/6.43；300750 8/0/-42.31/49.08），无第二处错位。

### P0-2 货币 ETF 入池（AC-2）

- 根因：脚本此前只信任 P-1 证据池，未按名称排除货币/现金类 ETF，导致 511880 银华日利ETF 入池并按成交额排到默认第 2 位。
- 修正：新增 `MONEY_ETF_KEYWORDS = ("货币", "日利", "添利", "现金")`，`build_pool` 内对 `asset == "etf"` 且名称命中的标的直接跳过并打印排除日志；池校验末尾追加泄漏断言（命中即 `SystemExit`），关键词表为空时也拒绝构建。
- 验证：当前 P-1 证据已为 59 只，实际构建不再触发排除分支；另用合成证据注入 `511880 银华日利ETF`，脚本输出「排除货币/现金类 ETF：511880 银华日利ETF」并从池中移除；把关键词表置空后构建报「货币 ETF 排除关键词缺失，拒绝构建」。
- 结果：池 59 只（ETF 29 + 个股 30），仍满足 ≥50 与各类 ≥25；`summary/511880.json` 已删除。

### P1 每日重建未接入

- 修正：`.github/workflows/market-data.yml` 在行情构建与排行榜之后追加 `Build backtest static data`（`continue-on-error: true`），并新增 `Report backtest build failure` 步骤在失败时输出 `::warning::`；`git-auto-commit` 的 `file_pattern` 追加 `apps/web/public/data/backtest/index.json` 与 `apps/web/public/data/backtest/summary/*.json`。
- 效果：回测构建失败不阻断行情提交，但会在 Actions 日志中以 warning 显式可见，不会静默；成功后次日页面数据随行情一起更新。

## 七、需项目马复核

1. P0-1 修正后的结算口径：`exit_idx = i + hold`、扫描 `range(i+1, i+hold+1)`，与 §四表格数字互为验证。
2. P0-2 货币 ETF 排除与断言（关键词表 + 泄漏断言 + 空表拒绝构建）；当前证据已是 59 只，无重复剔除。
3. 样本末段不足 5 个交易日前瞻窗口的跳过规则（当前实现：不产生交易、不虚构平仓价）。
4. `latest` 作为当日收盘价的字段语义，以及复权因子同比例修正 high/low/open；8 个非交易日假快照已按 P-1 剔除。
5. 59 只池是否与更新后的 P-1 证据完全一致（脚本直接代入 `p1_evidence.json`，并断言 ≥50/各 ≥25、含 510300/600519、P-1 剔除标的不在池内、入池标的均 ≥60 日）。
6. 4 个 sendBeacon 事件落库时窗口写入 `term`（`win:3m`），未新增 D1 列；`/api/report` 现有漏斗过滤 `search`，不受影响。
7. AC-7 要求页面可见「不构成推荐」，同时禁用词清单又禁止「推荐」二字；页面采用「仅代表成交活跃度，不构成任何投资暗示」，请项目马确认该表述。
8. headless 剪贴板限制导致 AC-6 的复制成功态未机器验证，需真实浏览器复核。
