-- 韭菜圈匿名埋点 D1 建表脚本
-- 用法（二选一）：
--   1. Cloudflare 控制台 → Workers & Pages → D1 → 选择数据库 → Console，粘贴执行
--   2. 本地 wrangler：npx wrangler d1 execute jcq-telemetry --file=services/telemetry/schema.sql

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,          -- 客户端事件时间（epoch ms）
  received_at INTEGER NOT NULL, -- 服务端接收时间（epoch ms）
  day TEXT NOT NULL,            -- UTC+8 日历日 YYYY-MM-DD
  event TEXT NOT NULL,          -- 事件名（白名单枚举）
  asset TEXT,                   -- etf / stock
  code TEXT,                    -- 标的代码（如 sh512480）
  name TEXT,                    -- 标的名称（截断 20 字符）
  term TEXT,                    -- 搜索词（截断 24 字符）
  sid TEXT,                     -- 匿名会话 ID（浏览器内随机串，非身份信息）
  country TEXT                  -- CF 提供的国家级粗粒度地域（如 CN）
);

CREATE INDEX IF NOT EXISTS idx_events_day_event ON events(day, event);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
CREATE INDEX IF NOT EXISTS idx_events_term ON events(term);
