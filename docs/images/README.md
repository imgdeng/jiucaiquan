# 图片清单

> 本目录下存放部署教程的关键截图。把你那天操作过程中保存的截图按下方文件名改名后，直接放到这个目录里，教程文档会自动引用它们。

文件名 | 对应步骤 | 截图内容说明
---|---|---
`01-cloudflare-workers-pages-home.png` | 2.1 | Cloudflare Workers & Pages 首页，右上角可见 "Create application" 按钮
`02-create-application.png` | 2.1 | Create application 页面，上方是 "Pages"（Connect to Git），下方是 "Deploy Worker"（不要选）
`03-build-settings.png` | 2.3 | Pages Build 设置页：Framework preset = Astro，Build output directory = `apps/web/dist`（**手动改掉默认的 `dist`**）
`04-pages-settings-final.png` | 2.3 | Pages → Settings → Builds & deployments 最终配置截图（Build command / Build output / Production branch 都要能看见）
`05-add-site-free-plan.png` | 3.1 第1步 | Cloudflare Add Site → 选 Free 套餐（$0/month，最下面那张卡片）
`06-cloudflare-nameserver.png` | 3.1 第1步 | Cloudflare 给的 nameserver 页面（显示 `camilo.ns.cloudflare.com` + `fay.ns.cloudflare.com`）
`07-aliyun-dns-modify.png` | 3.1 第2步 | 阿里云后台，域名 `jiucaiquan.com` 的 "DNS 修改" 页面，已经填入 Cloudflare 的 2 个 nameserver
`08-pages-custom-domain-setup.png` | 3.1 第3步 | Pages → Custom domains → Set up a custom domain，输入 `jiucaiquan.com`
`09-custom-domains-active.png` | 3.1 第3步 | Custom domains 列表，`jiucaiquan.com` 和 `www.jiucaiquan.com` 状态都是 Active（绿色）
`10-jiucaiquan-homepage.png` | 4 | 浏览器打开 `https://jiucaiquan.com`，首页效果截图
`11-jiucaiquan-calculator.png` | 4 | 计算器页 `/tools/condition-order/` 效果截图

---

**操作方法（把图片放进来）：**

1. 打开 Finder，定位到：`/Users/gdeng/src/jiucaiquan/docs/images/`
2. 把你那天浏览器截的图拖进来，按上面表格改名
3. 命令行：
   ```
   cd /Users/gdeng/src/jiucaiquan
   git add docs/images/*.png
   git commit -m "docs: add deployment screenshots"
   git push origin main
   ```
4. 部署完后打开 `https://jiucaiquan.com/docs/deploy-to-cloudflare-pages/`（或直接在本地用 Markdown 预览看），图片就显示出来了

**如果你没有保存那天的截图也没关系**——下次再部署时，按步骤操作，顺手截一下就行。没有图片文件时，Markdown 文档里会显示一个占位图标，不影响文字内容阅读。
