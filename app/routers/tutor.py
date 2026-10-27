from typing import Optional, Dict, Any
from uuid import uuid4
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
from app.core.database import get_connection
from app.core.security import get_current_user, get_current_student_user
from app.services.user_service import user_service
from app.services.progress_service import record_activity
from app.services.rag_service import get_tutor_context
from app.services.gemini_service import AIProviderError, generate, generate_stream
from app.core.ai_guardrails import build_guarded_tutor_prompt

router = APIRouter(tags=["AI Tutor"])
logger = logging.getLogger(__name__)

FIRST_TUTOR_GREETING = "Hello! I am KeepAI, your academic tutor and study assistant."


def claim_first_tutor_greeting(user_id: str) -> bool:
    """Atomically persist whether this account has received its first-chat greeting."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id FROM tutor_greeting_state WHERE user_id = ?",
            (user_id,),
        )
        if cursor.fetchone():
            return False

        cursor.execute(
            "SELECT id FROM tutor_conversations WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        has_prior_chat = cursor.fetchone() is not None

        try:
            cursor.execute(
                "INSERT INTO tutor_greeting_state (user_id) VALUES (?)",
                (user_id,),
            )
            conn.commit()
            return not has_prior_chat
        except Exception:
            conn.rollback()
            cursor.execute(
                "SELECT user_id FROM tutor_greeting_state WHERE user_id = ?",
                (user_id,),
            )
            if cursor.fetchone():
                return False
            raise
    finally:
        conn.close()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    teaching_style: str = "simple"
    course_level: Optional[str] = "intermediate"  # beginner | intermediate | advanced
    document_id: Optional[str] = None
    document_name: Optional[str] = None

class SaveTutorTurnRequest(BaseModel):
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=50000)
    teaching_style: str = Field(default="simple", max_length=32)
    course_level: str = Field(default="intermediate", max_length=32)

def build_tutor_system_prompt(
    teaching_style: str = "simple",
    course_level: str = "intermediate",
    has_materials: bool = False,
    sources: list = None
) -> str:
    system, _ = build_guarded_tutor_prompt(
        question="",
        context=" " if has_materials else None,
        teaching_style=teaching_style,
        course_level=course_level,
        has_materials=has_materials,
        sources=sources,
    )
    return system

def get_owned_document_name(
    user_id: str,
    document_id: Optional[str],
    document_name: Optional[str],
) -> Optional[str]:
    """Resolve a selected document only from rows owned by the authenticated user."""
    if not document_id and not document_name:
        return None

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if document_id:
            cursor.execute(
                "SELECT filename FROM documents WHERE id = ? AND user_id = ?",
                (document_id, user_id),
            )
        else:
            cursor.execute(
                """
                SELECT filename FROM documents
                WHERE user_id = ? AND LOWER(filename) = LOWER(?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, document_name),
            )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row["filename"]

@router.post("/tutor/stream")
def stream_keepai(
    request: AskRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Real-time SSE token streaming for responsive ChatGPT-like interaction"""
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_id, request.document_name)
    user_service.increment_stat(uid, "questions_asked", 1)

    course_level = request.course_level or "intermediate"
    tutor_ctx = get_tutor_context(uid, request.question, target_filename=document_name)
    has_sources = bool(tutor_ctx["has_materials"])
    system, prompt = build_guarded_tutor_prompt(
        question=request.question,
        context=tutor_ctx.get("context"),
        teaching_style=request.teaching_style,
        course_level=course_level,
        has_materials=has_sources,
        sources=tutor_ctx.get("sources", []),
    )

    sources = tutor_ctx.get("sources", [])
    read_mode = tutor_ctx.get("read_mode", "none")

    def event_stream():
        meta_event = {
            "type": "meta",
            "sources": sources,
            "has_materials": has_sources,
            "read_mode": read_mode,
            "teaching_style": request.teaching_style,
            "course_level": course_level
        }
        yield f"data: {json.dumps(meta_event)}\n\n"
        
        try:
            for token in generate_stream(
                prompt=prompt,
                system=system,
                user_id=uid,
                teaching_style=request.teaching_style,
                has_sources=has_sources,
            ):
                token_event = {"type": "token", "token": token}
                yield f"data: {json.dumps(token_event)}\n\n"
        except Exception as exc:
            logger.warning("Tutor stream failed (%s)", type(exc).__name__)
            err_event = {
                "type": "error",
                "error": "The AI service could not generate a response. Please try again.",
            }
            yield f"data: {json.dumps(err_event)}\n\n"
            
        done_event = {"type": "done"}
        yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/tutor/ask")
def ask_keepai(
    request: AskRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Smart AI tutor that intelligently reads whole documents and grounds answers accurately"""
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_id, request.document_name)
    user_service.increment_stat(uid, "questions_asked", 1)

    course_level = request.course_level or "intermediate"
    tutor_ctx = get_tutor_context(uid, request.question, target_filename=document_name)
    has_sources = bool(tutor_ctx["has_materials"])
    sources = tutor_ctx.get("sources", [])
    read_mode = tutor_ctx.get("read_mode", "targeted_retrieval" if has_sources else "none")
    system, prompt = build_guarded_tutor_prompt(
        question=request.question,
        context=tutor_ctx.get("context"),
        teaching_style=request.teaching_style,
        course_level=course_level,
        has_materials=has_sources,
        sources=sources,
    )
    try:
        answer = generate(
            prompt,
            system=system,
            user_id=uid,
            teaching_style=request.teaching_style,
            has_sources=has_sources,
            max_output_tokens=1800,
        )
    except AIProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="The AI service could not generate a response. Please try again.",
        ) from exc

    record_activity(
        uid,
        "tutor_question",
        "Asked the AI tutor a study question",
        document_name or "AI Tutor",
    )
    if claim_first_tutor_greeting(uid):
        answer = f"{FIRST_TUTOR_GREETING}\n\n{answer}"
    
    return {
        "answer": answer,
        "sources": sources,
        "has_materials": tutor_ctx["has_materials"],
        "read_mode": read_mode,
        "teaching_style": request.teaching_style,
        "course_level": course_level
    }


@router.get("/tutor/history")
def list_tutor_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.title, c.teaching_style, c.course_level, c.created_at, c.updated_at,
                   COUNT(m.id) AS message_count
            FROM tutor_conversations c
            LEFT JOIN tutor_messages m ON m.conversation_id = c.id AND m.user_id = c.user_id
            WHERE c.user_id = ?
            GROUP BY c.id, c.title, c.teaching_style, c.course_level, c.created_at, c.updated_at
            ORDER BY c.updated_at DESC
            LIMIT 100
            """,
            (current_user["id"],),
        )
        return {"conversations": [dict(row) for row in cursor.fetchall()]}
    finally:
        conn.close()


@router.get("/tutor/history/{conversation_id}")
def get_tutor_conversation(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, teaching_style, course_level, created_at, updated_at
            FROM tutor_conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, current_user["id"]),
        )
        conversation = cursor.fetchone()
        if not conversation:
            raise HTTPException(status_code=404, detail="Chat not found.")

        cursor.execute(
            """
            SELECT id, role, content, created_at
            FROM tutor_messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY message_order ASC
            """,
            (conversation_id, current_user["id"]),
        )
        return {
            "conversation": dict(conversation),
            "messages": [dict(row) for row in cursor.fetchall()],
        }
    finally:
        conn.close()


@router.post("/tutor/history", status_code=201)
def save_tutor_turn(
    request: SaveTutorTurnRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        conversation_id = request.conversation_id
        if conversation_id:
            cursor.execute(
                "SELECT id FROM tutor_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, current_user["id"]),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Chat not found.")
            cursor.execute(
                """
                UPDATE tutor_conversations
                SET updated_at = CURRENT_TIMESTAMP,
                    teaching_style = ?,
                    course_level = ?
                WHERE id = ? AND user_id = ?
                """,
                (request.teaching_style, request.course_level, conversation_id, current_user["id"]),
            )
        else:
            conversation_id = uuid4().hex
            title = " ".join(request.question.split())[:200]
            cursor.execute(
                """
                INSERT INTO tutor_conversations
                    (id, user_id, title, teaching_style, course_level)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    current_user["id"],
                    title,
                    request.teaching_style,
                    request.course_level,
                ),
            )

        cursor.execute(
            "SELECT COALESCE(MAX(message_order), 0) AS last_order FROM tutor_messages WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, current_user["id"]),
        )
        message_order = cursor.fetchone()["last_order"]
        cursor.execute(
            """
            INSERT INTO tutor_messages (id, conversation_id, user_id, role, message_order, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uuid4().hex, conversation_id, current_user["id"], "user", message_order + 1, request.question),
        )
        cursor.execute(
            """
            INSERT INTO tutor_messages (id, conversation_id, user_id, role, message_order, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uuid4().hex, conversation_id, current_user["id"], "ai", message_order + 2, request.answer),
        )
        conn.commit()
        return {"conversation_id": conversation_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.delete("/tutor/history/{conversation_id}")
def delete_tutor_conversation(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM tutor_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, current_user["id"]),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Chat not found.")
        cursor.execute(
            "DELETE FROM tutor_messages WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, current_user["id"]),
        )
        cursor.execute(
            "DELETE FROM tutor_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, current_user["id"]),
        )
        conn.commit()
        return {"deleted": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.delete("/tutor/history")
def clear_tutor_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM tutor_messages WHERE user_id = ?",
            (current_user["id"],),
        )
        cursor.execute(
            "DELETE FROM tutor_conversations WHERE user_id = ?",
            (current_user["id"],),
        )
        conn.commit()
        return {"deleted": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
