-- 合并重复行（保留 id 最小的一条）
UPDATE learning_duration ld
JOIN (
  SELECT user_id, record_date, MIN(id) AS keep_id, SUM(duration_minutes) AS total_min
  FROM learning_duration
  GROUP BY user_id, record_date
  HAVING COUNT(*) > 1
) t ON ld.user_id = t.user_id AND ld.record_date = t.record_date
SET ld.duration_minutes = t.total_min
WHERE ld.id = t.keep_id;

DELETE ld FROM learning_duration ld
JOIN (
  SELECT user_id, record_date, MIN(id) AS keep_id
  FROM learning_duration
  GROUP BY user_id, record_date
) t ON ld.user_id = t.user_id AND ld.record_date = t.record_date
WHERE ld.id <> t.keep_id;

ALTER TABLE learning_duration
  ADD UNIQUE KEY uk_learning_duration_user_date (user_id, record_date);