-- ============================================================================
-- 补齐缺失的数据库变更：model_configs.is_primary + qa_messages.created_at 索引
-- 执行: mysql -u paper_user -p literature_system < database/0708_migration_v10_model_configs_and_qa_index.sql
-- MySQL 8.0 兼容
-- ============================================================================

USE `literature_system`;

-- 1. model_configs 增加 is_primary 字段（场景路由首选标记）
DROP PROCEDURE IF EXISTS migrate_v10;
DELIMITER //
CREATE PROCEDURE migrate_v10()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'model_configs'
          AND COLUMN_NAME = 'is_primary'
    ) THEN
        ALTER TABLE `model_configs`
          ADD COLUMN `is_primary` TINYINT(1) NOT NULL DEFAULT 0;
    END IF;

    -- 2. qa_messages.created_at 增加索引（配合时间范围查询/分页排序）
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'qa_messages'
          AND INDEX_NAME = 'idx_qa_messages_created_at'
    ) THEN
        ALTER TABLE `qa_messages`
          ADD INDEX `idx_qa_messages_created_at` (`created_at`);
    END IF;
END//
DELIMITER ;

CALL migrate_v10();
DROP PROCEDURE IF EXISTS migrate_v10;
