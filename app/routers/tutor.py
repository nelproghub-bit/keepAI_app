from typing import Optional, Dict, Any
from uuid import uuid4
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

router = APIRouter(tags=["AI Tutor"])

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

TEACHING_STYLE_DIRECTIVES = {
    "simple": (
        "TEACHING STYLE: Simple & Clear (Plain English).\n"
        "- Explain concepts in straightforward, everyday language.\n"
        "- Avoid unnecessary technical jargon. If a technical term is required, define it immediately in simple terms.\n"
        "- Use clean, short bullet points and break ideas down into 2-3 digestible points.\n"
        "- Focus on what the student needs to know to understand the core idea quickly."
    ),
    "socratic": (
        "TEACHING STYLE: Guiding / Socratic Method (Step-by-Step Questions).\n"
        "- Do NOT just dump the full final answer right away.\n"
        "- Guide the student interactively: break down the problem into logical stepping stones.\n"
        "- Provide a hint or key observation from the lesson, and then ask a thought-provoking guiding question to lead them to the answer.\n"
        "- Encourage their critical thinking, praise their progress, and invite them to respond to your question."
    ),
    "detailed": (
        "TEACHING STYLE: Detailed & In-Depth Academic Depth.\n"
        "- Provide a thorough, comprehensive university-level explanation.\n"
        "- Cover theoretical principles, architecture, underlying mechanisms, key definitions, and edge cases.\n"
        "- Include structural breakdowns, pros/cons, and academic citations/page references from the course document."
    ),
    "visual": (
        "TEACHING STYLE: Everyday Examples & Relatable Analogies.\n"
        "- Anchor every single concept in an intuitive real-world analogy or everyday metaphor (e.g. comparing protocol handshakes to postal mail, memory caches to kitchen counters, HCI to a car dashboard).\n"
        "- Walk through concrete scenarios and practical real-life examples so the student can visualize the abstract concepts clearly."
    )
}

COURSE_LEVEL_DIRECTIVES = {
    "beginner": (
        "COURSE LEVEL: Introductory / Freshman.\n"
        "- Assume the student has little or no prior background in this subject.\n"
        "- Define all terms thoroughly, use gentle pacing, and emphasize foundational intuition ('What is this?' and 'Why is it used?')."
    ),
    "intermediate": (
        "COURSE LEVEL: Undergraduate / Intermediate.\n"
        "- Suitable for university students in Bachelor of Science in Computer Science / IT / Engineering.\n"
        "- Balance core theoretical concepts with practical software/hardware engineering context, system architecture, and standard terminology."
    ),
    "advanced": (
        "COURSE LEVEL: Advanced Capstone / Senior.\n"
        "- Treat the student as a senior researcher or graduating engineer working on capstone systems.\n"
        "- Emphasize architectural trade-offs, scalability, performance optimizations, security implications, edge cases, and industry design standards."
    )
}

def build_tutor_system_prompt(
    teaching_style: str = "simple",
    course_level: str = "intermediate",
    has_materials: bool = False,
    sources: list = None
) -> str:
    style_key = (teaching_style or "simple").lower().strip()
    level_key = (course_level or "intermediate").lower().strip()

    style_dir = TEACHING_STYLE_DIRECTIVES.get(style_key, TEACHING_STYLE_DIRECTIVES["simple"])
    level_dir = COURSE_LEVEL_DIRECTIVES.get(level_key, COURSE_LEVEL_DIRECTIVES["intermediate"])

    base_role = (
        "You are KeepAI, a friendly, expert, and empathetic academic study tutor.\n\n"
        f"{style_dir}\n\n"
        f"{level_dir}\n\n"
    )

    if has_materials:
        material_rules = (
            "GROUNDING & CITATION RULES:\n"
            "- Ground all your factual answers in the provided course materials.\n"
            "- Cite specific sections, topics, or page numbers (e.g., [Page 1], [Page 2]) when referencing definitions, outcomes, or examples.\n"
            "- If the student asks for a summary, give a well-structured summary matching your teaching style.\n"
            "- If a question cannot be answered from the materials, state that politely while offering helpful conceptual guidance."
        )
    else:
        material_rules = (
            "NOTE: The student has not yet uploaded or selected course materials for this query.\n"
            "- Answer using your general academic knowledge according to the assigned teaching style and course level.\n"
            "- Kindly remind them they can attach or select a lesson in the Library for specific document-grounded help."
        )

    return f"{base_role}{material_rules}"

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
    if tutor_ctx["has_materials"]:
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=True,
            sources=tutor_ctx.get("sources", [])
        )
        prompt = f"Lesson material from uploaded document:\n{tutor_ctx['context']}\n\nStudent question: {request.question}"
        has_sources = True
    else:
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=False
        )
        prompt = f"Student question: {request.question}"
        has_sources = False

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
                has_sources=has_sources
            ):
                token_event = {"type": "token", "token": token}
                yield f"data: {json.dumps(token_event)}\n\n"
        except Exception as e:
            err_event = {"type": "error", "error": str(e)}
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
    
    if tutor_ctx["has_materials"]:
        context = tutor_ctx["context"]
        sources = tutor_ctx["sources"]
        read_mode = tutor_ctx.get("read_mode", "targeted_retrieval")
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=True,
            sources=sources
        )
        try:
            answer = generate(
                f"Lesson material from uploaded document:\n{context}\n\nStudent question: {request.question}",
                system=system,
                user_id=uid,
                teaching_style=request.teaching_style,
                has_sources=True
            )
        except AIProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=False
        )
        try:
            answer = generate(
                f"Student question: {request.question}",
                system=system,
                user_id=uid,
                teaching_style=request.teaching_style,
                has_sources=False
            )
        except AIProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        sources = []
        read_mode = "none"

    record_activity(
        uid,
        "tutor_question",
        "Asked the AI tutor a study question",
        document_name or "AI Tutor",
    )
    
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
