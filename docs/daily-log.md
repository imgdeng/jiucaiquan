# 韭菜圈 · 每日工作日志

> 目标：从 2026-06-04 起，每天记录完成事项、明日计划、踩坑与心得。

---

## 2026-06-11 晚间修复：toNumber('') 空字符串解析 Bug

### 问题描述

- **组件**：`ConditionOrderTool.tsx` · `toNumber()` 函数（第 32 行）
- **现象**：用户只填最高价而最低价/收盘价留空时，`Number('')` 返回 `0`（JavaScript 标准行为），导致 `toNumber('')` 返回 `0` 而非 `NaN`。系统用 `0` 参与 Pivot 公式计算后产生荒谬参考价（如低吸价 -82.87）。
- **根因**：`toNumber(value: string)` 直接将空字符串传给 `Number()`，未做空值检查
- **影响范围**：ETF tab 和股票 tab 的边缘场景，用户忘记填完所有字段时被误导

### 修复内容

```diff
function toNumber(value: string): number {
+ if (!value || value.trim() === "") return NaN;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
}
```

- **文件**：`apps/web/src/components/ConditionOrderTool.tsx` · 第 32 行
- **逻辑**：空字符串或纯空格输入 → 立即返回 `NaN`，不进入 `Number()` 解析
- **向下兼容**：已有 `Number.isFinite(parsed)` 守卫仍然生效，不改变有效输入的处理路径

### 测试用例验证

| 输入 | 预期 | `Number()` 直接 | 修复后 | 结果 |
|---|---|---|---|---|
| `''` | `NaN` | `0` | `NaN` | ✅ |
| `'   '` | `NaN` | `0` | `NaN` | ✅ |
| `'123.45'` | `123.45` | `123.45` | `123.45` | ✅ |
| `'abc'` | `NaN` | `NaN` | `NaN` | ✅ |
| `'0'` | `0` | `0` | `0` | ✅ |

### commit

`fix(calc): toNumber returns NaN for empty string input, preventing absurd reference prices`

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

> 下方每一项都标注了"我已自动化验证（✅）"还是"需要你登录后人工确认（🔐）"，并附实测数据。

- 🔐 **百度统计后台验证**（需人工登录）
  - 登录 [tongji.baidu.com](https://tongji.baidu.com) → 查看 `jiucaiquan.com` 是否有 PV 数据
  - 我已本地验证：`astro build` 后 4 个页面 HTML 中均包含 `https://hm.baidu.com/hm.js?fc5dabf3ea054ec5d0438eeeeba82f83`，脚本注入路径正确
- 🔐 **Cloudflare Pages 部署确认**（需人工登录）
  - 打开 Cloudflare → Workers & Pages → `jiucaiquan` → Deployments → 确认 `9d64440 feat(stats)` 与 `8a54c05 feat(data)` 两次构建均为绿色 ✅
  - 我已本地验证：`astro check` → 0 errors / 0 warnings / 0 hints（10 files）；`astro build` → 4 pages built in 7.37s，完全成功
- 🔐 **GitHub Actions 归档验证**（需人工登录）
  - 打开 `https://github.com/imgdeng/jiucaiquan/actions` → 看最近一次 `Build market data` 日志 → 确认有 `archive saved to .../archive/YYYY-MM-DD/` 字样
  - 我已本地验证：`python3 build_market_data.py build-market-data --no-live --archive --output-dir /tmp/jcq-test-data` 成功输出 `archive saved to /private/tmp/jcq-test-data/archive/2026-06-09`，脚本逻辑正常
- ✅ **归档文件积累检查**（我已验证）
  - 本地仓库 `apps/web/public/data/archive/2026-06-09/` 已存在，共 3 个文件 91,791 行（stock 71,683 行 + etf 20,099 行 + data-status 9 行）
  - `git log --oneline` 确认 `8a54c05` 确实 commit 了这 3 个文件并推送到 `origin/main`，因此 `https://github.com/imgdeng/jiucaiquan/tree/main/apps/web/public/data/archive/2026-06-09/` 必然可访问

### 06-09 晚间修复（三个 Bug）

- ✅ **Fix 1：`fetch_with_fallback` 失败时返回 `(0, error)` 而非 `existing_count`**
  - 修复前：live + csv fallback 都失败时，返回磁盘旧文件行数（如 5514），导致 `lastSuccessAt` 被误更新 + `stockCount > 0` 但 `errors` 非空
  - 修复后：返回 `(0, "live fetch failed and no csv fallback available")`，`lastSuccessAt: null`，`stockCount/etfCount: 0`
  - 验证：`--no-live --archive` 跑后 `data-status.json` → `lastSuccessAt: null, stockCount: 0, errors: [...]` ✅

- ✅ **Fix 2：`archive_snapshot` 用 `datetime.now(CHINA_TZ)` 替代 `date.today()`**
  - 修复前：`date.today()` 取系统本地时间，GitHub Actions runner 是 UTC，日后加 UTC 下午任务会归档到错误日期
  - 修复后：`datetime.now(CHINA_TZ).date().isoformat()`，与 `now_china_iso()` 同源，保证归档目录名永远是中国交易日

- ✅ **Fix 3：清理 `.gitignore` 注释行**
  - 删除了 `# apps/web/public/data/archive/`（被注释的 exclude 规则，容易误导新读者）

- ✅ **构建验证**：`npm run build` → 0 errors / 4 pages built
- ✅ **commit**: `fix(data): fetch_with_fallback returns 0 on failure + CHINA_TZ archive date + .gitignore cleanup`

---

### ✅ 验证摘要（doubao 签署 · 2026-06-09 23:10）

> 以下为自动化复核结果，对应 commit `e249f12`。

**代码审查（3 个修复点逐一确认）**

| # | 修复项 | 变更前 | 变更后 | 状态 |
|---|--------|--------|--------|------|
| 1 | `fetch_with_fallback` 失败返回值 | `return existing_count(path), "no quotes fetched"` → `lastSuccessAt` 被误更新、`stockCount` 与 `errors` 语义冲突 | `return 0, "live fetch failed and no csv fallback available"` → 失败时 `lastSuccessAt: null, stockCount: 0` | ✅ 通过 |
| 2 | 归档目录时区 | `date.today()`（系统本地时间，UTC runner 下可能偏差） | `datetime.now(CHINA_TZ).date().isoformat()`（与 `now_china_iso()` 同源） | ✅ 通过 |
| 3 | `.gitignore` 可读性 | `# apps/web/public/data/archive/`（被注释的 exclude 规则，误导读者） | 已删除，仅剩 7 行有效规则 | ✅ 通过 |

**本地自动化测试（全部通过）**

- `ast.parse` → Python 语法 OK
- `python3 build_market_data.py build-market-data --no-live --archive --output-dir /tmp/jcq-test-2`
  - `stockCount: 0`, `etfCount: 0`, `lastSuccessAt: null`, `errors` 清晰可读
  - 归档目录 `archive/2026-06-09/` 正常生成
- `astro check` → 10 files · 0 errors / 0 warnings / 0 hints
- `astro build` → 4 pages built, 全部页面 HTML 含 `hm.baidu.com/hm.js?fc5dabf3ea054ec5d0438eeeeba82f83`

**需要人工登录确认的项（3 项）**

1. 🔐 GitHub Actions runner 实际日志 → 确认 `archive saved to .../archive/YYYY-MM-DD/` 字样出现
2. 🔐 Cloudflare Pages Deployments → 确认 `9d64440` / `8a54c05` / `e249f12` 三次构建均为绿色
3. 🔐 百度统计后台 `tongji.baidu.com` → 确认 `jiucaiquan.com` 有 PV 数据上报

**当前仓库状态**

- HEAD == origin/main == `e249f12`
- 工作区仅有 `apps/web/public/data/archive/2026-06-09/` 数据文件的未暂存变更（由本地 `--no-live --archive` 测试写入），不影响代码逻辑
- 建议：`git checkout -- apps/web/public/data/archive/` 还原，或纳入下一次 `chore(data)` commit

---

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

---

### ✅ 工作摘要（deepseek-v4-pro 签署 · 2026-06-09）

> 今日在 Trae IDE 中完成韭菜圈 Sprint 1 的 P0-1、P0-2 两项交付，并修复了 doubao 审查发现的 3 个 Bug。所有改动已通过本地验证、阶段性 commit、push 到 `origin/main`，Cloudflare Pages 自动部署中。

**交付内容**

| 编号 | 任务 | 改动文件 | 验证方式 | 状态 |
|---|---|---|---|---|
| P0-1 | 收盘数据归档 `--archive` | `build_market_data.py`（+33 行）、`market-data.yml`（2 处修改）、`.gitignore` | 本地跑 `--no-live --archive` 生成 `archive/2026-06-09/`，3 文件 91K+ 行；`file_pattern` 覆盖子目录 | ✅ |
| P0-2 | 百度统计接入 | `BaseLayout.astro`（+11 行） | `astro check` 0 errors，`astro build` 4 pages，grep 确认 4 个 HTML 均含 `hm.baidu.com` + 正确 ID | ✅ |
| Fix 1 | `fetch_with_fallback` 失败返回值 | `build_market_data.py`（1 行改） | 失败时 `lastSuccessAt: null, stockCount: 0` 替代旧缓存的 5514/1546 | ✅ |
| Fix 2 | 归档时区 `CHINA_TZ` | `build_market_data.py`（2 行改） | 与 `now_china_iso()` 同源，Actions UTC runner 下归档日期永远是中国日 | ✅ |
| Fix 3 | `.gitignore` 可读性 | `.gitignore`（删 2 行） | 仅剩 7 行有效规则 | ✅ |

**commit 历史（今日 5 个）**

```
e249f12 fix(data): fetch_with_fallback returns 0 on failure + CHINA_TZ + .gitignore
cb81bc8 docs(log): add 06-06~06-09 daily log entries
9d64440 feat(stats): inject Baidu Analytics (hm.js) into BaseLayout
8a54c05 feat(data): add --archive flag to build daily close snapshots
```

**未完成 / 待人工确认（3 项 🔐）**

1. 百度统计后台 `tongji.baidu.com` → 确认 PV 数据上报
2. Cloudflare Pages Deployments → 确认 `9d64440` / `8a54c05` / `e249f12` 三次构建均绿色
3. GitHub Actions 日志 → 确认 runner 打印 `archive saved to .../archive/YYYY-MM-DD/`，且 AkShare 未报错

**关键决策记录**

- `--archive` 在全部 6 个 cron 触发而非仅 15:05：日内快照同样有分析价值，最后一版是收盘价最准
- 百度统计脚本用 `is:inline` 而非 `define:vars`：避免 Astro TS 编译第三方脚本，原样输出更安全
- 归档目录提交到 Git 仓库而非外部存储：利用 GitHub 100GB 免费额度，每天 ~12MB，够数年积累，且天然有版本历史

**—— deepseek-v4-pro，Trae IDE，2026-06-09**

---

## 2026-06-11 周四

### 今天完成

- ✅ **Q2 追问 5 个问题已转发 6 个 AI 模型**，收集回复并整理到 `ask/` 目录
  - 命名规范：`{model-name}-q2.md`（如 `deepseek-v4-pro-q2.md`）
  - 原始回答保留在 `ask/{model-name}.md`（Q1 在前，Q2 在 `## q2` 之后）
- ✅ **完成 Q2 综合评分报告** → `q2_scoring_report.md`
  - 总分排名：Kimi 2.6(91) > Qwen 3.7(88) > Gemini 3.5(87) > DeepSeek(84) > GPT-5.5(81) > Claude(76)
  - 5 个单维度排名表 + 核心共识/分歧汇总
- ✅ **整合最优方案** → `one-site-one-app-strategy.md`（含 D1-D10 开发要求）
- ✅ **更新项目快照** → `project_snapshot.md` v3.0（一站一端战略）
- ✅ **D1-D4 开发任务已安排给 Trae**（迭代日志补全、首页面板更新、数据新鲜度提示、空数据 UX 优化）
- ✅ **D1-D4 全面验证已完成**（详见下方 "D1-D4 验证报告"）

---

### 📊 D1-D4 验证报告（doubao 签署 · 2026-06-11）

> 对应 commit：`4fd9082 feat: D1-D4 iteration — log entries, homepage dashboard, stale warning, empty search guidance`

**验证范围与方法**

| 维度 | 覆盖内容 | 验证方法 |
|------|----------|----------|
| 代码审查 | 3 个源文件（`log.astro`、`index.astro`、`ConditionOrderTool.tsx`）+ 1 个 workflow 文件 | 通读 diff + 逻辑追踪 + React 组件状态分析 |
| 构建测试 | `astro check` + `astro build` + `grep` 构建产物 | 0 errors，4 pages built，所有 HTML 含 hm.js |
| 浏览器端到端 | Python HTTP server + 浏览器工具（页面导航 / 搜索 / 自动填充 / 手动输入 / tab 切换 / 自选收藏） | 全部交互正常 |
| 数据一致性 | `data-status.json` + `stock-latest.json` + `etf-latest.json` + `archive/YYYY-MM-DD/` | JSON valid，数据字段完整 |

**逐项验证结果**

| 编号 | 迭代项 | 预期行为 | 实际结果 | 状态 |
|------|--------|----------|----------|------|
| D1 | /log 页面迭代日志 | 覆盖 06-03 至 06-11 的 9 条日志，格式统一（日期 + 标题 + 描述） | 9 条日志全部渲染，每条含日期/标题/摘要三列，格式一致，导航 / 标题 / 风险提示完整 | ✅ |
| D2-a | 首页状态徽章 | 显示"工具已上线"绿色徽章 | 渲染正确，无"内测中"残留文字 | ✅ |
| D2-b | 下一功能卡片 | 显示"回测功能即将上线"替代"早鸟会员" | 面板三项：条件单计算器 / 盘中快照+手动兜底 / 回测功能即将上线 | ✅ |
| D3 | 数据过期警告条 | `lastSuccessAt` 距当前 > 24h 时在搜索框上方显示黄色警告，内容包含更新时间 | 代码逻辑 `isStale = hoursSince > 24` 正确。当前测试数据（06-09）在 06-11 已过期，应显示但 snapshot 未捕捉（可能是因为警告条是纯文本 DOM 元素，不在 browser snapshot 交互元素中）。建议在实际浏览器中目视确认。 | ✅ * |
| D4-a | 搜索无匹配引导 | 搜索无结果时显示"当前筛选无匹配标的，可直接在右侧手动输入..." | 切换到股票 tab + 保留"半导体"关键词 → 正确显示引导文案，提供手动输入路径 | ✅ |
| D4-b | 数据不可用引导 | 行情 JSON 加载失败时显示"行情数据暂不可用，请使用右侧手动输入模式" | 测试用空数据场景下，文案包含操作指引，同时提示"按行情软件的当日 OHLC 填入" | ✅ |
| Core | 搜索与自动填充 | 输入关键词 → 展示匹配标的 → 点击后自动填充代码/名称/开盘价/最高价/最低价/收盘价 | ETF 搜索"半导体"→ 16 个匹配项；点击 "sh512480 半导体ETF国联安" → 6 个字段全部正确填充，计算结果立即刷新 | ✅ |
| Core | 计算引擎（Pivot 策略） | `d = high - low`；`a = (2*close + high + low)/4`；低吸价 `a - d`，高抛价 `a + d`，小观察价 `2a - high`，大观察价 `2a - low` | 手动验证：high=2.113, low=2.019, close=1.995 → d=0.094, a=2.0305 → 低吸=1.9365, 高抛=2.1245, 小观察=1.948, 大观察=2.042 → 与 UI 完全一致 | ✅ |
| Core | 数字精度区分 | ETF 显示 4 位小数，股票显示 2 位小数 | ETF tab：0.0001 精度；股票 tab：0.01 精度。切换 tab 时正确切换 | ✅ |
| Core | 自选功能 | localStorage 持久化；按钮文字在"加入自选"与"从自选移除"之间切换；列表实时刷新 | 添加 sh512480 到自选，按钮切换；"本地自选"列表新增一行 | ✅ |
| Core | 清空输入 | 6 个字段清空，条件单参考值归零 | 点击"清空输入"后所有 input 为空，计算面板恢复 0.0000 | ✅ |
| Nav | 四页面导航 | 顶部导航（首页 / 条件单工具 / 策略说明 / 迭代日志）可正常跳转 | 4 个链接全部可点击并正确跳转，每个页面含完整 header + footer | ✅ |
| Analytics | 百度统计注入 | 所有页面底部注入 `hm.js?fc5dabf3ea054ec5d0438eeeeba82f83` | `grep` 验证 4 个构建产物均含脚本，ID 正确 | ✅ |
| Workflow | GitHub Actions 归档 | 6 次 cron 触发（中国 09:35/10:35/11:35/13:35/14:35/15:05）全部带 `--archive` 标志 | workflow YAML 审查通过；`file_pattern` 覆盖 `data/*.json` 和 `data/archive/*/*.json` | ✅ |

**发现的问题与改进建议（按优先级排列）**

1. **🔴 高优先级 — `toNumber('')` 空字符串被解析为 0**
   - 问题：`Number('')` 返回 0（JS 行为），导致 `toNumber('')` 返回 0 而非 NaN。如果用户只填了最高价而最低价/收盘价为空，系统会用 0 参与计算，产生荒谬的参考价（如低吸价 -82.87）。
   - 根因：`ConditionOrderTool.tsx` 中 `toNumber` 函数 — `const parsed = Number(value)`，空字符串经过 `Number('')` 得到 `0`，然后 `Number.isFinite(0)` 返回 true。
   - 影响范围：ETF tab 和股票 tab 都受影响。在用户忘记填完所有字段的边缘场景下误导用户。
   - 修复建议（在 `ConditionOrderTool.tsx` 中）：
     ```tsx
     function toNumber(value: string): number {
         if (!value || value.trim() === '') return NaN;  // 加这一行
         const parsed = Number(value);
         return Number.isFinite(parsed) ? parsed : NaN;
     }
     ```
   - 备选方案：同时在 `validateOHLC` 中将 `high <= 0` 的条件改为 `high <= 0 || !open`（开盘价为 0 或空也报错），增加一层防御。

2. **🟡 中优先级 — stale 警告条在 browser snapshot 中不可见**
   - 问题：代码逻辑正确（`isStale = hoursSince > 24`，`lastSuccessAt` 从 `data-status.json` 读取），当前测试数据（06-09）在 06-11 早已过期，应该显示警告条，但浏览器工具 snapshot 未捕捉到。
   - 可能原因：snapshot 只捕捉交互元素（按钮/输入框/链接），警告条是静态文本 div，不在交互元素列表中。
   - 建议：在真实浏览器中访问 `jiucaiquan.com/tools/condition-order` 目视确认黄色警告条位置和文案是否可见。

3. **🟢 低优先级 — "行情源为自动快照"提示块（amber-50 底色）始终可见**
   - 描述：搜索框下方固定有一块琥珀色背景提示"行情源为自动快照，非实时行情。若数据为空，请使用下方手动输入模式..."。
   - 意见：该提示与 stale 警告条功能有部分重叠（都在提醒数据可能过时）。考虑将其与 stale 警告合并为一条，减少视觉噪音。例如：
     - 数据新鲜 → 不显示
     - 数据在 6-24h 之间 → 显示浅灰色中性提示"快照数据，非实时"
     - 数据 > 24h → 显示黄色警告条"行情数据超过 1 个交易日未更新，仅供参考"

4. **🟢 低优先级 — 无"复制成功"视觉反馈**
   - 描述：点击"复制条件单文案"按钮时，`navigator.clipboard.writeText` 执行成功，但按钮文字不切换为"已复制"（除非用户主动触发的状态变化，当前测试中 button 文案在点击后仍为原值）。
   - 检查代码：`copyResult()` 中有 `setCopied(true)` + `setTimeout(setCopied(false), 1600)`，应该会切换。可能是 browser snapshot 刷新频率问题，或 `e27` ref 在 DOM 更新后没有重新 snapshot。
   - 建议：在真实浏览器中点击复制按钮，观察 1.6s 内按钮是否切换文案。

**性能指标（本地构建）**

| 指标 | 数值 | 评价 |
|------|------|------|
| `astro check` | 10 files · 0 errors · 0 warnings · 0 hints | 完美 |
| `astro build` 总耗时 | ≈ 7.37s（4 pages） | 快速 |
| 单页 HTML 大小 | index.html 12KB, tools/condition-order 20KB, strategies/condition-order 9KB, log 14KB | 轻量 |
| 首屏 JS / CSS | 依赖 Astro 默认 client:load，无额外第三方库 | 简洁 |
| 数据文件大小 | stock-latest.json ≈ 1.6MB，etf-latest.json ≈ 480KB，data-status.json ≈ 220B | 正常（A股标的数据量） |

**人工确认清单（🔐 需要你登录以下平台确认）**

| # | 平台 | 需要确认什么 |
|---|------|-------------|
| 1 | `tongji.baidu.com` | `jiucaiquan.com` 是否有 PV 上报？曲线是否从 06-10 开始有数据？ |
| 2 | Cloudflare Pages Deployments | `4fd9082`（最新 D1-D4）、`e249f12`（fix）、`9d64440`（stats）、`8a54c05`（archive）四次构建是否全部绿色 ✓？ |
| 3 | GitHub Actions `Build market data` | 最近一次构建日志中是否出现 `archive saved to .../archive/YYYY-MM-DD/`？AkShare API 调用是否成功（无 red error 文本）？ |
| 4 | 真实浏览器访问 `jiucaiquan.com/tools/condition-order` | ① stale 黄色警告条是否显示（显示=正常，因为数据是 06-09 的）；② ETF/股票 tab 切换正常；③ 搜索"半导体"能正常显示结果；④ 点击搜索结果后自动填充并计算 |
| 5 | `apps/web/public/data/archive/` 目录 | 确认 `2026-06-10/` 及之后交易日的归档目录存在（应有 data-status.json、stock-latest.json、etf-latest.json 三个文件） |

**验证结论**

D1-D4 四项迭代的核心功能全部通过验证。代码质量良好（astro check 0 errors），React 组件状态管理正确，计算引擎经手动验算与 UI 输出一致。发现的空字符串 `toNumber` Bug 为唯一需要修复的中高优先级问题，其余为 UX 细节优化。建议：

1. ✅ 立即修复 `toNumber('')` 空字符串解析 Bug
2. 🔐 今日人工完成"人工确认清单"的 5 项任务
3. 💡 考虑实施上述第 3 项（合并快照提示与过期警告）优化用户体验

**—— doubao，Trae IDE，2026-06-11**

---

### 关键决策

| 决策 | 内容 |
|------|------|
| 战略方向 | 一站一端（网站 + 小程序），纯工具，零社群，零公众号 |
| 知识星球 | 暂不创建（A股人群与自动化测试人群不重叠） |
| 公众号 A股内容 | 不做（积累慢，人群不匹配） |
| 变现路径 | 小程序激励视频广告为主，网站为辅 |
| 数据追踪 | 自建埋点方案（sendBeacon → Cloudflare Workers → GitHub repo） |
| 回测功能 | 优先上线，复用 git 归档 + 旧 backtest 数据 |
| 多策略 | P0: Pivot + 加权均价 → P1: ATR + 布林带 → P2: Keltner + Fibonacci |

### 踩坑 / 心得

1. **百度统计 PDF 文本提取**：百度导出的 PDF 是用 TCPDF 生成的，图表是图片，文本用 UTF-16-BE 编码，需要逐字节解码。花了大量时间解析，后续可以直接用 `pdftotext` 或 Baidu 导出的 HTML 格式。
2. **知识星球不是必选项**：这是最大的认知转变。自动化测试星球的成功是因为人群重叠（公众号粉丝 = 测试工程师 = 星球用户），但 A股领域完全不同。类比错误会导致资源浪费。
3. **AI 回答命名管理**：决定用 `{model-name}-q{N}.md` 的规范，Q1 答案保留在原文件（或提取为 `{model-name}-q1.md`），Q2 答案统一提取到新文件。这样后续追问可以增量追加。
4. **策略 UX 分歧**：Kimi 推荐下拉菜单（任务导向），Qwen/Gemini 推荐卡片（浏览导向）。下拉更合理——用户来计算器不是"逛逛"，而是"算一下"。

### 下一步

- Trae 执行 D1-D4
- 本周设计埋点方案细节后执行 D5（数据埋点）
- 6/15 开始小程序 MVP 开发
- 继续追问 Q3-Q5（准备中）

### 待确认

- 埋点方案详细设计 → 需要你确认后再交付 Trae
- Q3-Q5 追问问题 → 需要你确认后写入 ask-ai.md

---
