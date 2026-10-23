import uuid
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.database import get_connection
from app.core.security import get_current_admin_user, get_current_user

router = APIRouter(tags=["Announcements"])


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=3, max_length=5000)
    kind: Literal["info", "update", "maintenance"] = "info"


def _serialize_announcement(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "message": row["message"],
        "kind": row["kind"],
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "is_read": bool(row.get("is_read", False)),
    }


@router.get("/announcements")
def list_announcements(current_user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.id, a.title, a.message, a.kind, a.created_at,
                   CASE WHEN r.id IS NULL THEN FALSE ELSE TRUE END AS is_read
            FROM announcements a
            LEFT JOIN announcement_reads r
                ON r.announcement_id = a.id AND r.user_id = ?
            WHERE a.is_active = ?
            ORDER BY a.created_at DESC
            LIMIT 100
            """,
            (current_user["id"], True),
        )
        rows = cursor.fetchall()
        announcements = [_serialize_announcement(dict(row)) for row in rows]
        return {
            "announcements": announcements,
            "unread_count": sum(not item["is_read"] for item in announcements),
        }
    finally:
        conn.close()


@router.post("/announcements/{announcement_id}/read")
def mark_announcement_read(
    announcement_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM announcements WHERE id = ? AND is_active = ?",
            (announcement_id, True),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Announcement not found")

        cursor.execute(
            "SELECT id FROM announcement_reads WHERE announcement_id = ? AND user_id = ?",
            (announcement_id, current_user["id"]),
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO announcement_reads (id, announcement_id, user_id)
                VALUES (?, ?, ?)
                """,
                (f"read_{uuid.uuid4().hex[:16]}", announcement_id, current_user["id"]),
            )
            conn.commit()
        return {"announcement_id": announcement_id, "is_read": True}
    finally:
        conn.close()


@router.get("/admin/announcements")
def list_admin_announcements(
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, message, kind, created_at, FALSE AS is_read
            FROM announcements
            WHERE is_active = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (True,),
        )
        return {
            "announcements": [
                _serialize_announcement(dict(row)) for row in cursor.fetchall()
            ]
        }
    finally:
        conn.close()


@router.post(
    "/admin/announcements",
    status_code=status.HTTP_201_CREATED,
)
def create_announcement(
    request: AnnouncementCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    title = request.title.strip()
    message = request.message.strip()
    if len(title) < 3 or len(message) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A title and message with at least 3 non-space characters are required.",
        )

    announcement_id = f"announcement_{uuid.uuid4().hex[:16]}"
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO announcements (id, title, message, kind, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                announcement_id,
                title,
                message,
                request.kind,
                current_user["id"],
            ),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT id, title, message, kind, created_at, FALSE AS is_read
            FROM announcements
            WHERE id = ?
            """,
            (announcement_id,),
        )
        return _serialize_announcement(dict(cursor.fetchone()))
    finally:
        conn.close()


@router.delete("/admin/announcements/{announcement_id}")
def deactivate_announcement(
    announcement_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE announcements SET is_active = ? WHERE id = ? AND is_active = ?",
            (False, announcement_id, True),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")
        conn.commit()
        return {"id": announcement_id, "is_active": False}
    finally:
        conn.close()
