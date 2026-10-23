import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from app.core.config import MAX_UPLOAD_BYTES
from app.core.security import get_optional_current_user
from app.core.database import get_connection
from app.services.document_service import extract_document_structured, split_text
from app.services.rag_service import index_chunks, delete_file_chunks, get_user_document_stats

router = APIRouter(tags=["Documents"])

@router.get("/documents")
def list_documents(
    user_id: Optional[str] = None,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Get all indexed documents and statistics for the active student"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"
    return get_user_document_stats(uid)

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """Upload and securely index a PDF, DOCX, or TXT course document for the student"""
    uid = (current_user["id"] if current_user else None) or user_id or "student_arnel"
    
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
    
    return {
        "message": "Document indexed successfully",
        "file_id": file_id,
        "filename": fn,
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
        cur.execute("DELETE FROM documents WHERE id = ? OR filename = ?", (file_id, file_id))
        if filename:
            cur.execute("DELETE FROM documents WHERE filename = ? OR id = ?", (filename, filename))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ SQL delete warning: {e}")
        
    return {"message": "Document permanently deleted", "file_id": file_id}
