-- QA 消息思考过程字段（方案 A：与正文分库存储）
-- 执行: mysql -u paper_user -p literature_system < database/migration_v3_qa_reasoning.sql

USE `literature_system`;

ALTER TABLE `qa_messages`
  ADD COLUMN `reasoning_content` TEXT NULL COMMENT 'LLM 推理/思考过程' AFTER `content`;
