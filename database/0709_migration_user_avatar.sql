-- 用户头像 URL
ALTER TABLE users
  ADD COLUMN avatar_url VARCHAR(255) NULL AFTER quota_json;
