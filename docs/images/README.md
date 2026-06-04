# 图片清单

> 本目录下存放韭菜圈部署到 Cloudflare Pages 全过程的关键截图。每张图对应 `deploy-to-cloudflare-pages.md` 文档里的一个具体步骤。

文件名 | 对应步骤 | 截图内容
---|---|---
`cloudflare-workers-pages-home.png` | 2.1 | Cloudflare Workers & Pages 首页，右上角有 "Create application" 按钮
`pages-worker-deploy-failed.png` | 2.1 | 反面教材：第一次选错成 Worker 项目导致部署失败（Latest build failed）
`cloudflare-pages-build-settings.png` | 2.3 | **最关键的设置页**：Framework preset = Astro，Build output directory = `apps/web/dist`
`cloudflare-add-site.png` | 3.1 第1步 | Add a site 页面，选 Connect a domain（不要选 Transfer 或 Buy）
`cloudflare-dns-management.png` | 3.1 第1步 | DNS management 空记录页面，点 Continue to activation 继续
`cloudflare-nameserver.png` | 3.1 第1步 | Cloudflare 分配的 nameserver：`camilo.ns.cloudflare.com` + `fay.ns.cloudflare.com`
`aliyun-dns-modify.png` | 3.1 第2步 | 阿里云 DNS 修改页面，已把默认 DNS 替换成 Cloudflare 的两个 nameserver
`cloudflare-domain-pending.png` | 3.1 第2步 | 域名 Overview 页面，显示 "Waiting for your registrar to propagate your new nameservers"
`pages-custom-domains-setup.png` | 3.1 第3步 | Pages → Custom domains 初始页面，右上角有 "Set up a custom domain" 按钮
`pages-custom-domains-transfer.png` | 3.1 第3步 | Custom domains 提示需要先迁移 DNS 管理，点 Begin DNS transfer
`pages-custom-domains-active.png` | 3.1 第3步 | 最终状态：`jiucaiquan.com` 和 `www.jiucaiquan.com` 都是绿色 Active + SSL enabled
`jiucaiquan-homepage.png` | 4 | 韭菜圈首页效果（域名 `https://jiucaiquan.com` 正常访问）

---

**如果以后需要重新部署或迁移：**

1. 按 `deploy-to-cloudflare-pages.md` 文档步骤操作
2. 截图有更新时直接替换同名文件即可
3. `git add docs/images/*.png && git commit && git push origin main`
4. 静态站重新部署后，文档里的图片会自动更新
