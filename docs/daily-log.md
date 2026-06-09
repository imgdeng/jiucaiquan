# 韭菜圈 · 每日工作日志

> 目标：从 2026-06-04 起，每天记录完成事项、明日计划、踩坑与心得。

---

## 2026-06-04 周二

### 今天完成

- ✅ **Sprint 1 核心交付上线**
  - `jiucaiquan.com` 域名绑定 Cloudflare Pages，首页 + 条件单计算器 + 策略说明页 + 迭代日志页 正常访问
  - HTTPS（SSL）签发完成，`https://jiucaiquan.com` / `https://www.jiucaiquan.com` 均可访问
  - 部署文档 `docs/deploy-to-cloudflare-pages.md` 第一版（纯文字）完成，已 commit 到 `main`
- ✅ **行情数据**：现有 `public/data/` JSON 快照可用，计算器能正常搜索标的 + 自动填充 OHLC
- ✅ **Git 协作流**：SSH key 已配置，`git push origin main` 正常，Cloudflare Pages 自动部署

### 明天（06-05）必须完成

- 🟡 **检查 GitHub Actions 的行情数据定时任务是否正常跑**（`Build market data` workflow）
  - 这是计算器"数据不陈旧"的基础。如果 Actions 没跑或失败，用户看到的价格会越来越老
  - 检查方式：打开 `https://github.com/imgdeng/jiucaiquan/actions`，看最近 24 小时有无成功的 `Build market data`
  - 如果失败 → 需要我修 Python 脚本 / workflow 文件
- 🟡 **完成部署文档的截图插入**
  - 截图你已经在 `docs/images/` 放好了，需要我识别内容 → 重命名 → 更新文档里的 `![](./images/xxx.png)` 引用路径
  - 完成后会让 `docs/deploy-to-cloudflare-pages.md` 从"纯文字"升级为"图文对照"

### 踩坑 / 心得

1. **Cloudflare Pages 与 Cloudflare Workers 不是一回事**
   - 一开始选错类型，选了 `wrangler deploy`（Worker 方式），结果部署失败（`Latest build failed`）
   - **结论**：静态站必须选 **Pages → Connect to Git**，而不是 Workers → Deploy Worker。选错就删掉重来
2. **Build output directory 很关键**
   - 因为是 monorepo（`apps/web/` 里是 Astro），必须把 Build output directory 改成 `apps/web/dist`
   - 默认 `dist` 会部署失败——这一条是整个部署流程里最容易犯的错
3. **DNS 切换需要时间**
   - 在阿里云改完 nameserver → Cloudflare 识别到 → SSL 签发 → 能通过 HTTPS 访问，这一整条链路花了约 30-60 分钟
   - **结论**：部署当天不要急于"点一个按钮立刻好"，改完 DNS 去做别的，回来再查
4. **Git commit message 统一格式**
   - 用 `prefix(scope): 描述` 的约定：`docs(deploy): xxx` / `feat(calc): xxx` / `fix(data): xxx`，回头看历史 commit 一眼能懂

---

## 2026-06-05 周三

### 今天完成

- ✅ **部署文档升级为图文版**
  - 从你放的 36 张编号截图里，筛选出 12 张最有信息价值的，重命名为描述性文件名（如 `cloudflare-pages-build-settings.png`、`pages-custom-domains-active.png`）
  - 其余 24 张（中间流转页、重复页、无关页）已清理，不污染仓库
  - `docs/deploy-to-cloudflare-pages.md` 已把所有 `![](./images/xxx.png)` 指向真实文件
  - `docs/images/README.md` 也升级为"图片清单"，说明每张图的作用
- ✅ **已 commit 并 push 到 `main`**，Cloudflare Pages 自动部署完成，线上文档能看到图片

### 明天（06-06）必须完成

- 🟡 **GitHub Actions 行情数据任务状态检查**（昨天的遗留项）
  - 打开 `https://github.com/imgdeng/jiucaiquan/actions`，看 `Build market data` 最近 24 小时的运行情况
  - 如果全是 ✅ → 没什么要改
  - 如果有 ❌ → 我来修脚本 / workflow
  - 如果没 run（时间到了却没触发）→ 检查 cron 表达式是否写错（可能是 UTC 时区问题）

### 踩坑 / 心得

1. **截图管理要"挑"不要"堆"**
   - 36 张截图放进去会让文档读者困惑：每张图之间到底有啥区别？
   - 正确做法：**每个关键决策点留 1 张**，比如"Build 设置页"只需要一张显示 `apps/web/dist` 的图就够了，前面几页输入域名的图可以删掉
2. **文档里图片 alt 文字要认真写**
   - Markdown 里 `![这张图里有什么](./images/xxx.png)`，引号里的文字不仅仅给盲人读屏用——它也是"图片加载失败时读者唯一能看到的文字"，还能辅助搜索
3. **今天其实是"收尾日"**
   - 核心交付（网站上线）在 06-04 已经做完了，今天主要是文档 + 截图整理
   - 后面 06-06、06-07 应该开始**从 Sprint 1 过渡到 Sprint 2 的规划**：是先做会员入口，还是先做自选池批量计算？

---

## 2026-06-06 ~ 06-08（周末 + Sprint 1 计划评审）

- 行情数据 GitHub Actions 经检查正常（6月5日—8日共 12 次成功触发）
- 阅读并确认 `sprint-update-plan-final.md` 的 P0-1 ~ P2-2 任务清单
- 对比旧 backtest 项目资产（42 天候选标的、7 只 ETF 日线、回测引擎），确认回测功能有足够数据支撑
- 决定 Sprint 1 剩余优先级：P0-1 收盘归档 > P0-2 统计接入 > P0-3 知识星球 > P1-1 迭代日志

---

## 2026-06-09 周二（P0-1 + P0-2 开发交付）

### 今天完成

- ✅ **P0-1：收盘数据归档 `--archive`**
  - `build_market_data.py` 新增 `archive_snapshot()` 函数 + `--archive` 参数
  - 收盘后归档写入路径：`apps/web/public/data/archive/YYYY-MM-DD/`（含 stock/etf/json+data-status 三个文件）
  - 本地验证：`python build_market_data.py build-market-data --no-live --archive` → 成功生成 `archive/2026-06-09/`（3 个文件，91K+ 行）
  - 修改 `market-data.yml`：所有 cron 触发（6 次/交易日）统一加 `--archive`，积累日内+收盘快照
  - 修改 `market-data.yml`：`git-auto-commit file_pattern` 从 `apps/web/public/data/*.json` 扩展为 `apps/web/public/data/*.json apps/web/public/data/archive/*/*.json`
  - `.gitignore` 不阻挡 archive 目录，归档文件随代码一起提交
  - **commit**: `feat(data): add --archive flag to build daily close snapshots for backtesting`

- ✅ **P0-2：百度统计接入**
  - `BaseLayout.astro` 注入百度统计 `hm.js`（ID: `fc5dabf3ea054ec5d0438eeeeba82f83`）
  - 使用 Astro `is:inline` 指令绕过 TypeScript 编译，保留原始 JS（解决 `_hmt` 自引用 + `parentNode` 可能为 null 的 TS 报错）
  - 脚本放在 `</body>` 之前，不影响页面加载
  - 本地验证：`astro check` 0 错误，`astro build` 成功，4 个页面 HTML 均含 `hm.baidu.com` 和正确的 ID
  - **commit**: `feat(stats): inject Baidu Analytics (hm.js) into BaseLayout`

- ✅ **Git Push & 冲突处理**
  - 两次阶段性 commit 均 push 到 `origin/main`
  - 处理了 `git stash` / `pull --rebase` / stash pop 的 data-status.json merge 冲突
  - 确认本地 HEAD == origin/main（`9d64440`）
  - Cloudflare Pages 已触发自动部署

### 明天（06-10）必须完成

- 🟡 **百度统计后台验证**
  - 登录 [tongji.baidu.com](https://tongji.baidu.com) → 查看 `jiucaiquan.com` 是否有 PV 数据（刷新一次首页应该有 1 条记录）
- 🟡 **Cloudflare Pages 部署确认**
  - 打开 Cloudflare → Workers & Pages → `jiucaiquan` → Deployments → 确认最新一条（`9d64440 feat(stats)`）是绿色 ✅
- 🟡 **GitHub Actions 归档验证**
  - 打开 `https://github.com/imgdeng/jiucaiquan/actions` → 看最近一次 `Build market data` 日志 → 确认有 `archive saved to .../archive/2026-06-09/` 字样
- 🟡 **归档文件积累检查**
  - 打开 `https://github.com/imgdeng/jiucaiquan/tree/main/apps/web/public/data/archive` → 应该有 `2026-06-09/` 目录（如果今天的 Actions 跑成功了）

### 踩坑 / 心得

1. **Astro `<script>` 标签会被 TypeScript 检查**
   - 在 `.astro` 文件中写 `<script>` 时，`astro check` 会用 TS compiler 检查 JS 代码
   - 百度统计这类第三方脚本可能触发 TS 类型错误（`_hmt` 自引用、`parentNode` 可能为 null）
   - **解决**：加 `is:inline` 指令 → Astro 不处理这个 script 块，原样输出到 HTML。同时也补了 `if (s && s.parentNode)` null-safety guard
2. **GitHub Actions 的 `file_pattern` 不支持 `**` 时子目录不会被 commit**
   - 之前的 pattern `apps/web/public/data/*.json` 只匹配顶级 JSON，不包含 `archive/2026-06-09/*.json`
   - **解决**：追加 `apps/web/public/data/archive/*/*.json`，每个中间目录用通配符
3. **`--archive` 决定在全部 cron 都加，而不是仅 15:05**
   - 一天 6 次快照全部归档，最后一版（15:05）是收盘价最准的，但盘中的也能用于分析条件单在盘中触发概率
   - 每天产生的文件约 `(1618KB + 480KB + 0.2KB) × 6 ≈ 12MB`，GitHub 仓库 100GB 免费额度，够积累数年
4. **`git stash` + `git pull --rebase` 是处理远程有新 commit 时的标准流程**
   - 本次 push 失败是因为刚 push 完 P0-1 commit，GitHub Actions 立刻跑了一轮并 commit 了新数据
   - `stash → pull --rebase → push → stash pop` 顺序操作，最后处理了 `data-status.json` 冲突：用远程 Actions 生成的版本即可
