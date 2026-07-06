-- Reader / notes / learning-records compatibility fixes
-- Execute:
--   mysql -u paper_user -p literature_system < database/migration_fix_reader_notes_and_learning_records.sql

USE `literature_system`;

-- 1. learning_records.event_type: allow new event names such as session_switch and paper_read.
ALTER TABLE `learning_records`
  MODIFY COLUMN `event_type` VARCHAR(64) NOT NULL;

-- 2. qa_messages: add columns used by current SQLAlchemy model / notebook code.
DROP PROCEDURE IF EXISTS add_column_if_missing;
DELIMITER //
CREATE PROCEDURE add_column_if_missing(
  IN table_name_in VARCHAR(64),
  IN column_name_in VARCHAR(64),
  IN ddl_in TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = table_name_in
      AND COLUMN_NAME = column_name_in
  ) THEN
    SET @ddl = ddl_in;
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END//
DELIMITER ;

CALL add_column_if_missing(
  'qa_messages',
  'reasoning_content',
  'ALTER TABLE `qa_messages` ADD COLUMN `reasoning_content` LONGTEXT NULL COMMENT ''LLM reasoning content'' AFTER `content`'
);

CALL add_column_if_missing(
  'qa_messages',
  'tool_artifacts',
  'ALTER TABLE `qa_messages` ADD COLUMN `tool_artifacts` LONGTEXT NULL COMMENT ''Tool artifacts JSON'' AFTER `reasoning_content`'
);

CALL add_column_if_missing(
  'qa_messages',
  'external_refs',
  'ALTER TABLE `qa_messages` ADD COLUMN `external_refs` LONGTEXT NULL COMMENT ''External references JSON'' AFTER `tool_artifacts`'
);

DROP PROCEDURE IF EXISTS add_column_if_missing;

-- 3. user_paper_notes: create the reader highlight/note table if missing.
CREATE TABLE IF NOT EXISTS `user_paper_notes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `paper_id` bigint NOT NULL,
  `page_number` int NOT NULL,
  `bbox` JSON NOT NULL,
  `selected_text` text NOT NULL,
  `note_content` text DEFAULT NULL,
  `highlight_color` varchar(20) NOT NULL DEFAULT '#FFEB3B',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_paper` (`user_id`, `paper_id`),
  KEY `idx_paper_page` (`paper_id`, `page_number`),
  CONSTRAINT `fk_user_paper_notes_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_user_paper_notes_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
