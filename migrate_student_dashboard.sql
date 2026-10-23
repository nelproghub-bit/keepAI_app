-- ====================================================================
-- KeepAI Student Dashboard Migration Script
-- Adds workspace management and student preferences
-- Safe to run on existing KeepAI database
-- ====================================================================

USE `keepai`;

-- 1. Add role column to users table if it doesn't exist
ALTER TABLE `users` 
ADD COLUMN IF NOT EXISTS `role` VARCHAR(32) NOT NULL DEFAULT 'student' AFTER `password_hash`;

-- 2. Create workspaces table
CREATE TABLE IF NOT EXISTS `workspaces` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT,
    `color` VARCHAR(32) DEFAULT '#4f46e5',
    `icon` VARCHAR(64) DEFAULT '📚',
    `is_active` TINYINT(1) DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_workspaces_user` (`user_id`),
    CONSTRAINT `fk_workspaces_user` FOREIGN KEY (`user_id`)
        REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Create student_preferences table
CREATE TABLE IF NOT EXISTS `student_preferences` (
    `user_id` VARCHAR(64) NOT NULL,
    `theme` VARCHAR(32) DEFAULT 'light',
    `ai_tutor_mode` VARCHAR(32) DEFAULT 'balanced',
    `show_citations` TINYINT(1) DEFAULT 1,
    `enable_notifications` TINYINT(1) DEFAULT 1,
    `default_workspace_id` VARCHAR(64) NULL,
    `preferences` LONGTEXT,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    CONSTRAINT `fk_student_prefs_user` FOREIGN KEY (`user_id`)
        REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Create workspace_documents junction table
CREATE TABLE IF NOT EXISTS `workspace_documents` (
    `workspace_id` VARCHAR(64) NOT NULL,
    `document_id` VARCHAR(64) NOT NULL,
    `added_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`workspace_id`, `document_id`),
    CONSTRAINT `fk_ws_docs_workspace` FOREIGN KEY (`workspace_id`)
        REFERENCES `workspaces` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ws_docs_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Create default workspace for existing demo student
INSERT INTO `workspaces` (`id`, `user_id`, `name`, `description`, `color`, `icon`, `is_active`)
VALUES (
    'workspace_default_arnel',
    'student_arnel',
    'My Main Workspace',
    'Default study workspace for all courses',
    '#4f46e5',
    '📚',
    1
) ON DUPLICATE KEY UPDATE `name`=VALUES(`name`);

-- 6. Create default preferences for existing demo student
INSERT INTO `student_preferences` (`user_id`, `theme`, `ai_tutor_mode`, `show_citations`, `enable_notifications`, `preferences`)
VALUES (
    'student_arnel',
    'light',
    'balanced',
    1,
    1,
    '{"language":"en","timezone":"UTC","study_reminder":true}'
) ON DUPLICATE KEY UPDATE `theme`=VALUES(`theme`);

-- Migration complete!
SELECT 'Student Dashboard migration completed successfully!' AS status;
