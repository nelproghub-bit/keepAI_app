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
                   COUNT(DISTINCT d.id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_documents wd ON w.id = wd.workspace_id
            LEFT JOIN documents d ON d.id = wd.document_id
            WHERE w.user_id = ? OR w.user_id = 'student_arnel'
            GROUP BY w.id
            ORDER BY w.created_at DESC
            """,
            (uid,)
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            r = dict(row)
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

@router.post("/workspaces/{workspace_id}/documents/{document_id}")
def add_document_to_workspace(
    workspace_id: str,
    document_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Link an existing student document to a workspace exactly once."""
    uid = (current_user["id"] if current_user else None) or "student_arnel"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM workspaces WHERE id = ? AND (user_id = ? OR user_id = 'student_arnel')",
            (workspace_id, uid)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        cur.execute(
            "SELECT id FROM documents WHERE id = ? AND user_id = ?",
            (document_id, uid)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

        cur.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = ? AND document_id = ?",
            (workspace_id, document_id)
        )
        cur.execute(
            "INSERT INTO workspace_documents (id, workspace_id, document_id) VALUES (?, ?, ?)",
            (f"wsdoc_{uuid.uuid4().hex[:12]}", workspace_id, document_id)
        )
        conn.commit()
        return {"workspace_id": workspace_id, "document_id": document_id}
    finally:
        conn.close()

@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Delete a workspace from the database"""
    uid = (current_user["id"] if current_user else None) or "student_arnel"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM workspaces WHERE id = ? AND user_id = ?",
            (workspace_id, uid)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        cur.execute("DELETE FROM workspace_documents WHERE workspace_id = ?", (workspace_id,))
        cur.execute("DELETE FROM workspaces WHERE id = ? AND user_id = ?", (workspace_id, uid))
        conn.commit()
        return {"message": "Workspace deleted", "id": workspace_id}
    finally:
        conn.close()
