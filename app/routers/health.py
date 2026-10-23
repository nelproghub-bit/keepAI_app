from fastapi import APIRouter
from app.core.database import get_database_info
from app.services.gemini_service import ai_service
from app.services.training_service import training_service

router = APIRouter(tags=["System"])

@router.get("/health")
def health():
    return {
        "status": "KeepAI API is running",
        "database": get_database_info()
    }

@router.get("/database-status")
def database_status():
    """Get active database configuration and connection status (MariaDB/MySQL or SQLite)"""
    return get_database_info()

@router.get("/ai-status")
def ai_status():
    return ai_service.get_status()

@router.get("/training-status")
def training_status():
    """Get training dataset integration status"""
    return {
        "dataset_loaded": len(training_service.training_examples) > 0,
        "training_examples": len(training_service.training_examples),
        "task_types": list(training_service.task_patterns.keys()),
        "knowledge_base_files": list(training_service.knowledge_base.keys()),
        "enhanced_features": [
            "Task-specific response patterns",
            "Academic writing styles (Taglish, Professor, Academic)",
            "Conversation memory and context",
            "RAG guidance integration",
            "Educational content generation"
        ]
    }
