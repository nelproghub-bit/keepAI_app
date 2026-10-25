import os
import sys
import time
import threading
import subprocess
import platform
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from app.core.security import (
    create_access_token,
    get_current_admin_user
)
from app.core.database import get_connection, is_mysql_fallback_active
from app.core.config import GEMINI_MODEL, GEMINI_API_KEY
from app.services.user_service import user_service
from app.services.rag_service import delete_file_chunks, get_tutor_context
from app.services.gemini_service import generate
from app.services.platform_settings import (
    get_student_registration_setting,
    set_student_registration_setting,
)

router = APIRouter(prefix="/admin", tags=["Admin Control Panel"])


# -------------------------------------------------------------
# Request & Response Models
# -------------------------------------------------------------
class AdminRegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)

class AdminLoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)

class AITestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=3000)
    mode: str = "tutor"  # tutor, summary, quiz, flashcard

class StudentRegistrationSettingRequest(BaseModel):
    enabled: bool

import uuid
from app.core.security import hash_password

class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    student_id: Optional[str] = "Student"
    role: str = "student"
    password: str = Field(min_length=6, max_length=128)

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    student_id: Optional[str] = None
    role: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


# -------------------------------------------------------------
# Admin Registration & Auth Endpoints
# -------------------------------------------------------------
@router.get("/registration-status")
def get_registration_status():
    """
    Check if admin registration is open or closed.
    Only one administrator account is allowed in the system.
    """
    admin_count = user_service.get_admin_count()
    admin_exists = admin_count >= 1
    return {
        "admin_exists": admin_exists,
        "admin_count": admin_count,
        "can_register": not admin_exists,
        "message": (
            "Admin registration is closed. Only one admin account is allowed."
            if admin_exists
            else "Admin registration is open. Create your administrator account."
        )
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_admin(request: AdminRegisterRequest):
    """
    Register the single allowed admin account.
    Fails with 403 Forbidden if an admin already exists.
    """
    admin_count = user_service.get_admin_count()
    if admin_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin registration is closed. Only one administrator account is allowed in this system."
        )

    try:
        user = user_service.register_admin(
            full_name=request.full_name,
            email=request.email,
            username=request.username,
            password=request.password
        )
        token = create_access_token({"sub": user["id"], "username": user["username"], "role": "admin"})
        return {
            "message": "Administrator account registered successfully.",
            "access_token": token,
            "token_type": "bearer",
            "user": user
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Admin registration failed: {str(e)}"
        )

@router.post("/login")
def login_admin(request: AdminLoginRequest):
    """
    Authenticate administrator credentials and verify admin role.
    """
    user = user_service.authenticate_admin(request.identifier, request.password)
    if is_mysql_fallback_active():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured MySQL/MariaDB database is unavailable. Start MySQL in XAMPP and try again.",
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials or unauthorized account."
        )

    token = create_access_token({"sub": user["id"], "username": user["username"], "role": "admin"})
    return {
        "message": "Administrator signed in successfully.",
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }


# -------------------------------------------------------------
# Admin Statistics & Overview
# -------------------------------------------------------------
@router.get("/stats")
def get_admin_dashboard_stats(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """
    Fetch comprehensive administrative metrics: student counts, documents, study activity.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Count students
        cur.execute("SELECT COUNT(*) as student_count FROM users WHERE role != 'admin'")
        student_count = cur.fetchone()["student_count"]

        # Count total documents
        cur.execute("SELECT COUNT(*) as doc_count FROM documents")
        doc_count = cur.fetchone()["doc_count"]

        # Aggregate study stats
        cur.execute("""
            SELECT 
                COALESCE(SUM(questions_asked), 0) as total_questions,
                COALESCE(SUM(quizzes_attempted), 0) as total_quizzes,
                COALESCE(SUM(summaries_generated), 0) as total_summaries,
                COALESCE(SUM(study_minutes), 0) as total_study_minutes
            FROM student_stats
        """)
        stats_row = cur.fetchone()

        return {
            "total_students": student_count,
            "total_documents": doc_count,
            "total_questions_asked": int(stats_row["total_questions"]),
            "total_quizzes_attempted": int(stats_row["total_quizzes"]),
            "total_summaries_generated": int(stats_row["total_summaries"]),
            "total_study_minutes": int(stats_row["total_study_minutes"]),
            "ai_provider": "Google Gemini AI",
            "ai_model": GEMINI_MODEL,
            "ai_status": "Active" if bool(GEMINI_API_KEY) else "Missing API Key",
            "database_status": "Connected (MariaDB / MySQL)"
        }
    except Exception as e:
        print(f"Error getting admin stats: {e}")
        return {
            "total_students": 0,
            "total_documents": 0,
            "total_questions_asked": 0,
            "total_quizzes_attempted": 0,
            "total_summaries_generated": 0,
            "total_study_minutes": 0,
            "ai_provider": "Google Gemini AI",
            "ai_model": GEMINI_MODEL,
            "ai_status": "Error",
            "database_status": f"Error: {e}"
        }
    finally:
        conn.close()


# -------------------------------------------------------------
# User Management (Real MariaDB/MySQL Database Connection)
# -------------------------------------------------------------
@router.get("/users")
def get_all_users(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """
    Fetch all real user accounts (students and admins) from MariaDB database.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, email, full_name, student_id, role, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        users = []
        for r in rows:
            users.append({
                "id": r["id"],
                "username": r["username"],
                "full_name": r["full_name"] or "N/A",
                "email": r["email"] or "N/A",
                "student_id": r["student_id"] or "N/A",
                "role": r["role"] or "student",
                "created_at": r["created_at"].strftime("%m/%d/%Y") if r.get("created_at") else "N/A",
                "last_login": r["last_login"].strftime("%m/%d/%Y %H:%M") if r.get("last_login") else "Never"
            })
        return users
    except Exception as e:
        print(f"Error listing users: {e}")
        return []
    finally:
        conn.close()

@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_new_user(
    request: CreateUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Add a new user directly into the real MariaDB database.
    """
    username_clean = request.username.strip().lower()
    email_clean = request.email.strip().lower()
    role_clean = request.role.strip().lower() if request.role else "student"
    if role_clean not in ("student", "admin"):
        role_clean = "student"

    if role_clean == "admin":
        if user_service.get_admin_count() >= 1:
            raise HTTPException(
                status_code=403, 
                detail="Admin registration is closed. Only one admin account is allowed in this system."
            )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Username '{username_clean}' already exists.")

        cur.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Email '{email_clean}' already exists.")

        user_id = str(uuid.uuid4())
        pw_hash = hash_password(request.password)

        cur.execute("""
            INSERT INTO users (id, username, email, full_name, student_id, password_hash, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username_clean, email_clean, request.full_name.strip(), request.student_id or "Student", pw_hash, role_clean))

        try:
            cur.execute("""
                INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans)
                VALUES (?, 0, 0, 0, 0, 0, '[]')
            """, (user_id,))
        except Exception:
            pass

        conn.commit()
        return {"message": "User created successfully in database.", "id": user_id, "username": username_clean}
    finally:
        conn.close()

@router.put("/users/{user_id}")
def update_user_info(
    user_id: str,
    request: UpdateUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Update user information in the real MariaDB database.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, role FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User account not found.")

        updates = []
        params = []
        if request.full_name is not None:
            updates.append("full_name = ?")
            params.append(request.full_name.strip())
        if request.email is not None:
            updates.append("email = ?")
            params.append(request.email.strip().lower())
        if request.student_id is not None:
            updates.append("student_id = ?")
            params.append(request.student_id.strip())
        if request.role is not None:
            new_role = request.role.strip().lower()
            if new_role == "admin" and user["role"] != "admin":
                if user_service.get_admin_count() >= 1:
                    raise HTTPException(status_code=403, detail="Only one admin account is allowed in this system.")
            updates.append("role = ?")
            params.append(new_role)

        if updates:
            params.append(user_id)
            cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()

        return {"message": "User information updated successfully."}
    finally:
        conn.close()

@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    request: ResetPasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Reset user password with bcrypt hash in the real MariaDB database.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User account not found.")

        pw_hash = hash_password(request.new_password)
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
        return {"message": "Password updated successfully in database."}
    finally:
        conn.close()

@router.delete("/users/{user_id}")
def delete_user_permanently(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Permanently delete user account from real MariaDB database.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User account not found.")

        # Clean student documents and chunks
        cur.execute("SELECT id, filename FROM documents WHERE user_id = ?", (user_id,))
        docs = cur.fetchall()
        for doc in docs:
            delete_file_chunks(user_id, doc["id"], doc.get("filename"))

        cur.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM student_stats WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

        return {"message": f"User '{user['username']}' permanently deleted from database."}
    finally:
        conn.close()

@router.get("/students")
def list_students(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """
    List all registered student accounts with their activity numbers.
    """
    return user_service.list_students_with_stats()

@router.delete("/students/{user_id}")
def delete_student(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Permanently delete a student account, their progress stats, and documents.
    """
    return delete_user_permanently(user_id, current_user)



# -------------------------------------------------------------
# Global Document Library Management
# -------------------------------------------------------------
@router.get("/documents")
def list_all_documents(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """
    List all uploaded and indexed documents in the system across all students.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.id, d.user_id, d.filename, d.page_count, d.chunks_indexed, 
                   d.char_count, d.created_at, u.username, u.full_name, u.student_id
            FROM documents d
            LEFT JOIN users u ON d.user_id = u.id
            ORDER BY d.created_at DESC
        """)
        rows = cur.fetchall()
        docs = []
        for r in rows:
            docs.append({
                "id": r["id"],
                "file_id": r["id"],
                "filename": r["filename"],
                "title": r["filename"],
                "user_id": r["user_id"],
                "student_name": r["full_name"] or r["username"] or r["user_id"],
                "student_id": r["student_id"] or "N/A",
                "page_count": r["page_count"] or 1,
                "chunk_count": r["chunks_indexed"] or 0,
                "char_count": r["char_count"] or 0,
                "uploaded_at": str(r["created_at"]) if r["created_at"] else ""
            })
        return docs
    except Exception as e:
        print(f"Error listing admin documents: {e}")
        return []
    finally:
        conn.close()

@router.delete("/documents/{file_id}")
def delete_document_permanently(
    file_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Permanently delete a document from MySQL database and chunk storage.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, filename FROM documents WHERE id = ?", (file_id,))
        doc = cur.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
    finally:
        conn.close()

    delete_file_chunks(doc["user_id"], doc["id"], doc["filename"])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM workspace_documents WHERE document_id = ?", (doc["id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"message": "Document permanently deleted from system.", "file_id": doc["id"]}

# -------------------------------------------------------------
# AI Interactive Playground & Diagnostics
# -------------------------------------------------------------
@router.post("/test-ai")
def test_ai_system(
    request: AITestRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    """
    Interactive AI test console for administrators to verify Gemini AI answers and RAG context.
    """
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Please enter a question or prompt to test.")

    system_instruction = (
        "You are KeepAI, a friendly and helpful study assistant. "
        "Answer the user's question clearly and simply using plain, easy-to-understand words. "
        "Explain key points step-by-step so anyone can understand."
    )

    if request.mode == "summary":
        system_instruction = (
            "You are KeepAI study assistant. "
            "Provide a simple, clear, bulleted summary explaining the main points in everyday language."
        )
    elif request.mode == "quiz":
        system_instruction = (
            "You are KeepAI study assistant. "
            "Generate 3 multiple-choice practice quiz questions with simple questions, 4 options each, and correct answers marked clearly."
        )
    elif request.mode == "flashcard":
        system_instruction = (
            "You are KeepAI study assistant. "
            "Generate 3 study flashcards (Question & Answer pairs) in simple and clear words."
        )

    try:
        reply = generate(prompt, system=system_instruction)
        return {
            "status": "success",
            "provider": "Google Gemini AI",
            "model": GEMINI_MODEL,
            "mode": request.mode,
            "prompt": prompt,
            "response": reply
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "Google Gemini AI",
            "model": GEMINI_MODEL,
            "mode": request.mode,
            "prompt": prompt,
            "response": f"Error communicating with Gemini AI: {str(e)}"
        }


# -------------------------------------------------------------
# System Diagnostics & Health Status
# -------------------------------------------------------------
@router.get("/system")
def get_system_diagnostics(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """
    Get detailed server environment, database status, and AI configuration.
    """
    db_connected = False
    db_error = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        db_connected = True
        conn.close()
    except Exception as e:
        db_error = str(e)

    return {
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "database": {
            "type": "MariaDB / MySQL",
            "connected": db_connected,
            "error": db_error
        },
        "ai_engine": {
            "provider": "Google Gemini AI",
            "model": GEMINI_MODEL,
            "api_key_configured": bool(GEMINI_API_KEY)
        },
        "system_status": "Healthy" if db_connected and bool(GEMINI_API_KEY) else "Needs Attention"
    }


@router.get("/settings")
def get_admin_settings(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    return {
        "student_registration": get_student_registration_setting(),
        "ai_engine": {
            "provider": "Google Gemini AI",
            "model": GEMINI_MODEL,
            "api_key_configured": bool(GEMINI_API_KEY),
        },
    }


@router.put("/settings/student-registration")
def update_student_registration_setting(
    request: StudentRegistrationSettingRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    setting = set_student_registration_setting(
        enabled=request.enabled,
        admin_id=current_user["id"],
    )
    return {
        "message": "Student registration settings saved.",
        "student_registration": setting,
    }


# -------------------------------------------------------------
# Server Process Management & Controls
# -------------------------------------------------------------
SERVER_START_TIME = time.time()

@router.get("/server/status")
def get_server_status(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    uptime_sec = int(time.time() - SERVER_START_TIME)
    hours, rem = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    db_connected = False
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        db_connected = True
        conn.close()
    except Exception:
        pass

    return {
        "success": True,
        "status": "online",
        "message": "KeepAI backend server is active and operational",
        "uptime": uptime_str,
        "database": "Connected" if db_connected else "Disconnected",
        "port": 8000,
        "pid": os.getpid()
    }

@router.post("/server/start")
def start_server_api(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    return {
        "success": True,
        "status": "online",
        "message": f"Server is already running on port 8000 (PID: {os.getpid()})"
    }

@router.post("/server/stop")
def stop_server_api(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    def _shutdown():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_shutdown).start()
    return {
        "success": True,
        "status": "offline",
        "message": "KeepAI server stopped successfully."
    }

@router.post("/server/restart")
def restart_server_api(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    def _restart():
        time.sleep(0.5)
        python_exe = sys.executable
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        subprocess.Popen([
            python_exe,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "8000"),
        ], cwd=base_dir)
        os._exit(0)
    threading.Thread(target=_restart).start()
    return {
        "success": True,
        "status": "online",
        "message": "Server restart initiated successfully."
    }
