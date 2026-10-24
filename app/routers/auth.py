from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from app.core.security import create_access_token, get_current_user
from app.services.user_service import user_service

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
    full_name: Optional[str] = None
    student_id: Optional[str] = None
    teaching_style: Optional[str] = None
    course_level: Optional[str] = None

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
    credential: str
    client_id: Optional[str] = None

@router.post("/google")
def google_auth(request: GoogleLoginRequest):
    """Authenticate or register student using Google Identity Services credential (JWT)"""
    import base64
    import json
    import uuid
    try:
        parts = request.credential.split(".")
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid Google credential token.")
            
        padding = 4 - len(parts[1]) % 4
        payload_str = base64.urlsafe_b64decode(parts[1] + "=" * padding).decode("utf-8")
        payload = json.loads(payload_str)
        
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain an email address.")
            
        name = payload.get("name") or email.split("@")[0]
        sub = payload.get("sub", str(uuid.uuid4()))
        picture = payload.get("picture")
        
        user = user_service.get_or_create_google_user(
            email=email,
            full_name=name,
            google_id=sub,
            picture=picture
        )
        
        token = create_access_token({"sub": user["id"], "username": user["username"]})
        stats = user_service.get_stats(user["id"])
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google authentication failed: {str(e)}")

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
        full_name=request.full_name,
        student_id=request.student_id,
        teaching_style=request.teaching_style,
        course_level=request.course_level
    )
    return {"user": updated_user}

@router.get("/users")
def get_all_students(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Admin view: Retrieve list of registered student accounts"""
    return {"users": user_service.list_users()}
