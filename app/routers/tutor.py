from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json
from app.core.security import get_optional_current_user
from app.services.user_service import user_service
from app.services.rag_service import get_tutor_context
from app.services.gemini_service import generate, generate_stream

router = APIRouter(tags=["AI Tutor"])

class AskRequest(BaseModel):
    user_id: Optional[str] = "student_arnel"
    question: str = Field(min_length=1, max_length=4000)
    teaching_style: str = "simple"
    course_level: Optional[str] = "intermediate"  # beginner | intermediate | advanced
    document_name: Optional[str] = None
    inline_context: Optional[str] = None   # Raw text content sent directly from the client (chat attach)

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

@router.post("/tutor/stream")
def stream_keepai(
    request: AskRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Real-time SSE token streaming for responsive ChatGPT-like interaction"""
    uid = (current_user["id"] if current_user else None) or request.user_id or "student_arnel"
    if current_user:
        user_service.increment_stat(current_user["id"], "questions_asked", 1)

    course_level = request.course_level or "intermediate"

    # If the client sent file text directly (chat attachment), use that as context
    if request.inline_context and request.inline_context.strip():
        context = request.inline_context[:12000]   # cap at ~12k chars to fit prompt window
        fname = request.document_name or "Attached Document"
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=True,
            sources=[fname]
        )
        prompt = f"Document content from '{fname}':\n{context}\n\nStudent question: {request.question}"
        has_sources = True
        sources = [fname]
        read_mode = "inline_attachment"
    else:
        tutor_ctx = get_tutor_context(uid, request.question, target_filename=request.document_name)
        
        if tutor_ctx["has_materials"]:
            context = tutor_ctx["context"]
            system = build_tutor_system_prompt(
                teaching_style=request.teaching_style,
                course_level=course_level,
                has_materials=True,
                sources=tutor_ctx.get("sources", [])
            )
            prompt = f"Lesson material from uploaded document:\n{context}\n\nStudent question: {request.question}"
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
        has_materials = tutor_ctx.get("has_materials", False)

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
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Smart AI tutor that intelligently reads whole documents and grounds answers accurately"""
    uid = (current_user["id"] if current_user else None) or request.user_id or "student_arnel"
    if current_user:
        user_service.increment_stat(current_user["id"], "questions_asked", 1)

    course_level = request.course_level or "intermediate"

    # If the client sent file text directly (chat attachment), use that as context
    if request.inline_context and request.inline_context.strip():
        context = request.inline_context[:12000]   # cap to fit prompt window
        fname = request.document_name or "Attached Document"
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=True,
            sources=[fname]
        )
        answer = generate(
            f"Document content from '{fname}':\n{context}\n\nStudent question: {request.question}",
            system=system,
            user_id=uid,
            teaching_style=request.teaching_style,
            has_sources=True
        )
        return {
            "answer": answer,
            "sources": [fname],
            "has_materials": True,
            "read_mode": "inline_attachment",
            "teaching_style": request.teaching_style,
            "course_level": course_level
        }

    tutor_ctx = get_tutor_context(uid, request.question, target_filename=request.document_name)
    
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
        answer = generate(
            f"Lesson material from uploaded document:\n{context}\n\nStudent question: {request.question}",
            system=system,
            user_id=uid,
            teaching_style=request.teaching_style,
            has_sources=True
        )
    else:
        system = build_tutor_system_prompt(
            teaching_style=request.teaching_style,
            course_level=course_level,
            has_materials=False
        )
        answer = generate(
            f"Student question: {request.question}",
            system=system,
            user_id=uid,
            teaching_style=request.teaching_style,
            has_sources=False
        )
        sources = []
        read_mode = "none"
    
    return {
        "answer": answer,
        "sources": sources,
        "has_materials": tutor_ctx["has_materials"],
        "read_mode": read_mode,
        "teaching_style": request.teaching_style,
        "course_level": course_level
    }
