import os
import sqlite3
from typing import Optional, Dict, Any, List
import pymysql
import pymysql.cursors
from app.core.config import (
    DB_TYPE, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_PATH
)

_active_engine = "sqlite"

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
        print(f"⚠️ MySQL/MariaDB connection notice: {e}. Falling back to SQLite.")
        return None

def _get_sqlite_connection():
    """Fallback to local SQLite database"""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_connection():
    """Get active database connection (MariaDB/MySQL preferred, SQLite fallback)"""
    global _active_engine
    if DB_TYPE in ["mysql", "mariadb"]:
        mysql_conn = _try_get_mysql_connection()
        if mysql_conn:
            _active_engine = "mariadb"
            return mysql_conn
    
    _active_engine = "sqlite"
    return _get_sqlite_connection()

def init_db():
    """Initialize schema tables on MariaDB/MySQL or SQLite"""
    global _active_engine
    conn = get_connection()
    cursor = conn.cursor()

    if _active_engine == "mariadb":
        # MariaDB / MySQL DDL
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(64) UNIQUE NOT NULL,
            email VARCHAR(128) UNIQUE NOT NULL,
            full_name VARCHAR(128) NOT NULL,
            student_id VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user (user_id)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        """)

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        conn.close()
        print(f"[KeepAI] Connected to SQLite database: {DB_PATH}")

def get_database_info() -> Dict[str, Any]:
    """Get active database status and configuration"""
    return {
        "engine": _active_engine.upper(),
        "database": DB_NAME if _active_engine == "mariadb" else DB_PATH,
        "host": f"{DB_HOST}:{DB_PORT}" if _active_engine == "mariadb" else "local_file",
        "user": DB_USER if _active_engine == "mariadb" else "system",
        "status": "connected"
    }

# Auto-initialize database schema
init_db()
