import hmac
import hashlib
import base64
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import JWT_SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.database import get_connection

security_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt salt"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), 
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _base64url_decode(s: str) -> bytes:
    padding = '=' * (4 - (len(s) % 4)) if len(s) % 4 != 0 else ''
    return base64.urlsafe_b64decode((s + padding).encode('utf-8'))

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a standard RFC 7519 HMAC-SHA256 JWT access token"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = data.copy()
    
    now = int(time.time())
    if expires_delta:
        expire = now + int(expires_delta.total_seconds())
    else:
        expire = now + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        
    payload["iat"] = now
    payload["exp"] = expire
    
    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    
    header_b64 = _base64url_encode(header_json)
    payload_b64 = _base64url_encode(payload_json)
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(JWT_SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify an HMAC-SHA256 JWT token"""
    try:
        parts = token.strip().split('.')
        if len(parts) != 3:
            return None
            
        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        actual_sig = _base64url_decode(signature_b64)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        now = int(time.time())
        if payload.get("exp") and payload["exp"] < now:
            return None
            
        return payload
    except Exception:
        return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user record from database by user ID"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, username, email, full_name, student_id, role, created_at,
                   google_id, password_login_enabled, teaching_style, course_level
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            user = dict(row)
            user["google_linked"] = bool(user.pop("google_id", None))
            user["password_login_enabled"] = bool(user["password_login_enabled"])
            return user
        return None
    finally:
        conn.close()

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, Any]:
    """FastAPI dependency to enforce authentication and get the active user"""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Optional[Dict[str, Any]]:
    """FastAPI dependency to optionally get user if a valid bearer token is provided"""
    if not credentials or not credentials.credentials:
        return None
        
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        return None
        
    return get_user_by_id(payload["sub"])

def get_current_student_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Require an authenticated student account for student-owned resources."""
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student account required.",
        )
    return current_user

def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """FastAPI dependency to ensure the active user has admin privileges"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required. Access denied."
        )
    return current_user
