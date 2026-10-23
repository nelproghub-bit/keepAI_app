from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services.progress_service import get_progress, record_activity

router = APIRouter(tags=["Progress"])


class ProgressActivityRequest(BaseModel):
    event_type: str = Field(pattern="^(study_time|quiz_completed|flashcard_mastered)$")
    description: Optional[str] = Field(default=None, max_length=255)
    subject: Optional[str] = Field(default=None, max_length=255)
    duration_seconds: int = Field(default=0, ge=0, le=90)
    score_percent: Optional[float] = Field(default=None, ge=0, le=100)


@router.get("/progress")
def read_progress(current_user: Dict[str, Any] = Depends(get_current_user)):
    return get_progress(current_user["id"])


@router.post("/progress/activity", status_code=201)
def create_progress_activity(
    request: ProgressActivityRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if request.event_type == "quiz_completed" and request.score_percent is None:
        raise HTTPException(status_code=400, detail="A quiz score is required.")
    if request.event_type == "study_time" and request.duration_seconds == 0:
        raise HTTPException(status_code=400, detail="Study duration must be greater than zero.")

    defaults = {
        "study_time": "Active study time",
        "quiz_completed": "Completed a practice quiz",
        "flashcard_mastered": "Practiced a flashcard",
    }
    record_activity(
        current_user["id"],
        request.event_type,
        request.description or defaults[request.event_type],
        request.subject,
        request.duration_seconds,
        request.score_percent,
    )
    return {"status": "recorded"}
