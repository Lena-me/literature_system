-- ============================================================================
-- 阶段一迁移：知识域 + 图谱-论文关联
-- 执行方式: mysql -u root -p literature_system < database/migration_v2_knowledge_domain.sql
-- ============================================================================

USE `literature_system`;

-- 1. 新建知识域表
DROP TABLE IF EXISTS `knowledge_domains`;
CREATE TABLE `knowledge_domains` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `icon` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'folder',
  `parent_domain_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_domain_user` (`user_id`),
  KEY `idx_domain_parent` (`parent_domain_id`),
  CONSTRAINT `fk_domain_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_domain_parent` FOREIGN KEY (`parent_domain_id`) REFERENCES `knowledge_domains` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 新建图谱-论文多对多关联表
DROP TABLE IF EXISTS `knowledge_graph_papers`;
CREATE TABLE `knowledge_graph_papers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `graph_id` bigint NOT NULL,
  `paper_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_graph_paper` (`graph_id`, `paper_id`),
  KEY `idx_kgp_graph` (`graph_id`),
  KEY `idx_kgp_paper` (`paper_id`),
  CONSTRAINT `fk_kgp_graph` FOREIGN KEY (`graph_id`) REFERENCES `knowledge_graphs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_kgp_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. knowledge_graphs 增加 domain_id 字段
ALTER TABLE `knowledge_graphs`
  ADD COLUMN `domain_id` bigint DEFAULT NULL AFTER `user_id`,
  ADD KEY `idx_graph_domain` (`domain_id`),
  ADD CONSTRAINT `fk_graph_domain` FOREIGN KEY (`domain_id`) REFERENCES `knowledge_domains` (`id`) ON DELETE SET NULL;

-- 4. graph_nodes 增加 embedding_vector 字段（实体融合用）
ALTER TABLE `graph_nodes`
  ADD COLUMN `embedding_vector` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER `properties`;

-- 5. 新建探索记录表（知识推荐用）
DROP TABLE IF EXISTS `exploration_tasks`;
CREATE TABLE `exploration_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `domain_id` bigint NOT NULL,
  `concept` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'relation',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'clicked',
  `paper_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_explore_user` (`user_id`),
  KEY `idx_explore_domain` (`domain_id`),
  CONSTRAINT `fk_explore_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_explore_domain` FOREIGN KEY (`domain_id`) REFERENCES `knowledge_domains` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_explore_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE content_items ADD COLUMN bbox JSON NULL