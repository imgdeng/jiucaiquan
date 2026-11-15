# US-990 · `jiucaiquan.com` 新增只读对照接口 `GET /api/quote`

> 提出人：项目马（按欢乐马 2026-11-15 16:13 裁定「② 按修正角色加只读对照接口」）｜2026-11-15｜**🚀 已上线，待项目马线上终验**｜优先级 **P0**

---

## 元数据

| 字段 | 值 |
|---|---|
| **编号** | US-990 |
| **标题** | `jiucaiquan.com` 新增只读对照接口 `GET /api/quote` |
| **优先级** | **P0**（1116 一文一码发布前置） |
| **创建人** | 项目马 |
| **创建日期** | 2026-11-15 |
| **当前状态** | 🚀 已上线（2026-11-15），待项目马线上终验 |
| **当前负责人** | 工程马（实现/部署）→ 项目马（线上验收） |
| **关联** | US-991 按本契约改造（可并行），最终联调需本接口线上可用 |
| **顺序** | 欢乐马 16:13 定序：**文案 → US-991（一码，ceo）→ 本卡（站点，em＋欢乐马）**。本卡与 US-991 可并行实现；本接口线上验收是**最终联调实跑**的前置，不阻塞 US-991 按契约改造与降级路径开发 |
| **不重复** | 已有 `GET /api/top-items` 是热门榜聚合接口（依赖 D1，线上实测 15s 超时），**不能复用**为本对照接口 |

---

## 一、为什么需要它

1116 一文的选题是「API+UI 组合测试」，但当前 `playwright-api-ui-combo` 包里**没有任何业务计算接口**：8 条边界值来自本地静态清单，「接口侧期望值」是测试代码在本地按公式重算的；唯一真实 HTTP 是可选的 `GET /api/top-items`，不参与任何断言。这是 `1116_文包一致性核查_20261115.md` 查出的根上的错位。

欢乐马选定 ②：**保留线上页面的真实缺陷，只补测试脚手架**。即新增一个只读对照接口，独立给出「业务上是否允许」和一组参照值，让 API+UI 的三段式第一次真实成立——接口层给独立业务判据 → UI 层看用户可见行为 → 测试层对账下结论。

---

## 二、必须守住的边界（红线）

1. **不碰线上用户计算路径**：`apps/web/src/components/ConditionOrderTool.tsx` 与 `apps/web/src/lib/strategies/condition-order.ts` **一行不改**。`high=9 / low=0.338 / close=0.342 → 低吸价 -6.1565` 是特意保留的教学缺陷，禁止顺手修掉。
2. **判据必须独立编写**：禁止 `import`、复制或复用前端的 `validateOHLC` / `calculateConditionOrder`。本接口是「独立参照实现」，若照抄同一条公式，就会出现文中论证的「两边都错且一致 → 假绿」。
3. **纯计算、零外部依赖**：不读 D1、不查 KV、不 `fetch` 任何外部服务、不写日志到外部。线上 `GET /api/top-items` 实测 15s 超时即为前车之鉴；本接口必须做到连跑两次结果逐字一致，才能把日志贴进文章。
4. **只读**：只接受 GET，不产生任何写操作、不落库、不改状态。
5. **对外文案必须写明**：「这是为演示特意补的测试脚手架，不是生产链路的一环」。禁止宣传成「后端拦住了异常」——它不参与线上页面计算，拦不住任何东西。

---

## 三、接口契约（初稿，em 可实现前与项目马确认）

**请求**

```
GET /api/quote?high=9&low=0.338&close=0.342
```

- 三个参数均为必填、有限数值字符串；`open` 可选（当前计算不用）。
- 非法参数返回 `400` + `{ "error": "..." }`，不得抛 500。

**响应（`200`，`Content-Type: application/json`）**

```json
{
  "input": { "high": 9, "low": 0.338, "close": 0.342 },
  "business_valid": false,
  "reason": "波动区间 8.662 ≥ 基准价 2.5055，低吸价业务上不允许为负",
  "expected": {
    "基准价": 2.5055,
    "波动区间": 8.662,
    "低吸价": -6.1565,
    "高抛价": 11.1675
  },
  "contract_version": "v0.1"
}
```

字段职责在 US-991 中定死：**`business_valid` 只喂给 `sanity()`，`expected` 只喂给 `compare()`**，两者不得交叉使用。`expected` 是「按被测公式复刻的参照值」，故意允许它与 UI 一起错；业务判据 `business_valid` 才是独立的那一条。

**必须稳定可复现的几组**（供项目马按真实日志逐字贴回文章）：

| high | low | close | business_valid | 低吸价参照值 |
|---|---|---|---|---|
| 9 | 0.338 | 0.342 | `false` | -6.1565 |
| 3 | 1 | 1 | `false` | -0.5 |
| 10 | 9 | 9.5 | `true` | 8.5 |
| 999999999999999 | 1.0 | 1.5 | `false` | 负数 |
| 1e308 | 1.0 | 1.5 | `false` | `inf` 相关字段 |

判定条件：`3 × high − 5 × low > 2 × close` 时 `business_valid=false`（等价于 `波动区间 ≥ 基准价`）。

---

## 四、实施范围

- 新增 `functions/api/quote.ts`（Cloudflare Pages Functions，参照现有 `functions/api/top-items.ts` 的 `onRequestGet` 写法）。
- **不改** `astro.config.*`、不改构建模式、不改任何页面组件与策略文件。
- 加一个本地最小测试（同参数两次调用响应逐字一致；`1e308` 不抛异常）。
- 部署由**欢乐马**执行（本会话无站点部署权限）；部署后项目马做线上验收。

---

## 五、验收标准

1. `curl -sS "https://jiucaiquan.com/api/quote?high=9&low=0.338&close=0.342"` 返回 `200`，`business_valid=false`，`expected.低吸价 = -6.1565`，**响应时间 < 1s**。
2. 同参数连跑两次，响应体（除可能的请求 ID 外）**逐字一致**；无 D1 / 外部 fetch 调用。
3. 上表 5 组输入全部返回预期 `business_valid`，非法参数返回 `400` 而非 `500`。
4. 站点页面行为**未变**：手动输入 `9 / 0.338 / 0.342` 仍显示 `-6.1565`（真实缺陷保留）。
5. 提供实现文件与本地测试输出（存证路径由 em 自定），并在卡内回填。
6. 项目马线上 `curl` 复核通过后才算验收；线上不通过不得触发 US-991 的最终联调实跑。

---

## 六、派活顺序（欢乐马 16:13 定序）

```
① 1116_正文_v8.md 文案层通过（✅ 已完成，欢乐马确认后生效）
      ↓
② US-991 ceo 按本契约改源码包 + 降级路径（不阻塞，先做）
      ↓  ③ 本卡 em 实现 → 欢乐马部署 → 项目马线上验收（可与 ② 并行）
      ↓
④ 两者汇合：干净解压实跑两次 → 项目马按真实日志微调 v8 定稿
      → article-preflight → 四维评审 → 欢乐马终审
```

---

## 七、附件 / 参考

- `10_content/release_plan/2026-11-16/release/1116_正文_v8.md`（本卡服务的文案）
- `1116_文包一致性核查_20261115.md` §九～§十一（错位根因、A+ 撤回、修正后的接口角色）
- `apps/web/src/lib/strategies/condition-order.ts` L33–40（`validateOHLC`）、L69（`buyPrice = basePrice - range`）
- `apps/web/src/components/ConditionOrderTool.tsx` L156/L161（计算 100% 在前端）
- `functions/api/top-items.ts`（写法参照）、`1116_改造任务书索引.md`

---

## 八、实施回填（2026-11-15）

| 项 | 内容 |
|---|---|
| 实现 | [functions/api/quote.ts](file:///Users/gdeng/work/jiucaiquan/functions/api/quote.ts)（仅 `onRequestGet`，纯计算） |
| 测试 | [tests/test-quote.ts](file:///Users/gdeng/work/jiucaiquan/tests/test-quote.ts) → `20 passed, 0 failed` |
| 工程记录 | [02_eng.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/02_eng.md) |
| 交付记录 | [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/03_deliver.md) |
| 提交 | `6be797ea8` `[工程马] feat(us-990): 新增只读对照接口 GET /api/quote` |
| 部署 | 推送 `main` 后 Cloudflare Pages 自动部署 ✅ |
| 线上验收 | `9/0.338/0.342` → 200、`business_valid=false`、低吸价 `-6.1565`；5 组固定输入与 400 校验通过；同参响应逐字一致 |
| 未改动 | `ConditionOrderTool.tsx`、`condition-order.ts` 零改动，页面 `9/0.338/0.342` 仍显示 `-6.1565` |
| 环境备注 | 线上请求时延波动较大（静态资源同样波动，非接口代码问题）；本机最低 322ms，服务器纯计算本地实测 3–23ms |

**结论**：接口已上线并按契约返回；最终 `<1s` 硬指标建议项目马在稳定网络下复核，详见 [03_deliver.md](file:///Users/gdeng/work/jiucaiquan/team/us/us-990/03_deliver.md)。

---

*项目马 | 2026-11-15 · 仅开卡，站点代码未动*
*工程马 | 2026-11-15 · 实现、测试、部署回填*
