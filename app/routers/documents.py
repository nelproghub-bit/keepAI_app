import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from app.core.config import MAX_UPLOAD_BYTES
from app.core.security import get_optional_current_user
from app.core.database import get_connection
from app.services.document_service import extract_document_structured, split_text
from app.services.rag_service import index_chunks, delete_file_chunks, get_user_document_stats
from app.services.progress_service import record_activity

router = APIRouter(tags=["Documents"])

@router.get("/documents")
def list_documents(
    user_id: Optional[str] = None,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Get all indexed documents and statistics for the active student"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"
    stats = get_user_document_stats(uid)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.id, d.filename, wd.workspace_id
            FROM documents d
            LEFT JOIN workspace_documents wd ON wd.document_id = d.id
            WHERE d.user_id = ?
            """,
            (uid,)
        )
        workspace_by_document = {
            row["id"]: row["workspace_id"]
            for row in cur.fetchall()
        }
    finally:
        conn.close()

    for document in stats["files"]:
        document["workspace_id"] = workspace_by_document.get(document["file_id"])
    return stats

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    workspace_id: Optional[str] = Form(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Upload and securely index a PDF, DOCX, or TXT course document for the student"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.id, wd.workspace_id
            FROM documents d
            LEFT JOIN workspace_documents wd ON wd.document_id = d.id
            WHERE d.user_id = ? AND LOWER(d.filename) = LOWER(?)
            """,
            (uid, file.filename or "")
        )
        existing_rows = cur.fetchall()
        previous_document_ids = [row["id"] for row in existing_rows]
        effective_workspace_id = workspace_id or next(
            (row["workspace_id"] for row in existing_rows if row["workspace_id"]),
            None
        )

        if effective_workspace_id:
            cur.execute(
                "SELECT id FROM workspaces WHERE id = ? AND (user_id = ? OR user_id = 'student_arnel')",
                (effective_workspace_id, uid)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Workspace not found")
    finally:
        conn.close()
    
    fn = file.filename or ""
    fn_lower = fn.lower()
    allowed_exts = (".pdf", ".docx", ".doc", ".txt", ".md", ".csv")
    if not any(fn_lower.endswith(ext) for ext in allowed_exts):
        raise HTTPException(400, "Supported formats: PDF, DOCX, TXT, MD.")
        
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_BYTES // (1024*1024)}MB upload limit.")
        
    try:
        doc_info = extract_document_structured(data, fn)
    except Exception as e:
        raise HTTPException(400, f"Unable to read the document: {str(e)}")
        
    full_text = doc_info.get("full_text", "")
    if not full_text.strip():
        raise HTTPException(
            400,
            "No readable text found in document. Scanned documents require optical character recognition (OCR).",
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
        outline=doc_info.get("outline", [])
    )

    if effective_workspace_id:
        conn = get_connection()
        try:
            cur = conn.cursor()
            for previous_id in previous_document_ids:
                cur.execute(
                    "DELETE FROM workspace_documents WHERE document_id = ?",
                    (previous_id,)
                )
            cur.execute(
                "DELETE FROM workspace_documents WHERE document_id = ?",
                (file_id,)
            )
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

    if current_user:
        record_activity(
            current_user["id"],
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
        "char_count": len(full_text)
    }

@router.delete("/documents/{file_id}")
def delete_document(
    file_id: str, 
    user_id: Optional[str] = None,
    filename: Optional[str] = None,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Permanently delete indexed document chunks and database metadata for the student"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"
    
    # 1. Delete from RAG chunks, metadata, and JSON storage
    delete_file_chunks(uid, file_id, filename)
    if uid != "student_arnel":
        delete_file_chunks("student_arnel", file_id, filename)
        
    # 2. Permanently delete from SQL database
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM workspace_documents WHERE document_id = ?",
            (file_id,)
        )
        cur.execute(
            """
            DELETE FROM workspace_documents
            WHERE document_id IN (
                SELECT id FROM documents WHERE filename = ? OR id = ?
            )
            """,
            (filename or file_id, file_id)
        )
        cur.execute("DELETE FROM documents WHERE id = ? OR filename = ?", (file_id, file_id))
        if filename:
            cur.execute("DELETE FROM documents WHERE filename = ? OR id = ?", (filename, filename))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ SQL delete warning: {e}")
        
    return {"message": "Document permanently deleted", "file_id": file_id}
