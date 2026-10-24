import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.core.security import get_current_student_user
from app.core.database import get_connection
from app.services.progress_service import record_activity

router = APIRouter(tags=["Workspaces"])

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = "No description"
    color: Optional[str] = "#7D1D1D"
    icon: Optional[str] = Field(default="fa-folder-open", max_length=32)

@router.get("/workspaces")
def list_workspaces(
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """List workspaces for the current student from the database"""
    uid = current_user["id"]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT w.id, w.user_id, w.name, w.category, w.description, w.color, w.icon, w.created_at,
                   COUNT(DISTINCT d.id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_documents wd ON w.id = wd.workspace_id
            LEFT JOIN documents d ON d.id = wd.document_id AND d.user_id = w.user_id
            WHERE w.user_id = ?
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
                "category": r.get("category"),
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
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Create a new workspace in the database"""
    uid = current_user["id"]
    ws_id = f"ws_{uuid.uuid4().hex[:12]}"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO workspaces (id, user_id, name, category, description, color, icon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ws_id, uid, req.name, req.category, req.description, req.color, req.icon)
        )
        conn.commit()
        record_activity(
            current_user["id"],
            "workspace_created",
            "Created a study workspace",
            req.name,
        )
        return {
            "id": ws_id,
            "name": req.name,
            "category": req.category,
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
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Link an existing student document to a workspace exactly once."""
    uid = current_user["id"]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM workspaces WHERE id = ? AND user_id = ?",
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
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Delete a workspace from the database"""
    uid = current_user["id"]
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
