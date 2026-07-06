-- 学科层级关系表（LLM 分析生成，用于雷达图知识域覆盖分析）
-- 执行: mysql -u paper_user -p literature_system < database/migration_v7_subject_hierarchy.sql

USE `literature_system`;

CREATE TABLE IF NOT EXISTS `subject_hierarchy` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `paper_id` bigint DEFAULT NULL COMMENT '文献ID',
  `subject_label` varchar(200) NOT NULL COMMENT '原始学科标签',
  `primary_domain` varchar(200) NOT NULL COMMENT '顶级学科（如：计算机科学）',
  `secondary_domain` varchar(200) DEFAULT NULL COMMENT '二级学科（如：人工智能）',
  `tertiary_domain` varchar(200) DEFAULT NULL COMMENT '三级学科（如：深度学习）',
  `domain_path` varchar(500) NOT NULL COMMENT '完整层级路径（如：计算机科学/人工智能/深度学习）',
  `is_core` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否为核心标签（非噪音）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_subject_label` (`subject_label`),
  KEY `idx_primary_domain` (`primary_domain`),
  KEY `idx_secondary_domain` (`secondary_domain`),
  KEY `idx_tertiary_domain` (`tertiary_domain`),
  CONSTRAINT `fk_subject_hierarchy_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_subject_hierarchy_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学科层级关系表（LLM分析生成，用于雷达图）';
