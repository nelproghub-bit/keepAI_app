-- ====================================================================
-- KeepAI Academic Intelligence Platform
-- MySQL / MariaDB Database Schema
-- Database: keepai
-- ====================================================================

CREATE DATABASE IF NOT EXISTS `keepai`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `keepai`;

-- 1. Students / Users Table
CREATE TABLE IF NOT EXISTS `users` (
    `id` VARCHAR(64) NOT NULL,
    `username` VARCHAR(64) NOT NULL,
    `email` VARCHAR(128) NOT NULL,
    `full_name` VARCHAR(128) NOT NULL,
    `student_id` VARCHAR(64) NOT NULL DEFAULT 'Student',
    `password_hash` VARCHAR(255) NOT NULL,
    `role` VARCHAR(32) NOT NULL DEFAULT 'student',
    `teaching_style` VARCHAR(32) NOT NULL DEFAULT 'simple',
    `course_level` VARCHAR(32) NOT NULL DEFAULT 'intermediate',
    `theme_preference` VARCHAR(16) NULL DEFAULT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `last_login` TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_username` (`username`),
    UNIQUE KEY `uq_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `admin_identity_audit_log` (
    `id` VARCHAR(64) NOT NULL,
    `admin_user_id` VARCHAR(64) NOT NULL,
    `target_user_id` VARCHAR(64) NOT NULL,
    `action` VARCHAR(64) NOT NULL,
    `changes_json` LONGTEXT NOT NULL,
    `reason` TEXT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_identity_audit_target` (`target_user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Student Learning Progress & Academic Stats
CREATE TABLE IF NOT EXISTS `student_stats` (
    `user_id` VARCHAR(64) NOT NULL,
    `questions_asked` INT NOT NULL DEFAULT 0,
    `summaries_generated` INT NOT NULL DEFAULT 0,
    `quizzes_attempted` INT NOT NULL DEFAULT 0,
    `questions_tested` INT NOT NULL DEFAULT 0,
    `study_minutes` INT NOT NULL DEFAULT 0,
    `study_plans` LONGTEXT NULL,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
    CONSTRAINT `fk_student_stats_user` FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Document Library & Metadata Table
CREATE TABLE IF NOT EXISTS `documents` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `filename` VARCHAR(255) NOT NULL,
    `chunks_indexed` INT NOT NULL DEFAULT 0,
    `char_count` INT NOT NULL DEFAULT 0,
    `page_count` INT NOT NULL DEFAULT 1,
    `size_bytes` BIGINT NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_documents_user` (`user_id`),
    CONSTRAINT `fk_documents_user` FOREIGN KEY (`user_id`)
        REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Seed Default Student (arnel / password123)
-- Password hash is salted bcrypt for 'password123'
INSERT INTO `users` (`id`, `username`, `email`, `full_name`, `student_id`, `password_hash`)
VALUES (
    'student_arnel',
    'arnel',
    'arnel.gubi@university.edu',
    'Arnel Gubi',
    'BSIT 412',
    '$2b$12$NqB80q29q.b80q29q.b80e81GqT84qO4u8qH5yvN1g0kM.yQc0qeq'
) ON DUPLICATE KEY UPDATE `username`=`username`;

INSERT INTO `student_stats` (`user_id`, `questions_asked`, `summaries_generated`, `quizzes_attempted`, `questions_tested`, `study_minutes`, `study_plans`)
VALUES (
    'student_arnel',
    3,
    2,
    1,
    5,
    45,
    '["Database Normalization", "AI Architecture"]'
) ON DUPLICATE KEY UPDATE `user_id`=`user_id`;


-- 4. Student Workspaces Table
CREATE TABLE IF NOT EXISTS `workspaces` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `name` VARCHAR(255) NOT NULL,
    `category` VARCHAR(80) NULL,
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

-- 5. Student Preferences Table
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

-- 6. Workspace Documents Junction Table
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

-- 7. Student Progress Activity
CREATE TABLE IF NOT EXISTS `study_activity` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `event_type` VARCHAR(40) NOT NULL,
    `description` VARCHAR(255) NOT NULL,
    `subject` VARCHAR(255) NULL,
    `duration_seconds` INT DEFAULT 0,
    `score_percent` DOUBLE NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_study_activity_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. AI Tutor chat history (scoped to each student account)
CREATE TABLE IF NOT EXISTS `tutor_conversations` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `title` VARCHAR(200) NOT NULL,
    `teaching_style` VARCHAR(32) NOT NULL DEFAULT 'simple',
    `course_level` VARCHAR(32) NOT NULL DEFAULT 'intermediate',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_tutor_conversations_user_updated` (`user_id`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `tutor_messages` (
    `id` VARCHAR(64) NOT NULL,
    `conversation_id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `role` VARCHAR(16) NOT NULL,
    `message_order` INT NOT NULL,
    `content` LONGTEXT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_tutor_messages_conversation_created` (`conversation_id`, `created_at`),
    KEY `idx_tutor_messages_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Creator announcements shown in student dashboards
CREATE TABLE IF NOT EXISTS `announcements` (
    `id` VARCHAR(64) NOT NULL,
    `title` VARCHAR(200) NOT NULL,
    `message` TEXT NOT NULL,
    `kind` VARCHAR(20) NOT NULL DEFAULT 'info',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_by` VARCHAR(64) NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_announcements_active` (`is_active`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `announcement_reads` (
    `id` VARCHAR(64) NOT NULL,
    `announcement_id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `read_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_announcement_user_read` (`announcement_id`, `user_id`),
    KEY `idx_announcement_reads_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `push_subscriptions` (
    `id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `endpoint` TEXT NOT NULL,
    `p256dh` VARCHAR(255) NOT NULL,
    `auth_secret` VARCHAR(255) NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_push_subscriptions_user` (`user_id`),
    CONSTRAINT `fk_push_subscriptions_user` FOREIGN KEY (`user_id`)
        REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Seed Default Workspace for Demo Student
INSERT INTO `workspaces` (`id`, `user_id`, `name`, `description`, `color`, `icon`, `is_active`)
VALUES (
    'workspace_default_arnel',
    'student_arnel',
    'My Main Workspace',
    'Default study workspace for all courses',
    '#4f46e5',
    '📚',
    1
) ON DUPLICATE KEY UPDATE `name`=`name`;
