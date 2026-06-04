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

## 部署

Cloudflare Pages 设置：

- Root directory: 仓库根目录
- Build command: `npm install && npm run build`
- Build output directory: `apps/web/dist`

## 合规边界

本站内容和工具仅用于投资学习、策略研究和条件单辅助计算，不构成证券投资建议，不承诺收益。
