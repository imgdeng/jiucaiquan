# us-110 开发与自测记录

- 迭代：26.11.1
- 负责：工程马
- 日期：2026-11-04
- 状态：开发完成，待项目马复核 AC-5 / AC-7

## 一、冻结决策落地

- D1 不做付费墙：明细区不展示、无「订阅可见」、不接支付、无 paywall 埋点；逐笔明细与权益曲线不生成。
- D2 数据裁剪 B 级：只开 3m 档；6m/12m 保留入口并置灰「数据积累中」；回补后重跑脚本自动开放，前端零改动。
- D3 标的池默认按末日成交额降序；页面不出现「热门」，也不出现「推荐」字样。

## 二、产物

| 产物 | 路径 |
| --- | --- |
| 预计算脚本 | `services/market-data/build_backtest.py` |
| 索引 | `apps/web/public/data/backtest/index.json` |
| 单标的摘要 | `apps/web/public/data/backtest/summary/{code}.json`（60 个） |
| 页面 | `apps/web/src/pages/tools/backtest.astro` |
| 组件 | `apps/web/src/components/BacktestTool.tsx` |
| 复制工具 | `apps/web/src/lib/clipboard.ts` |
| 埋点 | `apps/web/src/lib/telemetry.ts`、`functions/api/track.ts` |

构建命令：

```bash
python3 services/market-data/build_backtest.py
```

`--check` 只检查门禁与输入文件；`--print-contract` 输出 JSON 数据契约；`--index-only` 只生成索引。门禁文件或 `p1_evidence.json` 缺失时退出码 3，且不写任何文件。

## 三、数据与口径

- 直接代入 P-1：`dataStart=2026-06-08`、`dataEnd=2026-11-03`、`tradingDays=99`；剔除 8 个非交易日假快照；入池 60 只（ETF 30 + 个股 30，含 510300、600519），按末日成交额降序。
- 3m 实际区间 `2026-08-04 ~ 2026-11-03`，60 个交易日；6m/12m 未达 120/240 日门槛，`available=false`、`reason=数据积累中`。
- 价格读取复用 `build_leaderboard.py` 的 `load_snapshots / build_panel / adjust_price_series`，前复权。
- archive 的 `latest` 作为当日收盘价（`close` 字段是昨收，不用于当日 K 线）；用复权收盘价与 `latest` 的比值同比例修正 high/low/open。
- 策略按 01_req §4：`base=(2*close+high+low)/4`、`range=high-low`、`buy=base-range`、`sell=base+range`；D+1 低吸、达到高抛价卖出、最长持有 5 个交易日（第 5 日收盘价结算）；串行单仓。
- 指标：胜率=盈利笔数/平仓笔数；累计收益率=Σ单笔盈亏/10000；最大回撤按逐日权益（已实现盈亏 + 持仓浮动盈亏，初始资金 1 万元）。
- 样本末段前瞻窗口不足 5 个交易日的信号无法完整结算，构建时直接跳过，不虚构平仓价；该处理需项目马复核。

## 四、实测

- 构建耗时：1.44s（含 archive 读取、前复权、60 只模拟与写盘）。
- 幂等：连续两次构建，除 `generatedAt` 外所有 JSON 字节一致。
- 体积：`index.json` 7,518B（预算 150KB）；单标的摘要 944–963B（预算 20KB）。
- 页面冷加载（本地 preview）：HTML 9,471B / 5.5ms；CSS 14,031B；JS gzip 约 63KB；索引 7,518B / 3.5ms；摘要约 950B / 1.3ms；合计远低于 500KB。
- 393px：`document.documentElement.scrollWidth = document.body.scrollWidth = 393`，无横向滚动。
- 375px：Chrome headless 实测 `innerWidth=375`、`scrollWidth=375`；搜索框 301×50、首个标的项 299×49、策略下拉 301×50、区间按钮 301×44~54、复制按钮 128×48，均 ≥44px。
- 切标的实测：510300 12.5ms、600519 12.8ms、300750 12.0ms（本地 preview，预计算 JSON 读取 + 渲染），远低于 500ms；切区间为纯前端状态切换。
- 真实数据抽查（页面 = JSON）：510300 胜率 0.0%（0/7）、-8.16%、8.55%；600519 62.5%（5/8）、+8.68%、2.89%；300750 0.0%（0/9）、-43.24%、43.24%；区间均为 `2026-08-04 ~ 2026-11-03（60 个交易日）`。

## 五、AC 自测

| AC | 结论 | 证据 |
| --- | --- | --- |
| AC-1 入口 | 通过 | 首页 hero 与计算器页各 1 个 `/tools/backtest` 链接；页面标题含「回测」；`/tools/backtest` 可访问 |
| AC-2 标的池 | 通过 | 池 60 只（ETF 30 + 个股 30），含 510300 / 600519；默认按末日成交额降序；搜索可过滤；池外代码提示「暂未覆盖」；无「开始回测」入口 |
| AC-3 选择器 | 通过 | 策略下拉 1 个预置项；仅 3m 可选；6m/12m disabled 且显示「数据积累中」；无日期选择器 |
| AC-4 结果卡 | 通过 | 实际区间、60 个交易日、胜率（含 wins/trades）、收益率费用说明、最大回撤、规则两行、强制声明均展示；三个标的数字与 JSON 完全一致；切换 12.0–12.8ms |
| AC-6 复制 | 部分通过 | 复制模板字段与顺序符合 FR-5；成功/失败反馈与 `backtest_copy` / `backtest_copy_fail` 已实现；headless 因 `Document is not focused` 无法完成剪贴板写入，需真实浏览器复核 |
| AC-8 移动端 | 通过 | 393px 与 375px 均无横向滚动；结果卡单列；搜索/标的项/策略/区间/复制按钮高度 44–54px |
| AC-9 产物与埋点 | 通过 | 除 `generatedAt` 外字节一致；结束日 = `leaderboard.latestDate`；索引 7,518B ≤150KB、摘要 ≈950B ≤20KB；10 只异常标的未进池；4 个事件已注册且无 paywall 事件 |

AC-5（静态/性能/体积）与 AC-7（合规）的最终结论留项目马复核。

## 六、需项目马复核

1. 样本末段不足 5 个交易日前瞻窗口的跳过规则（当前实现：不产生交易、不虚构平仓价）。
2. `latest` 作为当日收盘价的字段语义，以及复权因子同比例修正 high/low/open；8 个非交易日假快照已按 P-1 剔除。
3. 60 只池是否与 P-1 证据完全一致（脚本直接代入 `p1_evidence.json`，并断言 30+30、含 510300/600519、剔除 10 只不在池内、入池标的均 ≥60 日）。
4. 4 个 sendBeacon 事件落库时窗口写入 `term`（`win:3m`），未新增 D1 列；`/api/report` 现有漏斗过滤 `search`，不受影响。
5. AC-7 要求页面可见「不构成推荐」，同时禁用词清单又禁止「推荐」二字；页面采用「仅代表成交活跃度，不构成任何投资暗示」，请项目马确认该表述。
6. headless 剪贴板限制导致 AC-6 的复制成功态未机器验证，需真实浏览器复核。
