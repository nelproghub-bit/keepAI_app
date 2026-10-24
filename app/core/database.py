import os
import sqlite3
from typing import Optional, Dict, Any, List
import pymysql
import pymysql.cursors
from app.core.config import (
    DATABASE_URL, DB_TYPE, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_PATH
)

_active_engine = "sqlite"

class PostgresCursorWrapper:
    """Adapt PostgreSQL cursors to the application's qmark placeholder convention."""
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query: str, args=None):
        adapted_query = query.replace("?", "%s")
        if args is not None:
            return self._cursor.execute(adapted_query, args)
        return self._cursor.execute(adapted_query)

    def executemany(self, query: str, args):
        return self._cursor.executemany(query.replace("?", "%s"), args)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        return self._cursor.close()

class PostgresConnectionWrapper:
    """Expose PostgreSQL connections through the database API used by services."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

class MySQLCursorWrapper:
    """Wrapper around PyMySQL DictCursor that converts ? placeholders to %s"""
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query: str, args=None):
        adapted_query = query.replace("?", "%s")
        if args is not None:
            return self._cursor.execute(adapted_query, args)
        return self._cursor.execute(adapted_query)

    def executemany(self, query: str, args):
        adapted_query = query.replace("?", "%s")
        return self._cursor.executemany(adapted_query, args)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        return self._cursor.close()

class MySQLConnectionWrapper:
    """Wrapper around PyMySQL Connection to provide standard cursor and transaction behavior"""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return MySQLCursorWrapper(self._conn.cursor(pymysql.cursors.DictCursor))

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

def _try_get_mysql_connection() -> Optional[MySQLConnectionWrapper]:
    """Attempt connecting to MariaDB / MySQL server"""
    try:
        # First ensure database exists
        admin_conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset="utf8mb4",
            connect_timeout=3
        )
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        admin_conn.commit()
        admin_conn.close()

        # Connect to specific database
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=4,
            autocommit=False
        )
        return MySQLConnectionWrapper(conn)
    except Exception as e:
        print(f"[KeepAI Notice] MySQL/MariaDB connection notice: {e}. Falling back to SQLite.")
        return None

def _get_postgres_connection() -> PostgresConnectionWrapper:
    """Connect to the configured persistent PostgreSQL database."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be set when DB_TYPE=postgres.")

    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        DATABASE_URL,
        connect_timeout=10,
        row_factory=dict_row,
    )
    return PostgresConnectionWrapper(conn)

def _get_sqlite_connection():
    """Fallback to local SQLite database"""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_connection():
    """Get a configured database connection."""
    global _active_engine
    if DB_TYPE in ["postgres", "postgresql"]:
        _active_engine = "postgres"
        return _get_postgres_connection()

    if DB_TYPE in ["mysql", "mariadb"]:
        mysql_conn = _try_get_mysql_connection()
        if mysql_conn:
            _active_engine = "mariadb"
            return mysql_conn
    
    _active_engine = "sqlite"
    return _get_sqlite_connection()

def init_db():
    """Initialize schema tables on PostgreSQL, MariaDB/MySQL, or SQLite."""
    global _active_engine
    conn = get_connection()
    cursor = conn.cursor()

    if _active_engine == "postgres":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(64) UNIQUE NOT NULL,
            email VARCHAR(128) UNIQUE NOT NULL,
            full_name VARCHAR(128) NOT NULL,
            student_id VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP NULL
        )
        """)
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'student'"
        )
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_stats (
            user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            questions_asked INTEGER DEFAULT 0,
            summaries_generated INTEGER DEFAULT 0,
            quizzes_attempted INTEGER DEFAULT 0,
            questions_tested INTEGER DEFAULT 0,
            study_minutes INTEGER DEFAULT 0,
            study_plans TEXT DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            chunks_indexed INTEGER DEFAULT 0,
            char_count INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 1,
            size_bytes BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes BIGINT DEFAULT 0"
        )
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(80),
            description TEXT,
            color VARCHAR(32) DEFAULT '#7D1D1D',
            icon VARCHAR(32) DEFAULT '📁',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute(
            "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS category VARCHAR(80)"
        )
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_documents (
            id VARCHAR(64) PRIMARY KEY,
            workspace_id VARCHAR(64) NOT NULL,
            document_id VARCHAR(64) NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (workspace_id, document_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_activity (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(40) NOT NULL,
            description VARCHAR(255) NOT NULL,
            subject VARCHAR(255),
            duration_seconds INTEGER DEFAULT 0,
            score_percent REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            chunks_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_conversations (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            title VARCHAR(200) NOT NULL,
            teaching_style VARCHAR(32) NOT NULL DEFAULT 'simple',
            course_level VARCHAR(32) NOT NULL DEFAULT 'intermediate',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_messages (
            id VARCHAR(64) PRIMARY KEY,
            conversation_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            role VARCHAR(16) NOT NULL,
            message_order INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tutor_conversations_user_updated ON tutor_conversations(user_id, updated_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tutor_messages_conversation_created ON tutor_messages(conversation_id, created_at)"
        )
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'info',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcement_reads (
            id VARCHAR(64) PRIMARY KEY,
            announcement_id VARCHAR(64) NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
            user_id VARCHAR(64) NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (announcement_id, user_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL,
            p256dh VARCHAR(255) NOT NULL,
            auth_secret VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspace_documents_workspace ON workspace_documents(workspace_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_study_activity_user_created ON study_activity(user_id, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_user ON rag_documents(user_id)"
        )
        conn.commit()
        conn.close()
        print("[KeepAI] Connected to PostgreSQL database.")
    elif _active_engine == "mariadb":
        # MariaDB / MySQL DDL
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(64) UNIQUE NOT NULL,
            email VARCHAR(128) UNIQUE NOT NULL,
            full_name VARCHAR(128) NOT NULL,
            student_id VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'student'"
            )

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_stats (
            user_id VARCHAR(64) PRIMARY KEY,
            questions_asked INT DEFAULT 0,
            summaries_generated INT DEFAULT 0,
            quizzes_attempted INT DEFAULT 0,
            questions_tested INT DEFAULT 0,
            study_minutes INT DEFAULT 0,
            study_plans LONGTEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            chunks_indexed INT DEFAULT 0,
            char_count INT DEFAULT 0,
            page_count INT DEFAULT 1,
            size_bytes BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("SHOW COLUMNS FROM documents LIKE 'size_bytes'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE documents ADD COLUMN size_bytes BIGINT DEFAULT 0")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(80) NULL,
            description TEXT,
            color VARCHAR(32) DEFAULT '#7D1D1D',
            icon VARCHAR(32) DEFAULT '📁',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_workspaces_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("SHOW COLUMNS FROM workspaces LIKE 'category'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE workspaces ADD COLUMN category VARCHAR(80) NULL")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_documents (
            id VARCHAR(64) PRIMARY KEY,
            workspace_id VARCHAR(64) NOT NULL,
            document_id VARCHAR(64) NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_workspace_document (workspace_id, document_id),
            INDEX idx_workspace_documents_workspace (workspace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_activity (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(40) NOT NULL,
            description VARCHAR(255) NOT NULL,
            subject VARCHAR(255),
            duration_seconds INT DEFAULT 0,
            score_percent DOUBLE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_study_activity_user_created (user_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            chunks_json LONGTEXT NOT NULL,
            metadata_json LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rag_documents_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_conversations (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            title VARCHAR(200) NOT NULL,
            teaching_style VARCHAR(32) NOT NULL DEFAULT 'simple',
            course_level VARCHAR(32) NOT NULL DEFAULT 'intermediate',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_tutor_conversations_user_updated (user_id, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_messages (
            id VARCHAR(64) PRIMARY KEY,
            conversation_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            role VARCHAR(16) NOT NULL,
            message_order INT NOT NULL,
            content LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_tutor_messages_conversation_created (conversation_id, created_at),
            INDEX idx_tutor_messages_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'info',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_announcements_active (is_active, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcement_reads (
            id VARCHAR(64) PRIMARY KEY,
            announcement_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_announcement_user_read (announcement_id, user_id),
            INDEX idx_announcement_reads_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh VARCHAR(255) NOT NULL,
            auth_secret VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_push_subscriptions_user (user_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        conn.commit()
        conn.close()
        print(f"[KeepAI] Connected to MariaDB / MySQL database: '{DB_NAME}' at {DB_HOST}:{DB_PORT}")
    else:
        # SQLite DDL
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            student_id TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        """)
        user_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in user_columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'"
            )

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_stats (
            user_id TEXT PRIMARY KEY,
            questions_asked INTEGER DEFAULT 0,
            summaries_generated INTEGER DEFAULT 0,
            quizzes_attempted INTEGER DEFAULT 0,
            questions_tested INTEGER DEFAULT 0,
            study_minutes INTEGER DEFAULT 0,
            study_plans TEXT DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            chunks_indexed INTEGER DEFAULT 0,
            char_count INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 1,
            size_bytes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        document_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(documents)").fetchall()}
        if "size_bytes" not in document_columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN size_bytes INTEGER DEFAULT 0")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            color TEXT DEFAULT '#7D1D1D',
            icon TEXT DEFAULT '📁',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        workspace_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(workspaces)").fetchall()}
        if "category" not in workspace_columns:
            cursor.execute("ALTER TABLE workspaces ADD COLUMN category TEXT")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_documents (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (workspace_id, document_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_activity (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT NOT NULL,
            subject TEXT,
            duration_seconds INTEGER DEFAULT 0,
            score_percent REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            chunks_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            teaching_style TEXT NOT NULL DEFAULT 'simple',
            course_level TEXT NOT NULL DEFAULT 'intermediate',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tutor_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            message_order INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tutor_conversations_user_updated ON tutor_conversations(user_id, updated_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tutor_messages_conversation_created ON tutor_messages(conversation_id, created_at)")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'info',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcement_reads (
            id TEXT PRIMARY KEY,
            announcement_id TEXT NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (announcement_id, user_id)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth_secret TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcements_active ON announcements(is_active, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcement_reads_user ON announcement_reads(user_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_user ON rag_documents(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspace_documents_workspace ON workspace_documents(workspace_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_study_activity_user_created ON study_activity(user_id, created_at)"
        )
        conn.commit()
        conn.close()
        print(f"[KeepAI] Connected to SQLite database: {DB_PATH}")

def get_database_info() -> Dict[str, Any]:
    """Get active database status and configuration"""
    if _active_engine == "postgres":
        return {
            "engine": "POSTGRES",
            "database": "configured database",
            "host": "remote",
            "user": "application",
            "status": "connected"
        }
    return {
        "engine": _active_engine.upper(),
        "database": DB_NAME if _active_engine == "mariadb" else DB_PATH,
        "host": f"{DB_HOST}:{DB_PORT}" if _active_engine == "mariadb" else "local_file",
        "user": DB_USER if _active_engine == "mariadb" else "system",
        "status": "connected"
    }

# Auto-initialize database schema
init_db()
