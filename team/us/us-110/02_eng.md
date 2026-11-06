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
- **货币/债券类 ETF 不入池**。关键词表不硬编码，直接读取 P-1 证据 `moneyBondEtf.keywords`（当前 20 项）；`build_pool` 按该表排除 ETF，落盘后再回读 `index.json` 扫描池内名称，命中即 `SystemExit`；证据缺词表或词表为空也拒绝构建。
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
- 修正：新增 `MONEY_ETF_KEYWORDS = ("货币", "日利", "添利", "现金")`，`build_pool` 内对 `asset == "etf"` 且名称命中的标的直接跳过并打印排除日志；池校验末尾追加泄漏断言（命中即 `SystemExit`），关键词表为空时也拒绝构建。（本轮 P2-1 已改为复用 P-1 证据词表 + 产物回读断言，见 §七）
- 验证：当前 P-1 证据已为 59 只，实际构建不再触发排除分支；另用合成证据注入 `511880 银华日利ETF`，脚本输出「排除货币/现金类 ETF：511880 银华日利ETF」并从池中移除；把关键词表置空后构建报「货币 ETF 排除关键词缺失，拒绝构建」。
- 结果：池 59 只（ETF 29 + 个股 30），仍满足 ≥50 与各类 ≥25；`summary/511880.json` 已删除。

### P1 每日重建未接入

- 修正：`.github/workflows/market-data.yml` 在行情构建与排行榜之后追加 `Build backtest static data`（`continue-on-error: true`），并新增 `Report backtest build failure` 步骤在失败时输出 `::warning::`；`git-auto-commit` 的 `file_pattern` 追加 `apps/web/public/data/backtest/index.json` 与 `apps/web/public/data/backtest/summary/*.json`。
- 效果：回测构建失败不阻断行情提交，但会在 Actions 日志中以 warning 显式可见，不会静默；成功后次日页面数据随行情一起更新。

## 七、终验收尾（P2）修复记录

- **P2-1 货币/债券防线**：删除脚本内 4 词硬编码 `MONEY_ETF_KEYWORDS`，新增 `load_money_bond_keywords()` 从 P-1 证据 `moneyBondEtf.keywords`（20 项）读取，单一来源不复制；过滤用该表，泄漏断言移到落盘后 `assert_no_money_bond_leak()` 回读 `index.json` 扫描池内名称（与过滤器不同取值路径，避免同谓词恒空）。词表缺失/为空即 `SystemExit`。
- 验证：用伪造 index 注入 `511880 银华日利ETF`，回读断言报「产物回读发现货币/债券类 ETF 仍在池内：511880 银华日利ETF」；证据删掉 `moneyBondEtf` 后报「P-1 证据缺少货币/债券 ETF 关键词表」并拒绝构建。
- **P2-5 披露**：`BacktestTool.tsx` 策略标签改为「Pivot 条件单（次日低吸/高抛，最长持有 5 个交易日，到期按收盘平仓）」，与 01_req §4 冻结口径一致。
- **P2-3 入口**：首页移除「Sprint 1 交付面板」里的回测卡片，仅保留 hero 的「查看历史回测」按钮，首页回到 1 个入口，与 AC-1 对齐。
- 重跑复核：池 59 只（ETF 29 + 个股 30）、`latestDate=2026-11-03`、3m 60 个交易日；`index.json` 7,408B、59 个摘要 944–964B；连续两次构建除 `generatedAt` 外逐文件差异为空。

## 八、需项目马复核

1. P0-1 修正后的结算口径：`exit_idx = i + hold`、扫描 `range(i+1, i+hold+1)`，与 §四表格数字互为验证。
2. P2-1 词表复用（P-1 证据 `moneyBondEtf.keywords`）与产物回读断言：断言与过滤器已分离取值路径，可被伪造产物触发。
3. 样本末段不足 5 个交易日前瞻窗口的跳过规则（当前实现：不产生交易、不虚构平仓价）。
4. `latest` 作为当日收盘价的字段语义，以及复权因子同比例修正 high/low/open；8 个非交易日假快照已按 P-1 剔除。
5. 59 只池是否与更新后的 P-1 证据完全一致（脚本直接代入 `p1_evidence.json`，并断言 ≥50/各 ≥25、含 510300/600519、P-1 剔除标的不在池内、入池标的均 ≥60 日）。
6. 4 个 sendBeacon 事件落库时窗口写入 `term`（`win:3m`），未新增 D1 列；`/api/report` 现有漏斗过滤 `search`，不受影响。
7. AC-7 要求页面可见「不构成推荐」，同时禁用词清单又禁止「推荐」二字；页面采用「仅代表成交活跃度，不构成任何投资暗示」，请项目马确认该表述。
8. headless 剪贴板限制导致 AC-6 的复制成功态未机器验证，需真实浏览器复核。

## 九、六档 + 底座拼接 + 可解释性 + 中性分布（本轮实现）

### 9.1 档位与底座

- 档位固定 6 个：`3m`(60) / `2w`(10) / `4w`(20) / `6m`(120) / `9m`(180) / `12m`(240)，同一策略、同一复权口径；`2w/4w` 不默认选中。
- 历史底座固定读取 `services/market-data/backtest-base/history_base.json`（与 `meta.json`），文件缺失直接 `FileNotFoundError` 终止构建，不静默降级；底座按日对齐的 `null` 停牌行跳过，不构造假 K 线。
- 底座与 archive 严格禁止日期重叠（重叠即 `SystemExit`）；拼接后统一交给 `adjust_price_series`，**不做二次缩放**（meta `consumerNote`）。
- 拼接连续性断言：archive 首个重叠日（2026-06-08）复权日收益 vs 原始日收益逐只对比，打印 510300/600519/300750 三只，实测差异均为 0.00pp。

### 9.2 可用性与文案

- 池级：`availableSymbols/sample` 与 `coverageNote` 由底座 `meta.constraints` 覆盖写入（`tiers` + `insufficient`），实测 3m/2w/4w=59/59、6m/9m=58/59、12m=57/59。
- 标的级：窗口内可用交易日 < 门槛 → `available=false`，`reason` 为「该标的此区间数据不足（可用 N 个交易日）」；中微公司 12m 按数据线裁决写 **231 日**（12m 窗口 2025-11-05~2026-11-03 实际可用天数；235 为缓存全区间口径，已弃用）。
- 12m 文案固定为「57/59 只满足 240 个交易日；中微公司 231 日、长鑫科技 66 日，数据不足，故近 12 个月档对上述 2 只标的不适用」。
- 方法级局限写入 `index.json#methodology` 与页面：漂移中位 0.0pp、最大 2.85pp（meta `worst=sh600036` 映射为招商银行），并保留「前复权、未计佣金与滑点」。

### 9.3 自洽与体积（实测）

- 构建期强校验：`sum(trade.pnl)=pnlTotal`、`100+cumReturn = equity 终点`、回撤区间一致；示例 510300 3m：pnlTotal -1006.0 / cumReturn -10.06%。
- `index.json` 10,128B（≤150KB）；59 个 summary 最大 1,841B（≤20KB）；59 个 detail 合计 602,842B，单档最大 12m 4,137B（≤6KB/档）。
- 构建耗时：real 2.09s / user 1.56s。
- 幂等：连续两次构建 120 个 JSON 除 `generatedAt` 外差异为空。
- 埋点新增 `backtest_detail_expand` / `backtest_detail_view`，`/api/track` 白名单与窗口集合同步扩展。

### 9.4 页面

- 回测页：新增「回测逻辑」四步说明；逐笔表与权益曲线按需加载（`detail/{code}.json`，同标的一次缓存）；摘要仍 <20KB。
- 池内分布：5 项统计 + 4 档分布条，不点名、不排序、无 TOP/热门/推荐字样。
- 内测路由 `/labs/backtest-top`：`noindex, nofollow`、`robots.txt` Disallow `/labs/`、无导航/sitemap/公开页链接；横幅与「未做访问控制」说明齐备。
- 冒烟：1440 桌面端六档、12m 覆盖文案、中微 231 日、2w 样本不足、逐笔与曲线一致均通过；内测页 200/noindex/10 行且笔数 ≥5 通过。393px 因浏览器锁定 960 视口未能实测，纵向响应式由 `sm:hidden`/`hidden sm:block` 类保证。

### 9.5 待确认

- 底座 meta 现已拆分为两组漂移口径：页面披露组 `driftVsQfqPp`（锚定后，中位 0.0pp / 最大 2.85pp，招商银行 600036），仅核查组 `driftVsQfqRawBase`（未缩放，-0.14pp / 6.72pp，工商银行 601398）；页面只消费前者。

## 10. us-116 全量 universe 热修（2026-11-06）

### 10.1 池 → universe

- 可检索集合改为数据底座中的全部有行情标的：**7,180 只**（ETF 1,611 / 个股 5,569），成交额只用于默认排序，不作准入；不再做货币/债券 ETF 过滤与 disk 回读断言。
- 底座固定读取 `services/market-data/backtest-base/history_base_all.json`（与 `meta_all.json`，约 32MB）；缺失即 `FileNotFoundError`，构建以退出码 4 终止，不静默降级。
- `universe.json` 与 `index.json` 分离：`index.json` 仅含 window/methodology/distribution/top30；`universe.json` 为紧凑并行结构（定长 code 串 + 竖线 name 串 + base36 六档可用日数）。

### 10.2 体积与产物（实测）

| 产物 | 实测 | 预算 |
|---|---|---|
| `index.json` | 7,281B | ≤150KB |
| `universe.json` raw | 264,915B | ≤300KB |
| `universe.json` gzip | 68,945B | ≤80KB |
| 单标的 summary | 7,180 个，单档摘要 <2KB | ≤20KB/个 |
| 单档 detail | 300 只 × 6 档，单档 ≤6KB | ≤6KB/档 |
| detail 合计 | 2,920,807B | ≤12MB |

- 构建耗时：**real 13.93s / user 11.46s**（全量 7,180 × 6 档），远低于 5 分钟目标，无需拆分 workflow。
- 幂等：连续两次构建全部 JSON 除 `generatedAt` 外差异为 0。

### 10.3 覆盖与自测

- 档位可用标的数：3m 7,145/7,180、2w 7,160、4w 7,119、6m 6,690、9m 6,368、12m 6,165；缺口文案按前 5 只 + 「等 N 只」截断，避免 index 膨胀。
- 512170（医疗ETF华宝）：六档全部可用（10/20/60/120/180/240），12m 胜率 61.8%、累计 +19.74%、最大回撤 13.34%（34 笔）。
- 非前 300（300613 富瀚微，成交额排名 301）：六档数字正常；逐笔区固定文案「该标的逐笔明细暂仅对成交额前 300 只提供」。
- 长鑫科技（688825）：3m/2w/4w 可用，6m/9m/12m 均提示「可用 66 个交易日」。
- 默认列表 `index.top` 30 只按末日成交额降序；搜索经 `universe.json` 延迟加载，首屏不请求。
- 393 / 375 真实视口（CDP device metrics）`scrollWidth == innerWidth`，无横向溢出；禁用词 TOP/热门/推荐在构建页 0 命中。

### 10.4 收口拍板（2026-11-06）

- 明细白名单：不开特例。512170 不进入「成交额前 300」，按同一成交额规则不提供逐笔/权益曲线，六档统计不受影响——口径一致性优先于单标的可用性。
- universe gzip：68,945B / 80KB（86%）接受；后续新增字段前必须先压缩（现有编码为定长 code 串 + 竖线 name 串 + base36 日数）。
- coverage 文案：按全量 universe 枚举，最多列 5 只 + 「等 N 只」+ 档位不适用说明，接受。

### 10.5 每日重建与 512170 复核（2026-11-06）

- 每日全量重建（7,180 summary + 300 detail + index/universe/ranking）实测 **real 13.53s / user 11.36s / sys 1.59s**，满足「每日重建 ≤4 分钟」。
- 每日仓库增量：本次重建改写 **7,482 个文件、raw 合计 14.85MB**（summary 12.05MB / detail 2.79MB / index+universe+ranking 13KB），git 对象压缩后约 **5.49MB**；按 git 实际入库计落在预估 7~9MB 以内，raw 层面高于预估，主因 summary 平均 1.76KB/个（仍远低于 20KB/个预算）。
- 512170 六档复核（构建日志与 `summary/512170.json` 双源比对一致，非抽样手填）：3m 9 笔 / 66.7% / +9.57% / 6.02%；2w 2 / 100% / +5.65% / 0.29%；4w 3 / 66.7% / +3.17% / 3.88%；6m 19 / 68.4% / +21.48% / 7.95%；9m 27 / 66.7% / +26.84% / 8.98%；12m 34 / 61.8% / +19.74% / 13.34%（笔数 / 胜率 / 累计收益率 / 最大回撤）。
