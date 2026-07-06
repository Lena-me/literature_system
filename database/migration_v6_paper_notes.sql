-- 文献阅读划词笔记
-- 执行: mysql -u paper_user -p literature_system < database/migration_v6_paper_notes.sql

USE `literature_system`;

CREATE TABLE IF NOT EXISTS `user_paper_notes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `paper_id` bigint NOT NULL COMMENT '文献ID',
  `page_number` int NOT NULL COMMENT 'PDF页码',
  `bbox` json NOT NULL COMMENT '归一化矩形数组 [{left,top,width,height}, ...]',
  `selected_text` text NOT NULL COMMENT '划选原文',
  `note_content` text DEFAULT NULL COMMENT '批注内容',
  `highlight_color` varchar(20) NOT NULL DEFAULT '#FFEB3B' COMMENT '高亮颜色',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_paper` (`user_id`, `paper_id`),
  KEY `idx_paper_page` (`paper_id`, `page_number`),
  CONSTRAINT `fk_note_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_note_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文献阅读笔记表';
