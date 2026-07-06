-- QA 消息拓展阅读/外部溯源持久化
-- 执行: mysql -u paper_user -p literature_system < database/migration_v5_qa_external_refs.sql

USE `literature_system`;

ALTER TABLE `qa_messages`
  ADD COLUMN `external_refs` JSON NULL COMMENT '拓展阅读/外部溯源链接' AFTER `tool_artifacts`;
