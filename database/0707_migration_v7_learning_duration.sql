USE literature_system;

CREATE TABLE IF NOT EXISTS `learning_duration` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `record_date` date NOT NULL,
  `duration_minutes` int NOT NULL DEFAULT '0',
  `week_of_year` varchar(10) NOT NULL,
  `month_of_year` varchar(7) NOT NULL,
  `year` int NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_record_date` (`record_date`),
  KEY `idx_week_of_year` (`week_of_year`),
  KEY `idx_month_of_year` (`month_of_year`),
  KEY `idx_year` (`year`),
  CONSTRAINT `fk_learning_duration_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;