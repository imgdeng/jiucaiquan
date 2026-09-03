# 韭菜圈匿名埋点配置手册：Cloudflare D1 + Pages Functions

> 适用场景：埋点代码已随 `b87bfe6` 上线（前端 `sendBeacon` → `functions/api/track` → D1），但数据需要在 Cloudflare 控制台做一次性绑定配置后才会真正落库。
> 目标：让 `https://jiucaiquan.com` 的用户行为（搜索、计算、复制等）写入 D1 数据库，并能用带密钥的报表链接查看。
> 预计耗时：10 分钟。配置前埋点接口静默返回 204，不影响网站任何功能。

---

## 0. 这套东西是什么（先建立全景）

```
用户浏览器
  │  页面访问 / 搜索 / 选标的 / 计算 / 复制 / 切 tab / 自选
  ▼
navigator.sendBeacon("/api/track", 事件JSON)     ← apps/web/src/lib/telemetry.ts
  │
  ▼
Cloudflare Pages Function（边缘节点，随 git push 自动部署）
  │  functions/api/track.ts   字段白名单收敛 → 写入
  │  functions/api/report.ts  聚合查询（需 KEY）
  ▼
Cloudflare D1 数据库（边缘 SQLite，免费额度）
  表：events   库名：jcq-telemetry
```

**两个必须配对的东西**：

| 配置项 | 在哪配 | 变量名 | 作用 |
|---|---|---|---|
| D1 数据库绑定 | Pages 项目 → Settings → Bindings | `DB` | 让 Function 能写数据库 |
| 报表访问密钥 | Pages 项目 → Settings → Variables and secrets | `REPORT_KEY` | 保护报表接口不被陌生人查看 |

> ⚠️ 变量名大小写必须完全一致（`DB`、`REPORT_KEY`），代码里按这两个名字读取。

---

## 1. 创建 D1 数据库

1. 登录 [dash.cloudflare.com](https://dash.cloudflare.com)
2. 左侧导航：**Storage & databases** → **D1 SQL Database**（或在 Compute → Workers & Pages 页面找 D1 入口）
3. 点 **Create database**
4. Database name 填：`jcq-telemetry`
5. 区域默认即可，点 **Create**

创建后进入数据库页面，URL 形如：
`dash.cloudflare.com/.../workers/d1/databases/<数据库ID>`

---

## 2. 建表（D1 Console 执行 SQL）

1. 在 `jcq-telemetry` 数据库页面，点顶部 **Console** 标签
2. 在底部输入框粘贴下面这段 SQL（**注意：必须用这个无注释版**，原因见文末踩坑 ①）：

```sql
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  day TEXT NOT NULL,
  event TEXT NOT NULL,
  asset TEXT,
  code TEXT,
  name TEXT,
  term TEXT,
  sid TEXT,
  country TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_day_event ON events(day, event);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
CREATE INDEX IF NOT EXISTS idx_events_term ON events(term);
```

3. 点蓝色 **Execute** 按钮
4. 看到 **`This query successfully executed.`** 即成功
5. 验证：输入 `/tables` 回车，应列出 `events` 表（旁边的 `sqlite_sequence` 是 SQLite 自动生成的，正常）
6. 再验证：输入 `SELECT COUNT(*) FROM events;` 回车，返回 `0`（空表，正常）

> 如果多语句一次执行报错，就把 `CREATE TABLE` 和三条 `CREATE INDEX` 分成四次粘贴执行，效果相同。

---

## 3. 把 D1 绑定到 Pages 项目

1. 左侧导航：**Compute** → **Workers & Pages**
2. 点 Pages 项目 **`jiucaiquan`**（注意是 Pages 项目，不是 D1）
3. 顶部标签点 **Settings**，页面停在 **Production** 环境（URL 末尾是 `settings/production`）
4. 找到 **Bindings** 区块（标题下方小字：Define the set of resources available to your Pages Functions）
5. 点右侧 **＋ Add**
6. 在弹出的右侧抽屉里：
   - **Variable name**：填 `DB`
   - **D1 database**：下拉选 `jcq-telemetry`
7. 点 **Save**

保存后 Bindings 表格里应出现一行：`D1 database ｜ DB ｜ jcq-telemetry`。

---

## 4. 设置报表访问密钥（REPORT_KEY）

1. 仍在 Settings 页面，找到 Bindings **上方**的 **Variables and secrets** 区块
   （标题下方小字：Define the text, secret or build variables for your project）
2. 点右侧 **＋ Add**
3. 出现一行三个输入框，依次填：
   - **Type**：保持 **Text**（明文即可；它只保护匿名统计报表）
   - **Name**：`REPORT_KEY`
   - **Value**：你自己定的密钥字符串，例如 `jcq-2026-9f3k7d2x`
     - 建议：字母+数字+短横线，12 位以上，不要用网站密码
     - **务必记下来**，看报表时要拼在 URL 里
4. 点该行外侧的保存（页面会自动保存或出现 Save 按钮）

保存后 Variables and secrets 表格里应出现：`Text ｜ REPORT_KEY ｜ jcq-2026-...`。

> 界面如果是 Production / Preview 两列布局，变量加在 **Production** 列即可，Preview 不用管。

---

## 5. 重新部署让绑定生效（必做，最容易漏）

绑定和环境变量**只对新部署生效**，必须手动触发一次：

1. 项目顶部切到 **Deployments** 标签
2. 在 **All deployments** 列表找到最上面一条（最新 commit，如 `b87bfe6 feat(telemetry)...`）
3. 点该行最右侧的 **⋯**（三个点）
4. 选 **Retry deployment**
5. 等 1-2 分钟，状态变绿色 ✓
6. （可选）点 **Details** 看构建日志，确认出现这两行：
   - `Found Functions directory at /functions. Uploading.`
   - `Success! Your site was deployed!`

---

## 6. 验证全链路（3 分钟）

### 6.1 在网站上产生几个真实事件

1. 浏览器打开 `https://jiucaiquan.com/tools/condition-order/`
2. 操作：搜索框输入"半导体" → 点一个搜索结果 → 切到"股票"tab 再切回 → 点"复制条件单文案" → 点"加入自选"
3. 等约 30 秒

### 6.2 在 D1 Console 查数据

回到 D1 数据库 **Console**，执行：

```sql
SELECT event, COUNT(*) FROM events GROUP BY event;
```

预期看到类似结果（数字 ≥ 1 即成功）：

| event | COUNT(*) |
|---|---|
| calculate | 1 |
| page_view | 1 |
| search | 3 |
| select_quote | 1 |
| watch_add | 1 |

### 6.3 打开在线报表

浏览器访问（把 `<你的KEY>` 换成第 4 步设的值）：

```
https://jiucaiquan.com/api/report?key=<你的KEY>&format=html
```

- 看到 HTML 表格（事件漏斗 / 热门搜索词 Top20 / 热门标的 / 地域分布）→ **全部完成** ✅
- 不加 `format=html` 返回 JSON（适合程序读取）
- 可选参数：`&days=7` 看近 7 天（默认 30 天，最大 90）

---

## 7. 日常怎么用

### 7.1 两个收藏级地址

| 用途 | 地址 |
|---|---|
| 可视化报表（浏览器看） | `https://jiucaiquan.com/api/report?key=<你的KEY>&format=html` |
| JSON 数据（接脚本/表格） | `https://jiucaiquan.com/api/report?key=<你的KEY>&days=30` |

### 7.2 D1 Console 常用查询

```sql
-- 今天的事件概况
SELECT event, COUNT(*) AS c, COUNT(DISTINCT sid) AS uv
FROM events WHERE day = date('now','+8 hours') GROUP BY event ORDER BY c DESC;

-- 最近 7 天热门搜索词
SELECT term, COUNT(*) AS c FROM events
WHERE event = 'search' AND term IS NOT NULL
GROUP BY term ORDER BY c DESC LIMIT 20;

-- 最近 7 天被复制最多的标的
SELECT code, name, COUNT(*) AS copies FROM events
WHERE event = 'copy' AND code IS NOT NULL
GROUP BY code ORDER BY copies DESC LIMIT 20;

-- 每天的独立用户数
SELECT day, COUNT(DISTINCT sid) AS uv FROM events GROUP BY day ORDER BY day DESC;
```

### 7.3 事件与字段说明

| 事件名 | 触发时机 |
|---|---|
| `page_view` | 打开计算器页面（每次会话 1 次） |
| `search` | 搜索框输入（800ms 防抖，连续相同词只记 1 次） |
| `select_quote` | 点击搜索结果自动填充行情 |
| `calculate` | 产生有效计算结果（同一标的只记 1 次，手动输入归并为 manual） |
| `copy` | 点击"复制条件单文案"成功 |
| `asset_switch` | ETF / 股票 tab 切换 |
| `watch_add` / `watch_remove` | 加入 / 移出自选 |

字段：`day`（UTC+8 日期）、`asset`（etf/stock）、`code`（标的代码）、`name`（标的名，截 20 字）、`term`（搜索词，截 24 字）、`sid`（浏览器随机匿名 ID，非身份信息）、`country`（国家级地域，如 CN）。
**不采集**：IP、UA、完整 URL、姓名/邮箱等身份信息。

---

## 8. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 网站正常但 `events` 表一直是空的 | D1 绑定没生效 | 检查第 3 步变量名是否严格为 `DB`；重做第 5 步重新部署 |
| 报表返回 `403 {"error":"unauthorized"}` | KEY 不对 | 检查 URL 里 `key=` 与 Variables 里的 `REPORT_KEY` 完全一致 |
| 报表返回 `404 {"error":"report not configured"}` | `REPORT_KEY` 没配或没部署 | 重做第 4、5 步 |
| 报表返回 `503 D1 binding 'DB' not found` | D1 绑定缺失 | 重做第 3、5 步 |
| 报表能打开但数据全是 0 | 绑定刚生效还没数据 | 在计算器页操作几下，等 30 秒再刷新 |
| Console 报 `Requests without any query are not supported` | 见踩坑 ① | 用第 2 步的无注释 SQL 重新执行 |
| 部署日志里没有 `Found Functions directory` | 部署的代码版本不含 `functions/` | 确认最新 commit 已 push（`git log` 含 `feat(telemetry)`） |

### 踩坑 ①：SQL 注释导致空查询

D1 Console 粘贴时换行可能被压平。SQL 中 `--` 是"注释到行尾"，一旦整条被压成一行，开头的 `-- 中文注释` 会把**后面所有建表语句全部注释掉**，控制台收到空查询就报 `Requests without any query are not supported`。
**解决**：一律使用本手册第 2 步的无注释版 SQL；建表脚本原件保留在仓库 `services/telemetry/schema.sql`（供 wrangler 命令行使用，含注释无妨）。

### 踩坑 ②：改了绑定但数据不进来

Bindings / Variables 的保存提示 *"This change will take effect on the next deployment"*——不重新部署就不生效。必须做第 5 步 Retry deployment。

### 安全提示

- `REPORT_KEY` 是报表入口的唯一凭证，不要贴在公开场合；泄露后直接在 Variables and secrets 里改值并重新部署即可。
- 埋点不涉及敏感数据，但 D1 数据库不要绑定到任何其他 Worker。

---

## 9. 关键信息汇总

| 项目 | 值 |
|---|---|
| D1 数据库名 | `jcq-telemetry` |
| 表名 | `events` |
| 建表脚本 | 仓库 `services/telemetry/schema.sql` |
| D1 绑定变量名 | `DB`（Pages → Settings → Bindings） |
| 报表密钥变量名 | `REPORT_KEY`（Pages → Settings → Variables and secrets） |
| 埋点接收接口 | `POST https://jiucaiquan.com/api/track`（自动调用，无需管） |
| 报表地址 | `https://jiucaiquan.com/api/report?key=<KEY>&format=html` |
| 生效方式 | 配置后必须 **Retry deployment** |
