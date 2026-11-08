-- 迁移：events 增加失败原因列（26.11.2）
-- 适用于线上已有 events 表的库；新库直接用 schema.sql（已含该列）。
-- 列可空，历史行 reason 为 NULL，不影响既有查询。

ALTER TABLE events ADD COLUMN reason TEXT;

-- 校验：应看到 reason TEXT
PRAGMA table_info(events);
