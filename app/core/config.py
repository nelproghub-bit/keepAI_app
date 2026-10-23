import os
import secrets
import warnings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# AI Provider Configuration
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")  # options: gemini, openai, anthropic

# Google Gemini Configuration (Primary AI Provider)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID")

# Alternative AI API Configuration (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

# Storage & Database Configuration
CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")
DATABASE_URL = os.getenv("DATABASE_URL")
DB_TYPE = os.getenv(
    "DB_TYPE",
    "postgres" if DATABASE_URL else "mysql",
).lower()  # options: postgres, mysql, mariadb, sqlite
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "keepai")
DB_PATH = os.getenv("DB_PATH", "./data/keepai.db")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# Authentication & Security Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    if ENVIRONMENT == "production":
        raise RuntimeError("JWT_SECRET_KEY must be set in production.")
    JWT_SECRET_KEY = secrets.token_urlsafe(32)
    warnings.warn(
        "JWT_SECRET_KEY is unset; using an ephemeral development key. "
        "Set JWT_SECRET_KEY to preserve sessions across restarts.",
        RuntimeWarning,
        stacklevel=2,
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173,http://localhost:3000,"
    "http://127.0.0.1:5173,http://127.0.0.1:3000"
)
ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]
