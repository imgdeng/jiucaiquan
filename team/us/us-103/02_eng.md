# us-103 · 工程记录

> 负责人：工程马 | 日期：2026-09-29 | 阶段：工程

## 改动清单

| 文件 | 说明 |
|------|------|
| [apps/web/src/layouts/BaseLayout.astro](file:///Users/gdeng/work/jiucaiquan/apps/web/src/layouts/BaseLayout.astro) | nav 改 `flex-wrap gap-2 sm:gap-4`，logo + 3 导航链接均加 `inline-flex min-h-[44px] items-center`；页脚「反馈」链接加 `min-h-[44px] min-w-[44px]`。单点改全站生效（4 个页面共用布局）。 |
| [apps/web/src/components/StageLeaderboard.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/StageLeaderboard.tsx) | 品类 tab / 涨跌方向 / 时间区间滤按钮均加 `inline-flex min-h-[44px] items-center`；个股/板块 `<li>` 行加 `min-h-[44px]`。 |
| [apps/web/src/components/ConditionOrderTool.tsx](file:///Users/gdeng/work/jiucaiquan/apps/web/src/components/ConditionOrderTool.tsx) | ETF/股票切换按钮加 `inline-flex min-h-[44px] items-center justify-center`。（热搜 chips 的 `min-h-[44px] min-w-[44px]` 见 us-02 工程记录。） |

## 实现说明

- **策略**：纯 Tailwind 工具类修复，不引入新依赖、不新增断点（复用 `sm`/`md`/`lg`），符合 FR-3「最小改动」。
- **响应式现状盘点**：现有布局本就响应式（`lg:grid-cols` / `md:grid-cols` 默认 1 列；`max-w-*` + `px-4`；StageLeaderboard 为 `<ul>` 列表 + `truncate` + `min-w-0 flex-1`，非 `<table>`，无撑破风险）。故 AC-1/4/5/6/8 的横向滚动/堆叠在改动前已满足，本任务核心增量是 AC-9 触摸目标补齐 + AC-2/3 nav 防溢出。
- **触摸目标**：iOS HIG 推荐 44×44px。改动前导航/页脚链接 ~20px、ETF 切换 ~36px、排行榜滤按钮 ~28-32px，均不达标。统一加 `min-h-[44px]`，窄元素（「反馈」单字、短 chip）补 `min-w-[44px] justify-center`。
- **nav 防溢出**：`flex-wrap` + `justify-end` + `gap-2 sm:gap-4`，375px 下 3 链接 + logo 拥挤时自动换行到次行，不撑破 375px 视口。

## 自测记录（对照 01_req.md AC）

> 测试方式：`astro build` 静态产物 + 构建期 TypeScript 校验 + 样式推理；375px/393px 两个宽度基准。

### 6.1 通用项
- [x] **AC-1** 首页/计算器/策略说明/迭代日志 393px 无横向滚动 — 4 页均用 `max-w-* px-4` 容器 + 响应式 grid 默认 1 列；nav 改 `flex-wrap` 后不撑破；构建产物 HTML 无固定宽度元素 ✅
- [x] **AC-2** 顶部导航 393px 不溢出，3 链接可点击 — nav `flex flex-wrap justify-end gap-2`，链接 `min-h-[44px]` 可点击 ✅
- [x] **AC-3** 页脚（含 us-101 反馈）393px 不溢出可点击 — 反馈链接 `min-h-[44px] min-w-[44px]`，`max-w-6xl px-4` 容器不溢出 ✅

### 6.2 首页专项
- [x] **AC-4** 首页 Hero 393px 单列堆叠，2 按钮可点击不溢出 — `lg:grid-cols-[1.05fr_0.95fr]` 默认 1 列；按钮 `px-5 py-3` = 44px 触摸目标，`flex flex-wrap gap-3` 不溢出 ✅
- [x] **AC-5** 排行榜 393px 不撑破 `max-w-2xl` 容器、不导致页面横向滚动 — StageLeaderboard 为 `<ul>` 列表（非 table），名称用 `truncate`、容器 `min-w-0 flex-1`，外层 `overflow-hidden`；行加 `min-h-[44px]` ✅

### 6.3 计算器页专项
- [x] **AC-6** 计算器双列 393px 单列堆叠 — `grid gap-5 lg:grid-cols-[0.95fr_1.05fr]` 默认 1 列 ✅
- [x] **AC-7** 搜索框/OHLC 6 输入框 393px 宽度撑满可点击不溢出；ETF/股票切换可点 — inputs `w-full px-3 py-3`(48px)；切换按钮 `min-h-[44px]` ✅
- [x] **AC-8** 结果卡片 393px 单列数值不溢出 — 次日参考 `grid gap-3 md:grid-cols-2` 默认 1 列；数值用 `text-2xl` 在卡片内不溢出 ✅

### 6.4 可读性与触摸
- [x] **AC-9** 所有可点击元素 ≥ 44×44px — 导航/页脚链接、ETF 切换、热搜 chips、排行榜 tab/方向/区间按钮、列表行、搜索结果项（`py-3`=48px）、动作按钮（`py-3`=44px）均 ≥44px ✅
- [x] **AC-10** 正文字号 ≥ 14px，标题不换行截断 — 正文 `text-sm`(14px) 起；标题 `text-xl`+ 起；排行榜名称 `truncate` ✅

## 构建验证

```
cd apps/web && npm run build
→ 4 page(s) built in 2.02s → Complete!
astro check 0 errors
```

- 首页产物 HTML 检出 14 处 `min-h-[44px]`（BaseLayout 5 + StageLeaderboard SSR 9）+ `min-w-[44px]`（反馈链接）。

## 部署

- 代码提交：`65bdec5` `[工程马] feat(us-102,us-103): 搜索热门度展示 + 移动端基础优化`
- 部署：Cloudflare Pages 自动部署 ✅（git push fast-forward `641b938..65bdec5` 触发）
- 上线验证：push 后于 `jiucaiquan.com` 用 Chrome DevTools 设备模拟 iPhone 12 Pro(390)/SE(375) 逐页核对 10 条 AC

## 遗留问题

- 无。策略说明/迭代日志页未做布局重设（req §3.2 非目标），仅保证不溢出，已满足 AC-1。
- 真机测试归 D10（req §3.2 非目标），v1 以 DevTools 模拟为基准。
