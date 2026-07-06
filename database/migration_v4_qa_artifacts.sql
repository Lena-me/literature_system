-- QA 消息工具产物持久化（报告/图谱/对比卡片）
-- 执行: mysql -u paper_user -p literature_system < database/migration_v4_qa_artifacts.sql

USE `literature_system`;

ALTER TABLE `qa_messages`
  ADD COLUMN `tool_artifacts` JSON NULL COMMENT 'LangGraph 工具产物（report/graph/comparison）' AFTER `reasoning_content`;
