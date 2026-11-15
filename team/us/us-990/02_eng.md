# us-990 · 工程记录

> 负责人：工程马 | 日期：2026-11-15 | 阶段：工程
> 需求卡：[00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/00_card.md)
> 契约：[us-990.json](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/us-990.json)

## 一、需求理解

为 1116「API+UI 组合测试」补一个只读对照接口，让 API→UI→测试三段式第一次真实成立：

- **接口层**独立给出业务判据 `business_valid`，不依赖前端；
- **参照值** `expected` 按被测页面公式独立复刻，故意允许与页面一起错，只供 `compare()` 对账；
- **不参与线上计算**：不碰 `ConditionOrderTool.tsx` 与 `condition-order.ts`，`9 / 0.338 / 0.342 → -6.1565` 的教学缺陷原样保留。

字段职责严格分离：`business_valid` 只喂 `sanity()`，`expected` 只喂 `compare()`。

## 二、实现要点

| 要点 | 实现 |
|---|---|
| 路由 | `functions/api/quote.ts`，仅导出 `onRequestGet`（只读 GET） |
| 参数 | `high` / `low` / `close` 必填有限数值；缺失、空白、`NaN`、`Infinity`、`high < low` 均返回 `400 { error }`；`open` 可选且不参与计算 |
| 独立判据 | `3 * high - 5 * low > 2 * close` → `business_valid = false`；未 import / 复制前端 `validateOHLC`、`calculateConditionOrder` |
| 参照值 | `波动区间 = high - low`；`基准价 = (2*close + high + low) / 4`；`低吸价 = 基准价 - 波动区间`；`高抛价 = 基准价 + 波动区间`；保留 4 位小数（页面默认 ETF 档） |
| 纯计算 | 不读 D1/KV、不 `fetch`、不落库、不写状态；响应无时间戳，同参数两次逐字一致 |
| 极大值 | `1e308` 在 4 位取整时溢出为 `Infinity`，JSON 序列化为 `null`，不抛 500；`business_valid=false` |
| 对外口径 | 文件头注释写明「为演示特意补的测试脚手架，不是生产链路的一环」 |

## 三、改动清单

| 文件 | 说明 |
|---|---|
| [functions/api/quote.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/quote.ts) | 新增只读对照接口；纯计算、独立判据、400 参数校验、`Cache-Control: no-store` |
| [tests/test-quote.ts](file:///Users/gdeng/work/jiucaiquan/tests/test-quote.ts) | 新增本地自测：5 组固定输入、非法参数 400、`open` 可选、同参幂等、耗时 < 1s |
| [team/us/us-990/00_card.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/00_card.md) | 需求卡入库（自 mawentai stories 目录迁入） |
| [team/us/us-990/us-990.json](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/us-990.json) | 结构化需求卡入库 |
| ~~apps/web/src/components/ConditionOrderTool.tsx~~ | **未改** |
| ~~apps/web/src/lib/strategies/condition-order.ts~~ | **未改** |

## 四、本地自测（对照 AC）

| AC | 结果 | 证据 |
|---|---|---|
| AC-1 `9/0.338/0.342` → 200、`business_valid=false`、低吸价 `-6.1565`、<1s | ✅ 本地通过；线上待复核 | 本地 HTTP 实测 23.2ms，响应见下 |
| AC-2 同参数两次逐字一致；无 D1 / 外部 fetch | ✅ | `tests/test-quote.ts` 幂等断言通过；代码无 `env`、无 `fetch` |
| AC-3 5 组固定输入符合预期；非法参数 400 而非 500 | ✅ | `20 passed, 0 failed` |
| AC-4 站点页面行为未变（`9/0.338/0.342` 仍显示 `-6.1565`） | ✅ 静态确认 | `ConditionOrderTool.tsx`、`condition-order.ts` 零改动；`npm run build` 通过 |
| AC-5 提供实现文件与本地测试输出 | ✅ | 本文件 + `tests/test-quote.ts` |
| AC-6 项目马线上 `curl` 复核 | ⏳ 部署后待复核 | 见 [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/03_deliver.md) |

### 固定输入本地实测

```text
200 /api/quote?high=9&low=0.338&close=0.342
{"input":{"high":9,"low":0.338,"close":0.342},"business_valid":false,"reason":"波动区间 8.662 ≥ 基准价 2.5055，低吸价业务上不允许为负","expected":{"基准价":2.5055,"波动区间":8.662,"低吸价":-6.1565,"高抛价":11.1675},"contract_version":"v0.1"}

200 /api/quote?high=3&low=1&close=1
{"business_valid":false,"expected":{"基准价":1.5,"波动区间":2,"低吸价":-0.5,"高抛价":3.5}}

200 /api/quote?high=10&low=9&close=9.5
{"business_valid":true,"expected":{"基准价":9.5,"波动区间":1,"低吸价":8.5,"高抛价":10.5}}

200 /api/quote?high=999999999999999&low=1.0&close=1.5
{"business_valid":false,"expected":{"低吸价":-749999999999997.2}}

200 /api/quote?high=1e308&low=1.0&close=1.5
{"business_valid":false,"expected":{"基准价":null,"波动区间":null,"低吸价":null,"高抛价":null}}

400 /api/quote?high=abc&low=0.338&close=0.342
{"error":"invalid number for high: abc"}
```

## 五、构建与测试命令

```bash
# 接口自测（20 条断言）
node --experimental-strip-types tests/test-quote.ts
# → 20 passed, 0 failed

# functions 类型检查
./node_modules/.bin/tsc --noEmit --strict --moduleResolution bundler \
  --target ES2022 --module ES2022 --skipLibCheck functions/api/quote.ts
# → 0 errors

# 站点构建回归（astro check + astro build）
npm run build
# → 6 page(s) built in 4.61s → Complete!
```

## 六、部署

- 分支策略：本地 `main` 与 `origin/main` 存在分叉，未 force push；在 `origin/main` 的隔离 worktree 上仅提交本卡 4 个文件。
- 提交：`6be797ea8` `[工程马] feat(us-990): 新增只读对照接口 GET /api/quote`
- 推送：`6f42610fc..6be797ea8 HEAD -> main` ✅
- 部署方式：Cloudflare Pages 监听 `main` 自动构建部署（`npm run build` → `apps/web/dist`，Functions 目录 `functions/`）。
- 线上验收：见 [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/03_deliver.md)。

---

*工程马 | 2026-11-15*
