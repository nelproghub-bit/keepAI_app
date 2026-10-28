import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from app.core.config import MAX_UPLOAD_BYTES
from app.core.security import get_current_student_user
from app.core.database import get_connection
from app.core.ai_guardrails import sanitize_filename, verify_file_content
from app.services.document_service import extract_document_structured, split_text
from app.services.rag_service import index_chunks, delete_file_chunks, get_user_document_stats
from app.services.progress_service import record_activity

router = APIRouter(tags=["Documents"])


@router.get("/documents")
def list_documents(current_user: Dict[str, Any] = Depends(get_current_student_user)):
    """List only documents owned by the authenticated student."""
    uid = current_user["id"]
    stats = get_user_document_stats(uid)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.id, w.id AS workspace_id
            FROM documents d
            LEFT JOIN workspace_documents wd ON wd.document_id = d.id
            LEFT JOIN workspaces w ON w.id = wd.workspace_id AND w.user_id = d.user_id
            WHERE d.user_id = ?
            """,
            (uid,)
        )
        workspace_by_document = {}
        for row in cur.fetchall():
            if row["workspace_id"]:
                workspace_by_document.setdefault(row["id"], row["workspace_id"])
    finally:
        conn.close()

    for document in stats["files"]:
        document["workspace_id"] = workspace_by_document.get(document["file_id"])
    return stats


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Upload a document and associate it with the authenticated student."""
    uid = current_user["id"]
    fn = sanitize_filename(file.filename or "")
    fn_lower = fn.lower()
    allowed_exts = (".pdf", ".docx", ".doc", ".pptx", ".txt", ".md", ".csv")
    if not any(fn_lower.endswith(ext) for ext in allowed_exts):
        raise HTTPException(400, "Supported formats: PDF, DOCX, PPTX, TXT, MD.")

    previous_document_ids = []
    effective_workspace_id = workspace_id
    conn = get_connection()
    try:
        cur = conn.cursor()
        if effective_workspace_id:
            cur.execute(
                "SELECT id FROM workspaces WHERE id = ? AND user_id = ?",
                (effective_workspace_id, uid)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Workspace not found")

        cur.execute(
            """
            SELECT d.id, w.id AS workspace_id
            FROM documents d
            LEFT JOIN workspace_documents wd ON wd.document_id = d.id
            LEFT JOIN workspaces w ON w.id = wd.workspace_id AND w.user_id = d.user_id
            WHERE d.user_id = ? AND LOWER(d.filename) = LOWER(?)
            """,
            (uid, fn)
        )
        existing_rows = cur.fetchall()
        previous_document_ids = [row["id"] for row in existing_rows]
        if not effective_workspace_id:
            effective_workspace_id = next(
                (row["workspace_id"] for row in existing_rows if row["workspace_id"]),
                None
            )
    finally:
        conn.close()

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_BYTES // (1024*1024)}MB upload limit.")

    is_valid, content_err = verify_file_content(data, fn)
    if not is_valid:
        raise HTTPException(400, content_err)

    try:
        doc_info = extract_document_structured(data, fn)
    except Exception as e:
        raise HTTPException(400, f"Unable to read the document: {str(e)}") from e

    full_text = doc_info.get("full_text", "")
    if not full_text.strip():
        ocr_failed = bool(doc_info.get("warnings"))
        detail = (
            "OCR could not read one or more scanned pages. Ensure Tesseract OCR is installed "
            "and available to the application, or upload a text-based copy."
            if ocr_failed
            else "No readable text could be extracted. For scanned PDFs, ensure OCR is available or upload a text-based copy."
        )
        raise HTTPException(
            400,
            detail,
        )

    chunks = split_text(full_text)
    if not chunks:
        raise HTTPException(400, "Could not process text into chunks.")

    file_id = str(uuid.uuid4())
    indexed = index_chunks(
        user_id=uid,
        file_id=file_id,
        filename=fn,
        chunks=chunks,
        full_text=full_text,
        outline=doc_info.get("outline", []),
        size_bytes=len(data),
        page_count=doc_info.get("page_count", 1),
    )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM documents WHERE id = ? AND user_id = ?",
            (file_id, uid)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=500, detail="Document ownership could not be persisted.")

        for previous_id in previous_document_ids:
            cur.execute(
                """
                DELETE FROM workspace_documents
                WHERE workspace_id IN (SELECT id FROM workspaces WHERE user_id = ?)
                    AND document_id = ?
                """,
                (uid, previous_id)
            )
        if effective_workspace_id:
            cur.execute(
                """
                INSERT INTO workspace_documents (id, workspace_id, document_id)
                VALUES (?, ?, ?)
                """,
                (f"wsdoc_{uuid.uuid4().hex[:12]}", effective_workspace_id, file_id)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    record_activity(
        uid,
        "document_uploaded",
        "Uploaded a study document",
        fn,
    )

    return {
        "message": "Document indexed successfully",
        "file_id": file_id,
        "filename": fn,
        "workspace_id": effective_workspace_id,
        "chunks_indexed": indexed,
        "page_count": doc_info.get("page_count", 1),
        "char_count": len(full_text),
        "size_bytes": len(data),
        "warnings": doc_info.get("warnings", []),
    }


@router.delete("/documents/{file_id}")
def delete_document(
    file_id: str,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Delete a document only after verifying its ownership."""
    uid = current_user["id"]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, filename FROM documents WHERE id = ? AND user_id = ?",
            (file_id, uid)
        )
        document = cur.fetchone()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

    finally:
        conn.close()

    delete_file_chunks(uid, document["id"], document["filename"])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM workspace_documents
            WHERE workspace_id IN (SELECT id FROM workspaces WHERE user_id = ?)
                AND document_id = ?
            """,
            (uid, document["id"])
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"message": "Document permanently deleted", "file_id": document["id"]}
