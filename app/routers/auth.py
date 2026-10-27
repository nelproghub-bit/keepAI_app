from typing import Optional, List, Dict, Any
import time

import requests
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from app.core.security import create_access_token, get_current_admin_user, get_current_user
from app.core.config import GOOGLE_OAUTH_CLIENT_ID
from app.services.platform_settings import is_student_registration_enabled
from app.services.user_service import StudentRegistrationDisabledError, user_service

router = APIRouter(prefix="/auth", tags=["Authentication & Security"])

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    student_id: str = Field(default="Student", max_length=60)
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)

class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128)

class ProfileUpdateRequest(BaseModel):
    teaching_style: Optional[str] = None
    course_level: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class StatsSyncRequest(BaseModel):
    questions_asked: Optional[int] = None
    summaries_generated: Optional[int] = None
    quizzes_attempted: Optional[int] = None
    questions_tested: Optional[int] = None
    study_minutes: Optional[int] = None
    study_plans: Optional[List[str]] = None

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_student(request: RegisterRequest):
    """Register a new student account securely with encrypted password"""
    if not is_student_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student registration is currently paused. Please contact your administrator.",
        )
    try:
        user = user_service.register(
            full_name=request.full_name,
            student_id=request.student_id,
            email=request.email,
            username=request.username,
            password=request.password
        )
        token = create_access_token({"sub": user["id"], "username": user["username"]})
        stats = user_service.get_stats(user["id"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
            "stats": stats
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed: " + str(e))

@router.post("/login")
def login_student(request: LoginRequest):
    """Authenticate a student with username, email, or student ID."""
    user = user_service.authenticate(
        identifier=request.identifier,
        password=request.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your username, email, or student ID and password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = create_access_token({"sub": user["id"], "username": user["username"]})
    stats = user_service.get_stats(user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "stats": stats
    }

class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=10000)

class PasswordUpdateRequest(BaseModel):
    current_password: Optional[str] = Field(default=None, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/registration-status")
def get_student_registration_status():
    return {"enabled": is_student_registration_enabled()}

@router.post("/google")
def google_auth(request: GoogleLoginRequest):
    """Verify a Google ID token, then authenticate or create its account."""
    try:
        verification = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": request.credential},
            timeout=(3, 10),
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in could not be verified right now. Please try again.",
        ) from exc

    if verification.status_code == 429 or verification.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is temporarily unavailable. Please try again.",
        )
    if verification.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in token is invalid or expired. Please try again.",
        )

    try:
        payload = verification.json()
        token_expiry = int(payload.get("exp", 0))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google returned an invalid sign-in response.",
        ) from exc

    if (
        payload.get("aud") != GOOGLE_OAUTH_CLIENT_ID
        or payload.get("azp") not in (None, GOOGLE_OAUTH_CLIENT_ID)
        or payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
        or token_expiry <= int(time.time())
        or payload.get("email_verified") not in (True, "true")
        or not payload.get("email")
        or not payload.get("sub")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in token could not be verified for this application.",
        )

    email = payload["email"]
    name = payload.get("name") or email.split("@")[0]
    sub = payload["sub"]

    try:
        user = user_service.get_or_create_google_user(
            email=email,
            full_name=name,
            google_id=sub,
            allow_create=is_student_registration_enabled(),
        )
    except StudentRegistrationDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    token = create_access_token({"sub": user["id"], "username": user["username"]})
    stats = user_service.get_stats(user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "student_id": user["student_id"],
            "role": user.get("role", "student"),
            "google_linked": True,
            "password_login_enabled": bool(user.get("password_login_enabled", True)),
        },
        "stats": stats,
    }

@router.put("/password")
def update_password(
    request: PasswordUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Set a password for a Google-linked account or change an existing password."""
    try:
        user_service.update_password(
            user_id=current_user["id"],
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"message": "Password updated successfully."}

@router.get("/me")
def get_current_student_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Retrieve currently authenticated student profile and progress metrics"""
    stats = user_service.get_stats(current_user["id"])
    return {
        "user": current_user,
        "stats": stats
    }

@router.post("/stats")
def sync_student_stats(
    request: StatsSyncRequest, 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Sync student study analytics and learning plans to persistent storage"""
    updates = request.dict(exclude_unset=True)
    updated_stats = user_service.update_stats(current_user["id"], updates)
    return {"stats": updated_stats}

@router.put("/profile")
def update_student_profile(
    request: ProfileUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update authenticated student profile details and preferences"""
    updated_user = user_service.update_profile(
        user_id=current_user["id"],
        teaching_style=request.teaching_style,
        course_level=request.course_level
    )
    return {"user": updated_user}

@router.get("/users")
def get_all_students(current_user: Dict[str, Any] = Depends(get_current_admin_user)):
    """Admin view: Retrieve list of registered student accounts"""
    return {"users": user_service.list_users()}
