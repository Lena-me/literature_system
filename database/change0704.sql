-- 表名 ： learning_records
-- 字段 ： event_type
-- 修改 ：字段长度从 VARCHAR(50) 扩大到 VARCHAR(100)

-- 修改原因
-- 新增学习记录功能，事件类型有： session_switch 、 ai_message 、 paper_read 、 paper_upload 、 paper_open ，原字段长度不够导致数据被截断报错。
ALTER TABLE learning_records MODIFY COLUMN event_type VARCHAR(100);
