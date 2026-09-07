# 韭菜圈

A 股 ETF/股票条件单辅助计算工具。第一版采用静态网站 + 后台行情快照文件，不引入数据库。

## 目录

- `apps/web`: Astro + React + Tailwind 前端
- `services/market-data`: 股票/ETF 行情数据生成服务
- `docs`: 产品、合规和运营文档草稿

## 本地运行

```bash
npm install
npm run build-market-data -- --no-live
npm run dev
```

打开 `http://localhost:4321`。

## 行情数据

实时行情参考并抽取自：

- 股票：`/Users/gdeng/src/backtest/aitrade/today.py`
- ETF：`/Users/gdeng/src/backtest/aitrade/monitor.py`

生成命令：

```bash
npm run fetch-stock
npm run fetch-etf
npm run build-market-data
```

无网络或 AkShare 不稳定时，可用本地 CSV 兜底：

```bash
npm run build-market-data -- --no-live
```

输出文件：

- `apps/web/public/data/stock-latest.json`
- `apps/web/public/data/etf-latest.json`
- `apps/web/public/data/data-status.json`

## 阶段排行榜

首页「阶段排行榜」卡片支持个股 / ETF / 板块三个品类，按近 1 周、近 1 月、近 3 月、今年来四个区间查看涨跌幅 TOP10，切换涨跌方向可看跌幅榜，全部为客户端即时筛选，不刷新页面。

排行榜数据由 `services/market-data/build_leaderboard.py` 预计算：

- 基于历史日线做前复权（按涨跌幅阈值识别除权除息缺口），再计算各区间收益率，避免复牌、分红、拆分造成的虚假跌幅；
- 板块由行业 ETF 名称关键词聚合（共 18 个板块），板块涨幅取成分 ETF 中位数，并附带代表 ETF；
- 输出 `apps/web/public/data/leaderboard.json`，随行情数据一起由 GitHub Actions 每个交易日定时重建并提交。

```bash
# 手动重建排行榜（需先有历史日线数据）
python services/market-data/build_leaderboard.py
```

交互埋点：`leaderboard_view`（曝光）与 `leaderboard_switch`（品类 / 涨跌 / 区间切换，带 `term` 参数），上报至 `/api/track`。

## 部署

Cloudflare Pages 设置：

- Root directory: 仓库根目录
- Build command: `npm install && npm run build`
- Build output directory: `apps/web/dist`

## 合规边界

本站内容和工具仅用于投资学习、策略研究和条件单辅助计算，不构成证券投资建议，不承诺收益。
