# 韭菜圈部署备忘：从 0 到 1 上 Cloudflare Pages

> 适用场景：GitHub 源码已经有了（Astro + React + 静态站点），域名也买了（阿里云 `jiucaiquan.com`），现在要上线到公网。
> 目标：让 `https://jiucaiquan.com` 和 `https://www.jiucaiquan.com` 可访问，并且每次 push 到 `main` 自动部署。

---

## 1. 前置准备

- 项目已经在本地能跑：`npm install && npm run build` 成功
- 项目已经推送到 GitHub：`github.com/imgdeng/jiucaiquan`
- 域名已经在阿里云买好了：`jiucaiquan.com`
- 注册了 Cloudflare 免费账号：`dash.cloudflare.com`

确认项目根目录里有：
- `apps/web/`（Astro 前端代码）
- `package.json`（根目录里有脚本：`npm run build`）
- `.github/workflows/market-data.yml`（定时行情数据更新，可选）

---

## 2. Cloudflare 新建 Pages 项目

### 2.1 从 Pages 入口开始（不要选 Worker！）

登录 Cloudflare → 左侧 **Workers & Pages** → 右上角 **Create application** → **Pages** → **Connect to Git**。

![Cloudflare Workers & Pages 首页](./images/01-cloudflare-workers-pages-home.png)

![Create application 页面，选 Pages 不要选 Worker](./images/02-create-application.png)

⚠️ **不要选**下半部分的 "Deploy Worker"（`npx wrangler deploy`），那是给后端代码用的，韭菜圈是静态站，用 Pages 才对。如果你之前已经建了一个 Worker 项目，去 Workers & Pages 列表里把它 **Delete** 掉，然后按上面的步骤重建。

### 2.2 选仓库 & 授权

授权 `imgdeng/jiucaiquan` 仓库给 Cloudflare Pages，然后 Production branch 选 `main`。

### 2.3 Build 设置（关键！这里最容易错）

最终设置页面长这样（Cloudflare 字段名是英文的，按下面填）：

| 字段 | 填什么 |
|---|---|
| Project name | `jiucaiquan` |
| Production branch | `main` |
| Framework preset | **Astro**（从下拉菜单里选） |
| Build command | `npm run build`（选了 Astro 后通常自动填好） |
| **Build output directory** | **`apps/web/dist`** ⚠️ 这一项是关键——默认值 `dist` 会部署失败，因为我们是 monorepo 结构，产物在子目录里 |
| Environment variables | 留空 |

![Build 设置页](./images/03-build-settings.png)

![Pages Settings 最终配置](./images/04-pages-settings-final.png)

**如果这里 Build output 只写了 `dist`，部署会失败**——必须改成 `apps/web/dist`。

点 **Save and Deploy**，等 1-2 分钟，Build log 变绿就是成功。

成功后会给一个临时域名 `https://jiucaiquan.pages.dev`，打开它看看首页、计算器、策略说明页面都能正常访问。

---

## 3. 绑定自定义域名（关键步骤）

### 3.1 两步法：先 Add Site（迁 DNS），再绑 Custom domain

**第 1 步：把 `jiucaiquan.com` 加到 Cloudflare 做域名管理**

Cloudflare 首页 → **Add Site** / **Add website** → 输入 `jiucaiquan.com` → 选 **Free 套餐**（$0/month）→ 扫描 DNS 记录时直接 Continue → 最后页面给你 2 个 Cloudflare nameserver。

![Add Site 选 Free 套餐](./images/05-add-site-free-plan.png)

![Cloudflare 分配的 nameserver](./images/06-cloudflare-nameserver.png)

**第 2 步：去阿里云改 DNS**

![阿里云 DNS 修改页面](./images/07-aliyun-dns-modify.png)

- 阿里云 → 控制台 → **域名** → `jiucaiquan.com` → **DNS 修改**
- 把原来的 `dns11.hichina.com` / `dns12.hichina.com` 替换成 Cloudflare 给你的 2 个 nameserver（一行一个，第二个用"+ 添加DNS"按钮加）
- 点蓝色 **"确定"** 按钮
- 等待 10-60 分钟全球生效

**第 3 步：在 Pages 项目里绑自定义域名**

![Pages → Custom domains → Set up](./images/08-pages-custom-domain-setup.png)

Workers & Pages → `jiucaiquan` → **Custom domains** → **Set up a custom domain**：

1. 先输入 `jiucaiquan.com` → 提交 → 点 **Activate domain** → 状态变 **Active** + **SSL enabled**
2. 再输入 `www.jiucaiquan.com` → 同样操作

![Custom domains 最终状态](./images/09-custom-domains-active.png)

> 提示：如果 Custom domains 页面提示 "先完成 DNS 迁移"，但你已经在阿里云改好了，等待一会儿 Cloudflare 会自动检测到，然后就可以直接输入域名提交。

---

## 4. 验证是否成功

用浏览器分别访问：

- `https://jiucaiquan.com`
- `https://www.jiucaiquan.com`
- `https://jiucaiquan.pages.dev`（临时域名保留方便排查问题）

![韭菜圈首页最终效果](./images/10-jiucaiquan-homepage.png)

![计算器页最终效果](./images/11-jiucaiquan-calculator.png)

都能正常打开首页、计算器页、策略说明页，就算部署 OK。

---

## 5. 以后如何更新网站

每次 `git push origin main` 后，Cloudflare Pages 会自动触发部署，一般 1-3 分钟就完成。

在 Cloudflare Pages → `jiucaiquan` → **Deployments** 标签可以看到每次部署的记录。

---

## 6. 常见坑和排查

### 问题 1：Build 失败，报错找不到文件 / dist 目录为空

**检查**：Build output directory 是不是 `apps/web/dist`？默认 `dist` 会失败，因为我们是 monorepo 结构。

**修**：Pages → Settings → Builds & deployments → 修改 Build output directory 为 `apps/web/dist`。

### 问题 2：域名能打开，但报 522 Connection timed out

**原因**：DNS 已经解析到 Cloudflare，但 Pages 项目还没确认这个自定义域名归你。

**修**：确保在 Pages → Custom domains 里添加了 `jiucaiquan.com`，而不仅仅是在 DNS 管理里加了 CNAME。

### 问题 3：第一次打开报 SSL 错误（红色提示）

**原因**：Cloudflare 正在签发免费 SSL 证书。

**修**：等 3-10 分钟，刷新即可。

### 问题 4：行情数据不更新

**检查**：GitHub Actions → `jiucaiquan` 仓库 → Actions 标签 → 看 `Build market data` workflow 是否有定时成功跑。

- 如果 workflow 没有运行记录：检查 `.github/workflows/market-data.yml` 是否在 `main` 分支上
- 如果 workflow 跑失败了：看 log，一般是 AkShare 接口问题或 Python 依赖问题
- 本地可以跑 `npm run build-market-data` 测试一下脚本是否能产出 JSON

### 问题 5：想撤销 / 改回去

- 域名不想用 Cloudflare DNS 了 → 阿里云改回原来的 DNS 即可
- Pages 项目想删 → Workers & Pages → `jiucaiquan` → Settings → Delete project

---

## 7. 关键信息汇总（方便自己以后查）

| 项目 | 值 |
|---|---|
| GitHub 仓库 | `github.com/imgdeng/jiucaiquan` |
| Pages 临时域名 | `https://jiucaiquan.pages.dev` |
| 正式域名 | `https://jiucaiquan.com` / `https://www.jiucaiquan.com` |
| Cloudflare nameserver | `camilo.ns.cloudflare.com` / `fay.ns.cloudflare.com` |
| Build 命令 | `npm run build` |
| Build output | `apps/web/dist` |
| 部署分支 | `main` |
| 部署方式 | Git push → Cloudflare Pages 自动部署 |
| 行情数据 | GitHub Actions 定时任务 + `public/data/*.json` |

