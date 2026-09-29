# us-101 · 工程记录

> 负责人：工程马 | 日期：2026-09-29 | 阶段：工程

## 改动清单

| 文件 | 说明 |
|------|------|
| [apps/web/src/layouts/BaseLayout.astro](file:///Users/gdeng/work/jiucaiquan/apps/web/src/layouts/BaseLayout.astro) | 全局布局页脚新增「反馈」链接：新标签页打开飞书表单 `https://idaas.feishu.cn/share/base/form/shrcn5u1mI0d5r7hb2kzxyEqNRf`，`hover:text-leaf` 与页脚文本一致，`rel="noopener noreferrer"` 保障外链安全。 |

## 实现说明

- **一处改全站生效**：`BaseLayout.astro` 是全局布局，首页 `/`（`index.astro`）与计算器页 `/tools/condition-order`（`condition-order.astro`）均通过 `<BaseLayout>` 包裹，页脚单点修改后两端同时生效。
- **飞书表单 URL**：直接采用 `01_req.md` §6 已就绪的表单地址，未使用占位符。
- **未引入埋点**：`01_req.md` §6 标注 `feedback_click` 埋点「可选」，6 条 AC 均未要求；为避免越界与范围蔓延，v1 不接入，留待下迭代评估（如需可复用 `functions/api/track.ts`，需在 `EVENTS` 白名单加 `feedback_click`）。

## 自测记录（对照 01_req.md AC）

- [x] **AC-1** 首页与计算器页页脚可见「反馈」链接 — `astro build` 产物 `dist/index.html` 与 `dist/tools/condition-order/index.html` 均检出 `反馈</a>` 字样 ✅
- [x] **AC-2** 点击「反馈」在新标签页打开飞书表单 — 链接含 `target="_blank" rel="noopener noreferrer"`，href 指向飞书表单 URL ✅
- [ ] **AC-3** 飞书表单含三字段（反馈类型/反馈内容/联系方式）— 非工程责任（欢乐马创建·产品马设计，已由产品马 lark-cli 重建并复核通过，见 01_req.md §8.1.1）
- [ ] **AC-4** 表单提交成功提示「感谢反馈…」— 非工程责任（同上）
- [x] **AC-5** 移动端 393px 页脚布局正常无横向滚动 — 页脚容器 `max-w-6xl px-4`，链接为 2 字短文本不触发换行/溢出；构建产物无固定宽度元素 ✅
- [x] **AC-6** 不影响现有页脚链接功能与样式 — 仅在风险提示段后追加一段 `<p class="mt-4">`，原风险提示文案、`text-stone-700 leading-7` 样式与结构未改动 ✅

> AC-3/AC-4 按 01_req.md §5 表注，为飞书表单配置项，由欢乐马创建、产品马设计字段，工程马仅放外链，不承担表单内部配置；产品马已于 2026-09-29 用 lark-cli 重建表单并复核字段与 FR-2 完全一致。

## 构建验证

```
cd apps/web && npm run build
→ 4 page(s) built in 2.04s
→ Complete!
```

- `astro check` 无类型/语法错误
- 首页与计算器页产物 HTML 均含「反馈」链接及正确 href/target 属性

## 部署

- 代码提交：`8a11886` `[工程马] feat(us-101): 全站页脚添加用户反馈入口`
- 部署：Cloudflare Pages 自动部署 ✅（git push 触发，与 `docs/roadmap.md` §10.2 流程一致）
- 上线验证：push 后于 `jiucaiquan.com` 首页与 `/tools/condition-order` 页脚点击「反馈」可跳转飞书表单

## 遗留问题

- 无。`feedback_click` 埋点未接入（v1 非必需），如需追踪反馈点击转化率，下迭代评估。
