CREATE DATABASE  IF NOT EXISTS `literature_system` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `literature_system`;
-- MySQL dump 10.13  Distrib 8.0.42, for Win64 (x86_64)
--
-- Host: localhost    Database: literature_system
-- ------------------------------------------------------
-- Server version	8.0.42

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint DEFAULT NULL,
  `operation_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `operation_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `operation_result` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `risk_flag` tinyint NOT NULL DEFAULT '0',
  `module` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_operation_type` (`operation_type`),
  CONSTRAINT `fk_audit_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `categories`
--

DROP TABLE IF EXISTS `categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `categories` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `fk_category_parent` (`parent_id`),
  CONSTRAINT `fk_category_parent` FOREIGN KEY (`parent_id`) REFERENCES `categories` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_category_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `comparison_analyses`
--

DROP TABLE IF EXISTS `comparison_analyses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `comparison_analyses` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `literature_ids` json NOT NULL COMMENT '对比文献ID列表',
  `result` json DEFAULT NULL COMMENT '对比结果（差异分析、表格等）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  CONSTRAINT `fk_compare_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `content_items`
--

DROP TABLE IF EXISTS `content_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `content_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `item_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'paragraph/heading/abstract/figure_caption/table/formula/footnote/list 等',
  `level` tinyint DEFAULT NULL COMMENT '标题层级，非标题为NULL',
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `page_number` smallint DEFAULT NULL,
  `order_index` int NOT NULL DEFAULT '0',
  `parent_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_item_type` (`item_type`),
  KEY `idx_parent_id` (`parent_id`),
  CONSTRAINT `fk_content_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_content_parent` FOREIGN KEY (`parent_id`) REFERENCES `content_items` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `figures_tables`
--

DROP TABLE IF EXISTS `figures_tables`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `figures_tables` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `type` enum('figure','table') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `caption` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `page_number` smallint DEFAULT NULL,
  `image_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `extracted_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '表格解析文本',
  `order_index` int NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_paper_id` (`paper_id`),
  CONSTRAINT `fk_figtab_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `graph_edges`
--

DROP TABLE IF EXISTS `graph_edges`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `graph_edges` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `graph_id` bigint NOT NULL,
  `source_node_id` bigint NOT NULL,
  `target_node_id` bigint NOT NULL,
  `relation_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'uses, evaluates, proposes...',
  `properties` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_graph_id` (`graph_id`),
  KEY `idx_source` (`source_node_id`),
  KEY `idx_target` (`target_node_id`),
  CONSTRAINT `fk_edge_graph` FOREIGN KEY (`graph_id`) REFERENCES `knowledge_graphs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_edge_source` FOREIGN KEY (`source_node_id`) REFERENCES `graph_nodes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_edge_target` FOREIGN KEY (`target_node_id`) REFERENCES `graph_nodes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `graph_nodes`
--

DROP TABLE IF EXISTS `graph_nodes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `graph_nodes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `graph_id` bigint NOT NULL,
  `entity_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'method/task/dataset/metric/author/paper',
  `name` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `properties` json DEFAULT NULL COMMENT '节点详情',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_graph_id` (`graph_id`),
  CONSTRAINT `fk_node_graph` FOREIGN KEY (`graph_id`) REFERENCES `knowledge_graphs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `knowledge_graphs`
--

DROP TABLE IF EXISTS `knowledge_graphs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `knowledge_graphs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `paper_id` bigint DEFAULT NULL COMMENT '基于的单篇文献',
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_paper_id` (`paper_id`),
  CONSTRAINT `fk_graph_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_graph_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `learning_records`
--

DROP TABLE IF EXISTS `learning_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `learning_records` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `paper_id` bigint DEFAULT NULL,
  `event_type` enum('ask','highlight_note','generate_report','generate_kg','change_reading_status','study_session') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_data` json DEFAULT NULL COMMENT '详情（笔记内容、高亮位置、旧新状态等）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_event_type` (`event_type`),
  CONSTRAINT `fk_learn_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_learn_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `model_call_stats`
--

DROP TABLE IF EXISTS `model_call_stats`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_call_stats` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `model_id` bigint NOT NULL,
  `date` date NOT NULL,
  `total_calls` bigint NOT NULL DEFAULT '0',
  `success_count` bigint NOT NULL DEFAULT '0',
  `total_tokens` bigint DEFAULT NULL COMMENT 'LLM专用',
  `avg_latency_ms` float DEFAULT NULL,
  `p95_latency_ms` float DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_date` (`model_id`,`date`),
  CONSTRAINT `fk_stat_model` FOREIGN KEY (`model_id`) REFERENCES `model_configs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `model_configs`
--

DROP TABLE IF EXISTS `model_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_configs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `model_type` enum('parse','vector','reranker','llm') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scenario` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'default' COMMENT '使用场景：default/qa/report/parsing等',
  `model_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `api_endpoint` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `config_json` json DEFAULT NULL,
  `is_active` tinyint NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_model_configs_scenario` (`scenario`),
  KEY `ix_model_configs_type_scenario_active` (`model_type`,`scenario`,`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `operation_stats`
--

DROP TABLE IF EXISTS `operation_stats`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `operation_stats` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `stat_date` date NOT NULL,
  `registered_users` int DEFAULT '0',
  `dau` int DEFAULT '0',
  `total_uploaded` int DEFAULT '0',
  `total_parsed` int DEFAULT '0',
  `total_qa_calls` int DEFAULT '0',
  `vector_db_total` bigint DEFAULT '0',
  `feature_usage_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_stat_date` (`stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `paper_extracted_info`
--

DROP TABLE IF EXISTS `paper_extracted_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `paper_extracted_info` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `title` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `authors` json DEFAULT NULL COMMENT '如[{"name":"...","affiliation":"..."}]',
  `abstract` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `keywords` json DEFAULT NULL,
  `research_question` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `method` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `experiment_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `main_results` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `innovations` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `limitations` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `future_work` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_paper_id` (`paper_id`),
  CONSTRAINT `fk_extract_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `papers`
--

DROP TABLE IF EXISTS `papers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `papers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `original_filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` int NOT NULL DEFAULT '0' COMMENT '字节',
  `file_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `object_key` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'MinIO对象键',
  `upload_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `parse_status` enum('uploaded','queued','parsing','extracting','vectorizing','indexed','completed','failed','deleted') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'uploaded',
  `title` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `authors` json DEFAULT NULL,
  `keywords` json DEFAULT NULL,
  `subject_labels` json DEFAULT NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `category_id` bigint DEFAULT NULL,
  `doi` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `publication_year` smallint DEFAULT NULL,
  `journal_conf` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint NOT NULL DEFAULT '0' COMMENT '软删除标记：0-正常, 1-已删除',
  `deleted_at` datetime DEFAULT NULL COMMENT '执行软删除的时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_parse_status` (`parse_status`),
  KEY `idx_object_key` (`object_key`),
  KEY `idx_category_id` (`category_id`),
  KEY `idx_is_deleted` (`is_deleted`),
  FULLTEXT KEY `ft_title_keywords` (`title`,`notes`),
  CONSTRAINT `fk_paper_category` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_paper_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `parse_tasks`
--

DROP TABLE IF EXISTS `parse_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `parse_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `task_type` enum('document_parse','info_extraction','vectorization') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('queued','running','completed','failed','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `priority` tinyint NOT NULL DEFAULT '5',
  `queue_position` int DEFAULT NULL,
  `start_time` datetime DEFAULT NULL,
  `end_time` datetime DEFAULT NULL,
  `duration_ms` int DEFAULT NULL,
  `error_log` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `retry_count` tinyint NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_task_type` (`task_type`),
  CONSTRAINT `fk_task_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_task_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `qa_message_sources`
--

DROP TABLE IF EXISTS `qa_message_sources`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `qa_message_sources` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `message_id` bigint NOT NULL COMMENT 'assistant消息ID',
  `chunk_id` bigint DEFAULT NULL,
  `paper_id` bigint DEFAULT NULL COMMENT '冗余，便于快速查询',
  `section_title` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `page_number` smallint DEFAULT NULL,
  `snippet` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '相关文本片段',
  `similarity_score` float DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_message_id` (`message_id`),
  KEY `idx_chunk_id` (`chunk_id`),
  KEY `idx_paper_id` (`paper_id`),
  CONSTRAINT `fk_source_chunk` FOREIGN KEY (`chunk_id`) REFERENCES `text_chunks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_source_message` FOREIGN KEY (`message_id`) REFERENCES `qa_messages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_source_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `qa_messages`
--

DROP TABLE IF EXISTS `qa_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `qa_messages` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `session_id` bigint NOT NULL,
  `role` enum('user','assistant') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  CONSTRAINT `fk_message_session` FOREIGN KEY (`session_id`) REFERENCES `qa_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `qa_session_papers`
--

DROP TABLE IF EXISTS `qa_session_papers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `qa_session_papers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `session_id` bigint NOT NULL,
  `paper_id` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_paper` (`session_id`,`paper_id`) COMMENT '防止同一会话重复绑定同一篇文献',
  KEY `idx_paper_id` (`paper_id`),
  CONSTRAINT `fk_qsp_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_qsp_session` FOREIGN KEY (`session_id`) REFERENCES `qa_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问答会话与多文献关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `qa_sessions`
--

DROP TABLE IF EXISTS `qa_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `qa_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `title` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  CONSTRAINT `fk_session_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `reports`
--

DROP TABLE IF EXISTS `reports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reports` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `paper_id` bigint NOT NULL,
  `title` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `content` json NOT NULL COMMENT '研读报告结构化内容',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_paper_id` (`paper_id`),
  CONSTRAINT `fk_report_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_report_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `reproducibility_guides`
--

DROP TABLE IF EXISTS `reproducibility_guides`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reproducibility_guides` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `guide_content` json NOT NULL COMMENT '步骤、环境、参数、注意事项等',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_user_id` (`user_id`),
  CONSTRAINT `fk_repguide_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_repguide_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `system_logs`
--

DROP TABLE IF EXISTS `system_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `level` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `stack_trace` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exception_type` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logged_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_level` (`level`),
  KEY `idx_logged_at` (`logged_at`),
  KEY `idx_trace_id` (`trace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `task_scheduler_config`
--

DROP TABLE IF EXISTS `task_scheduler_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_scheduler_config` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `max_concurrent_tasks` int NOT NULL DEFAULT '10',
  `per_user_concurrent` int NOT NULL DEFAULT '3',
  `timeout_seconds` int NOT NULL DEFAULT '3600',
  `alert_rules` json DEFAULT NULL,
  `backup_engine_config` json DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `text_chunks`
--

DROP TABLE IF EXISTS `text_chunks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `text_chunks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` bigint NOT NULL,
  `section_id` bigint DEFAULT NULL COMMENT '所属content_items.id',
  `chunk_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '分块文本内容（备查）',
  `page_number` smallint DEFAULT NULL,
  `start_position` int DEFAULT NULL,
  `end_position` int DEFAULT NULL,
  `chunk_size` int DEFAULT NULL COMMENT '字符数',
  `overlap_length` int DEFAULT NULL,
  `vector_dim` smallint DEFAULT NULL COMMENT '向量维度',
  `vectorization_status` enum('pending','running','completed','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `embedding_model_id` bigint DEFAULT NULL COMMENT '生成此向量的 Embedding 模型ID',
  `vector_id_in_vdb` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '向量库中的记录ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_section_id` (`section_id`),
  KEY `idx_vector_status` (`vectorization_status`),
  KEY `idx_vector_id` (`vector_id_in_vdb`),
  KEY `idx_embedding_model` (`embedding_model_id`),
  CONSTRAINT `fk_chunk_model` FOREIGN KEY (`embedding_model_id`) REFERENCES `model_configs` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_chunk_paper` FOREIGN KEY (`paper_id`) REFERENCES `papers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_chunk_section` FOREIGN KEY (`section_id`) REFERENCES `content_items` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `role` enum('researcher','admin') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'researcher',
  `status` enum('active','disabled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `last_login_at` datetime DEFAULT NULL,
  `last_login_ip` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `paper_upload_count` int NOT NULL DEFAULT '0' COMMENT '文献上传数量',
  `report_generate_count` int NOT NULL DEFAULT '0' COMMENT '报告生成数量',
  `quota_json` json DEFAULT NULL COMMENT '资源配额配置',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  UNIQUE KEY `uk_email` (`email`),
  UNIQUE KEY `uk_phone` (`phone`),
  KEY `idx_status` (`status`),
  KEY `idx_role` (`role`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vector_backups`
--

DROP TABLE IF EXISTS `vector_backups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vector_backups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `backup_type` enum('manual','auto') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `backup_time` datetime NOT NULL,
  `file_size_mb` float DEFAULT NULL,
  `file_location` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `retention_count` tinyint DEFAULT NULL,
  `status` enum('in_progress','completed','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'in_progress',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vector_db_snapshots`
--

DROP TABLE IF EXISTS `vector_db_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vector_db_snapshots` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `total_vectors` bigint DEFAULT NULL,
  `storage_used_mb` float DEFAULT NULL,
  `index_count` int DEFAULT NULL,
  `shard_count` int DEFAULT NULL,
  `avg_retrieve_ms` float DEFAULT NULL,
  `p95_retrieve_ms` float DEFAULT NULL,
  `success_rate` float DEFAULT NULL,
  `recall_rate` float DEFAULT NULL,
  `health_score` tinyint DEFAULT NULL,
  `recorded_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vector_restore_tasks`
--

DROP TABLE IF EXISTS `vector_restore_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vector_restore_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `backup_id` bigint NOT NULL,
  `restore_progress` tinyint DEFAULT '0',
  `status` enum('in_progress','completed','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'in_progress',
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `error_log` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  KEY `idx_backup_id` (`backup_id`),
  CONSTRAINT `fk_restore_backup` FOREIGN KEY (`backup_id`) REFERENCES `vector_backups` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-27 14:54:32
