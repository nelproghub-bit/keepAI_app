import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.core.security import get_optional_current_user
from app.core.database import get_connection

router = APIRouter(tags=["Workspaces"])

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = "No description"
    color: Optional[str] = "#7D1D1D"
    icon: Optional[str] = "📁"

@router.get("/workspaces")
def list_workspaces(
    user_id: Optional[str] = None,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """List workspaces for the current student from the database"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT w.id, w.user_id, w.name, w.description, w.color, w.icon, w.created_at,
                   COUNT(wd.document_id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_documents wd ON w.id = wd.workspace_id
            WHERE w.user_id = ? OR w.user_id = 'student_arnel'
            GROUP BY w.id
            ORDER BY w.created_at DESC
            """,
            (uid,)
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "description": r.get("description") or "No description",
                "color": r.get("color") or "#7D1D1D",
                "icon": r.get("icon") or "📁",
                "document_count": r.get("document_count", 0),
                "updated_at": "Active"
            })
        return {"workspaces": result}
    finally:
        conn.close()

@router.post("/workspaces")
def create_workspace(
    req: WorkspaceCreateRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Create a new workspace in the database"""
    uid = (current_user["id"] if current_user else None) or "student_arnel"
    ws_id = f"ws_{uuid.uuid4().hex[:12]}"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO workspaces (id, user_id, name, description, color, icon)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ws_id, uid, req.name, req.description, req.color, req.icon)
        )
        conn.commit()
        return {
            "id": ws_id,
            "name": req.name,
            "description": req.description,
            "color": req.color,
            "icon": req.icon,
            "document_count": 0,
            "updated_at": "Just now"
        }
    finally:
        conn.close()

@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Delete a workspace from the database"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,))
        cur.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        conn.commit()
        return {"message": "Workspace deleted", "id": workspace_id}
    finally:
        conn.close()
