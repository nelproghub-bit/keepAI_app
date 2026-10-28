import os
import json
import re
import math
from typing import List, Dict, Any, Optional
from app.core.config import CHROMA_PATH
from app.core.database import get_connection
from app.services.gemini_service import ai_service

# Enhanced in-memory storage with caching
_document_store: Dict[str, List[Dict]] = {}
_files_meta_store: Dict[str, Dict] = {}
_search_index: Dict[str, Dict] = {}


def _get_user_document_refs(user_id: str) -> tuple[set, set]:
    """Return database-confirmed document IDs and names for one owner."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, filename FROM documents WHERE user_id = ?",
            (user_id,)
        )
        rows = cur.fetchall()
        return (
            {row["id"] for row in rows},
            {row["filename"] for row in rows},
        )
    finally:
        conn.close()


def _load_user_rag_records(user_id: str) -> List[Dict[str, Any]]:
    """Load durable document chunks and metadata from the configured database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.filename, r.chunks_json, r.metadata_json
            FROM rag_documents r
            INNER JOIN documents d ON d.id = r.id AND d.user_id = r.user_id
            WHERE r.user_id = ?
            ORDER BY r.created_at, r.filename
            """,
            (user_id,)
        )
        records = []
        for row in cur.fetchall():
            metadata = json.loads(row["metadata_json"])
            if metadata.get("file_id") and metadata["file_id"] != row["id"]:
                continue
            chunks = json.loads(row["chunks_json"])
            records.append({
                "file_id": row["id"],
                "filename": row["filename"],
                "chunks": [
                    chunk for chunk in chunks
                    if (not chunk.get("user_id") or chunk["user_id"] == user_id)
                    and (not chunk.get("file_id") or chunk["file_id"] == row["id"])
                ],
                "metadata": metadata,
            })
        return records
    finally:
        conn.close()


def _save_user_rag_record(
    user_id: str,
    file_id: str,
    filename: str,
    chunks: List[Dict],
    metadata: Dict[str, Any],
) -> None:
    """Persist one document's RAG chunks and metadata in the configured database."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM rag_documents WHERE user_id = ? AND (id = ? OR filename = ?)",
            (user_id, file_id, filename)
        )
        cur.execute(
            "INSERT INTO rag_documents (id, user_id, filename, chunks_json, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (
                file_id,
                user_id,
                filename,
                json.dumps(chunks, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            )
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _delete_user_rag_records(user_id: str, file_id: str, filenames: set) -> None:
    """Remove durable RAG rows for a file and its legacy filename aliases."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM rag_documents WHERE user_id = ? AND id = ?",
            (user_id, file_id)
        )
        for filename in filenames:
            cur.execute(
                "DELETE FROM rag_documents WHERE user_id = ? AND filename = ?",
                (user_id, filename)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_storage_path(user_id: str) -> str:
    """Get storage path for user document chunks"""
    os.makedirs(os.path.dirname(CHROMA_PATH) or ".", exist_ok=True)
    return os.path.join(os.path.dirname(CHROMA_PATH), f"user_{user_id}_docs.json")

def _get_files_meta_path(user_id: str) -> str:
    """Get storage path for user document-level metadata and full texts"""
    os.makedirs(os.path.dirname(CHROMA_PATH) or ".", exist_ok=True)
    return os.path.join(os.path.dirname(CHROMA_PATH), f"user_{user_id}_files.json")

def _load_user_documents(user_id: str) -> List[Dict]:
    """Load user document chunks from the database, then legacy local files."""
    records = _load_user_rag_records(user_id)
    if records:
        docs = [
            chunk
            for record in records
            for chunk in record["chunks"]
        ]
        return [
            doc for doc in docs
            if "placeholder for PDF text extraction" not in doc.get("text", "")
        ]

    path = _get_storage_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                docs = json.load(f)
                owned_ids, owned_filenames = _get_user_document_refs(user_id)
                # Clean out any legacy mock placeholder chunks
                cleaned = [
                    d for d in docs 
                    if "placeholder for PDF text extraction" not in d.get("text", "")
                    and (not d.get("user_id") or d.get("user_id") == user_id)
                    and (
                        d.get("file_id") in owned_ids
                        or (not d.get("file_id") and d.get("filename") in owned_filenames)
                    )
                ]
                return cleaned
        except Exception as e:
            print(f"Error loading docs for {user_id}: {e}")
    return []

def _save_user_documents(user_id: str, documents: List[Dict]) -> None:
    """Save user document chunks to file"""
    path = _get_storage_path(user_id)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving documents: {e}")

def _load_user_files_meta(
    user_id: str,
    target_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Load file metadata from the database, then legacy local files."""
    if target_filename:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT r.id, r.filename, r.metadata_json
                FROM rag_documents r
                INNER JOIN documents d ON d.id = r.id AND d.user_id = r.user_id
                WHERE r.user_id = ? AND LOWER(r.filename) = LOWER(?)
                ORDER BY r.created_at DESC
                LIMIT 1
                """,
                (user_id, target_filename),
            )
            row = cur.fetchone()
            if row:
                metadata = json.loads(row["metadata_json"])
                if not metadata.get("file_id") or metadata["file_id"] == row["id"]:
                    return {row["filename"]: metadata}
        finally:
            conn.close()

        path = _get_files_meta_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                owned_ids, owned_filenames = _get_user_document_refs(user_id)
                item = metadata.get(target_filename)
                if item and (
                    item.get("file_id") in owned_ids
                    or (not item.get("file_id") and target_filename in owned_filenames)
                ):
                    return {target_filename: item}
            except Exception as e:
                print(f"Error loading files meta for {user_id}: {e}")
        return {}

    records = _load_user_rag_records(user_id)
    if records:
        return {
            record["filename"]: record["metadata"]
            for record in records
        }

    path = _get_files_meta_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            owned_ids, owned_filenames = _get_user_document_refs(user_id)
            return {
                filename: item
                for filename, item in metadata.items()
                if (
                    item.get("file_id") in owned_ids
                    or (not item.get("file_id") and filename in owned_filenames)
                )
            }
        except Exception as e:
            print(f"Error loading files meta for {user_id}: {e}")
    return {}

def _save_user_files_meta(user_id: str, meta: Dict[str, Any]) -> None:
    """Save user file-level metadata"""
    path = _get_files_meta_path(user_id)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving files meta: {e}")

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(vec1, vec2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))

def index_chunks(
    user_id: str, 
    file_id: str, 
    filename: str, 
    chunks: List[str],
    full_text: Optional[str] = None,
    outline: Optional[List[str]] = None,
    size_bytes: int = 0,
    page_count: int = 1,
) -> int:
    """
    Index document chunks with semantic vector embeddings and structured metadata.
    Automatically purges any existing stale chunks or mock placeholders for the same file.
    """
    documents = _load_user_documents(user_id)
    files_meta = _load_user_files_meta(user_id)
    
    # Clean out existing chunks for this filename or file_id, and legacy dummy text
    documents = [
        doc for doc in documents 
        if doc.get("filename") != filename 
        and doc.get("file_id") != file_id
        and "placeholder for PDF text extraction" not in doc.get("text", "")
    ]
    
    # Try generating semantic vector embeddings for chunks via nomic-embed-text
    embeddings = []
    try:
        if chunks:
            print(f"🧠 Generating embeddings for {len(chunks)} chunks in {filename}...")
            embeddings = ai_service.embed_many(chunks)
    except Exception as e:
        print(f"⚠️ Vector embedding notice: {e}. Falling back to lexical indexing.")
        embeddings = []
    
    new_chunks = []
    for i, chunk in enumerate(chunks):
        emb = embeddings[i] if i < len(embeddings) else None
        new_chunks.append({
            "id": f"{file_id}_{i}",
            "file_id": file_id,
            "filename": filename,
            "text": chunk,
            "user_id": user_id,
            "chunk_index": i,
            "char_length": len(chunk),
            "embedding": emb
        })
        
    documents.extend(new_chunks)
    
    # Save file-level metadata for whole-file queries
    char_len = len(full_text) if full_text else sum(len(c) for c in chunks)
    files_meta[filename] = {
        "file_id": file_id,
        "filename": filename,
        "chunks_count": len(chunks),
        "char_count": char_len,
        "full_text": full_text or "\n\n".join(chunks),
        "outline": outline or []
    }
    _save_user_rag_record(user_id, file_id, filename, new_chunks, files_meta[filename])
    _save_user_documents(user_id, documents)
    _save_user_files_meta(user_id, files_meta)
    _document_store[user_id] = documents
    _files_meta_store[user_id] = files_meta

    # Synchronize to database
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM documents WHERE user_id = ? AND (id = ? OR filename = ?)", (user_id, file_id, filename))
        existing_doc = cur.fetchone()
        if existing_doc:
            cur.execute(
                "UPDATE documents SET id = ?, filename = ?, chunks_indexed = ?, char_count = ?, page_count = ?, size_bytes = ? WHERE id = ? AND user_id = ?",
                (file_id, filename, len(chunks), char_len, max(1, page_count), size_bytes, existing_doc["id"], user_id)
            )
        else:
            cur.execute(
                "INSERT INTO documents (id, user_id, filename, chunks_indexed, char_count, page_count, size_bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (file_id, user_id, filename, len(chunks), char_len, max(1, page_count), size_bytes)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    
    print(f"📚 Successfully indexed {filename}: {len(chunks)} chunks, full text saved for user {user_id}")
    return len(chunks)

def _is_broad_query(question: str) -> bool:
    """Determine if a query is asking for whole-file summary or comprehensive overview"""
    q_lower = question.lower().strip()
    broad_indicators = [
        'summarize', 'summary', 'overview', 'main concept', 'main point', 'key point',
        'what is this document', 'what is this file', 'what is the document about',
        'what is this about', 'whole file', 'whole document', 'entire document',
        'all topic', 'topics covered', 'outline', 'explain the file', 'explain the lesson',
        'everything', 'read the whole', 'what does this cover', 'table of contents',
        'takeaways', 'review of', 'full context', 'walk me through',
        'all about', 'lesson about', 'lesson all about', 'about this lesson', 'about that lesson',
        'about the lesson', 'what is that lesson', 'what is this lesson', 'what is the lesson',
        'what is that', 'what is this', 'tell me about', 'what is it about', 'what does it teach',
        'what is covered', 'what does this lesson', 'what does that lesson'
    ]
    return any(ind in q_lower for ind in broad_indicators) or len(q_lower.split()) <= 2

def get_tutor_context(user_id: str, question: str, target_filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligent context builder for the AI Tutor:
    - If user has no uploaded materials: returns empty context with has_materials=False.
    - If user asks an overview/broad question: builds a structured multi-page overview 
      covering ALL pages of the uploaded files without exceeding CPU context limits.
    - If user asks a specific question: performs hybrid semantic vector + keyword search 
      to pinpoint the exact relevant chunks from the right page.
    """
    documents = _document_store.get(user_id) or _load_user_documents(user_id) or []
    files_meta = _files_meta_store.get(user_id) or _load_user_files_meta(user_id) or {}
    
    # Resolve an explicitly selected file only within the authenticated user's library.
    if target_filename:
        for fn in list(files_meta.keys()) + [d.get("filename", "") for d in documents]:
            if fn.lower() == target_filename.lower():
                target_filename = fn
                break
        if target_filename not in files_meta and not any(
            d.get("filename") == target_filename for d in documents
        ):
            return {
                "context": "",
                "sources": [],
                "has_materials": False,
                "read_mode": "none"
            }

    if not documents and not files_meta:
        return {
            "context": "",
            "sources": [],
            "has_materials": False,
            "read_mode": "none"
        }
        
    all_filenames = list(dict.fromkeys(
        list(files_meta.keys()) + [doc.get("filename", "Lesson") for doc in documents]
    ))
    
    # If target_filename specified and compact (<= 3,500 chars), pass entire document directly
    if target_filename and target_filename in files_meta:
        meta = files_meta[target_filename]
        c_count = meta.get("char_count", 0)
        if 0 < c_count <= 3500:
            ftext = meta.get("full_text") or "\n\n".join(d["text"] for d in documents if d.get("filename") == target_filename)
            return {
                "context": f"=== Study Material: {target_filename} ===\n{ftext}",
                "sources": [target_filename],
                "has_materials": True,
                "read_mode": "full_document"
            }

    total_chars = sum(meta.get("char_count", 0) for meta in files_meta.values()) or sum(len(d.get("text", "")) for d in documents)
    
    # 1. COMPACT DOCUMENT: If total text fits comfortably in prompt (<= 2,500 chars), pass full text
    if total_chars <= 2500 and total_chars > 0 and not target_filename:
        context_parts = []
        for fname in all_filenames:
            meta = files_meta.get(fname)
            ftext = meta.get("full_text") if meta else "\n\n".join(d["text"] for d in documents if d.get("filename") == fname)
            context_parts.append(f"=== Study Material: {fname} ===\n{ftext}")
            
        return {
            "context": "\n\n".join(context_parts),
            "sources": all_filenames,
            "has_materials": True,
            "read_mode": "full_document"
        }
        
    # 2. BROAD QUERY (Summarize, overview, whole file):
    # Construct an intelligent multi-page digest that gives full visibility across all pages
    if _is_broad_query(question):
        # Determine relevant files: target_filename if explicitly set, or keyword-matched,
        # otherwise defaults to the most recently uploaded document (last in all_filenames)
        if target_filename and target_filename in all_filenames:
            target_files = [target_filename]
        elif len(all_filenames) > 1:
            q_lower = question.lower()
            generic_words = {'what', 'that', 'this', 'about', 'lesson', 'file', 'document', 'pdf', 'notes', 'tell', 'show', 'explain', 'all', 'the', 'is', 'in'}
            specific_tokens = [t for t in re.findall(r'\w+', q_lower) if len(t) > 2 and t not in generic_words]
            scored = []
            for fname in all_filenames:
                score = 0
                fname_clean = fname.lower()
                for token in specific_tokens:
                    if token in fname_clean:
                        score += 5
                meta = files_meta.get(fname, {})
                full_samp = meta.get("full_text", "")[:1200].lower()
                for token in specific_tokens:
                    if token in full_samp:
                        score += 1
                scored.append((score, fname))
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored and scored[0][0] > 0:
                target_files = [scored[0][1]]
            else:
                target_files = [all_filenames[-1]]
        else:
            target_files = all_filenames

        context_parts = []
        for fname in target_files:
            meta = files_meta.get(fname, {})
            outline = meta.get("outline", [])
            f_chunks = [d for d in documents if d.get("filename") == fname]
            n = len(f_chunks)
            
            section_summary = [f"=== Document: {fname} ==="]
            if outline:
                section_summary.append("Document Topics / Sections:\n" + "\n".join(f"- {o}" for o in outline[:8]))
            
            # Construct structured multi-page overview:
            if f_chunks:
                first_excerpt = f_chunks[0]['text'][:450].strip()
                section_summary.append(f"[Beginning / Page 1 Overview]:\n{first_excerpt}")
                
                # If there are multiple pages, give a quick snapshot across subsequent pages
                if n > 1:
                    page_snapshots = []
                    for chunk in f_chunks[1:min(n, 6)]:
                        page_match = re.search(r'\[Page\s*(\d+)\]', chunk.get('text', ''))
                        page_label = f"Page {page_match.group(1)}" if page_match else "Section"
                        # Extract first meaningful non-empty lines
                        lines = [l.strip() for l in chunk.get('text', '').split('\n') if l.strip() and not l.startswith('[Page')]
                        snippet = " | ".join(lines[:2])[:120]
                        if snippet:
                            page_snapshots.append(f"- [{page_label}]: {snippet}")
                    if page_snapshots:
                        section_summary.append("Highlights Across Pages:\n" + "\n".join(page_snapshots))
                
                # Concluding excerpt if more than 2 pages
                if n > 2:
                    last_excerpt = f_chunks[-1]['text'][:200].strip()
                    section_summary.append(f"[Concluding Excerpt]:\n{last_excerpt}")
                    
            context_parts.append("\n\n".join(section_summary))
            
        return {
            "context": "\n\n====================\n\n".join(context_parts),
            "sources": target_files,
            "has_materials": True,
            "read_mode": "whole_document_overview"
        }
        
    # 3. TARGETED QUESTION:
    # Use hybrid retrieval (semantic vectors + keyword overlap) to pick the top 2-3 chunks (~1,500 chars)
    passages = retrieve(user_id, question, limit=3, target_filename=target_filename)
    if not passages:
        # Fallback to the first couple of chunks
        passages = [d for d in documents if not target_filename or d.get('filename') == target_filename][:2] or documents[:2]
        
    context_text = "\n\n---\n\n".join(
        f"Source: {p['filename']}\n{p['text']}" for p in passages
    )
    sources = list(dict.fromkeys(p["filename"] for p in passages))
    return {
        "context": context_text,
        "sources": sources,
        "has_materials": True,
        "read_mode": "targeted_retrieval"
    }

def retrieve(user_id: str, question: str, limit: int = 4, target_filename: Optional[str] = None) -> List[Dict]:
    """
    Hybrid semantic vector + keyword retrieval.
    Balances semantic meaning with exact keyword matches for high precision.
    """
    documents = _document_store.get(user_id) or _load_user_documents(user_id)
    if not documents:
        return []
        
    if target_filename:
        filtered = [d for d in documents if d.get('filename', '').lower() == target_filename.lower()]
        documents = filtered
    
    # 1. Try semantic embedding for the query
    q_embedding = None
    try:
        q_embs = ai_service.embed_many([question])
        if q_embs and len(q_embs) > 0:
            q_embedding = q_embs[0]
    except Exception as e:
        print(f"Embedding query note: {e}")
        q_embedding = None
        
    # 2. Prepare keyword tokens
    question_lower = question.lower()
    question_words = set(re.findall(r'\b\w+\b', question_lower))
    stop_words = {'the', 'is', 'at', 'which', 'on', 'and', 'or', 'but', 'in', 'with', 'a', 'an', 'what', 'who', 'how', 'why', 'are', 'was', 'were'}
    question_keywords = question_words - stop_words
    important_terms = [w for w in question_keywords if len(w) > 3]
    
    scored_docs = []
    for doc in documents:
        text = doc.get("text", "")
        text_lower = text.lower()
        text_words = set(re.findall(r'\b\w+\b', text_lower))
        
        # A. Semantic Score (0.0 to 1.0)
        semantic_score = 0.0
        doc_emb = doc.get("embedding")
        if q_embedding and doc_emb:
            semantic_score = max(0.0, _cosine_similarity(q_embedding, doc_emb))
            
        # B. Keyword Score
        keyword_overlap = len(question_keywords.intersection(text_words))
        important_matches = sum(1 for term in important_terms if term in text_lower)
        phrase_bonus = 2.0 if any(len(term) > 4 and term in text_lower for term in important_terms) else 0.0
        
        lexical_score = (keyword_overlap * 2.0) + (important_matches * 3.0) + phrase_bonus
        # Normalize lexical score roughly between 0.0 and 1.0
        norm_lexical = min(1.0, lexical_score / max(1.0, len(question_keywords) * 3.0))
        
        # C. Combined Hybrid Score
        if q_embedding and doc_emb:
            total_score = (0.65 * semantic_score) + (0.35 * norm_lexical)
        else:
            total_score = norm_lexical
            
        if total_score > 0.1 or lexical_score > 0:
            scored_docs.append((total_score, doc))
            
    scored_docs.sort(reverse=True, key=lambda x: x[0])
    
    results = []
    for score, doc in scored_docs[:limit]:
        results.append({
            "text": doc["text"],
            "filename": doc["filename"],
            "chunk_index": doc.get("chunk_index", 0),
            "match_score": round(score, 3)
        })
        
    return results

def delete_file_chunks(user_id: str, file_id: str, filename: Optional[str] = None) -> bool:
    """
    Permanently delete all chunks and metadata for a specific file across:
    1. In-memory stores (_document_store, _files_meta_store)
    2. Disk JSON files (user_{user_id}_docs.json, user_{user_id}_files.json)
    3. The configured database (RAG chunks and document metadata)
    """
    documents = _document_store.get(user_id) or _load_user_documents(user_id) or []
    files_meta = _files_meta_store.get(user_id) or _load_user_files_meta(user_id) or {}
    
    # Identify matching filenames
    target_filenames = set()
    if filename:
        target_filenames.add(filename)
        
    for d in documents:
        if d.get("file_id") == file_id or d.get("filename") == file_id or (filename and d.get("filename") == filename):
            if d.get("filename"):
                target_filenames.add(d.get("filename"))
                
    for fn, meta in list(files_meta.items()):
        if fn == file_id or meta.get("file_id") == file_id or (filename and fn == filename):
            target_filenames.add(fn)
            del files_meta[fn]
            
    # Also check case-insensitive match in files_meta
    for fn in list(files_meta.keys()):
        if fn.lower() == file_id.lower() or (filename and fn.lower() == filename.lower()):
            target_filenames.add(fn)
            del files_meta[fn]
            
    if file_id in files_meta:
        target_filenames.add(file_id)
        del files_meta[file_id]

    # Filter out chunks
    new_documents = [
        d for d in documents 
        if d.get("file_id") != file_id 
        and d.get("filename") not in target_filenames 
        and d.get("filename") != file_id
        and (not filename or d.get("filename") != filename)
        and (not filename or d.get("filename", "").lower() != filename.lower())
    ]
    
    _delete_user_rag_records(user_id, file_id, target_filenames)
    _save_user_documents(user_id, new_documents)
    _save_user_files_meta(user_id, files_meta)
    _document_store[user_id] = new_documents
    _files_meta_store[user_id] = files_meta
    
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM documents WHERE user_id = ? AND id = ?",
            (user_id, file_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        
    print(f"🗑️ Permanently deleted file '{file_id}' (targets: {list(target_filenames)}) for user {user_id}")
    return True

def get_user_document_stats(user_id: str) -> Dict:
    """Return document metadata from rows owned by this user, never shared RAG caches."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, filename, chunks_indexed, char_count, page_count, size_bytes
            FROM documents
            WHERE user_id = ?
            ORDER BY created_at DESC, filename
            """,
            (user_id,)
        )
        files = [
            {
                "filename": row["filename"],
                "file_id": row["id"],
                "chunks_indexed": row["chunks_indexed"] or 0,
                "char_count": row["char_count"] or 0,
                "page_count": row["page_count"] or 1,
                "size_bytes": row["size_bytes"] or 0,
            }
            for row in cur.fetchall()
        ]
    finally:
        conn.close()

    total_chars = sum(file["char_count"] for file in files)
    return {
        "total_chunks": sum(f["chunks_indexed"] for f in files),
        "files": files,
        "total_chars": total_chars
    }

def sync_initial_documents_to_db():
    """Ensure all existing documents are synced into the database table on startup"""
    try:
        import uuid
        storage_dir = os.path.dirname(CHROMA_PATH) or "."
        if os.path.isdir(storage_dir):
            for entry in os.listdir(storage_dir):
                if not entry.startswith("user_") or not entry.endswith("_docs.json"):
                    continue

                user_id = entry[len("user_"):-len("_docs.json")]
                docs_path = os.path.join(storage_dir, entry)
                meta_path = _get_files_meta_path(user_id)
                try:
                    with open(docs_path, "r", encoding="utf-8") as f:
                        legacy_docs = json.load(f)
                    with open(meta_path, "r", encoding="utf-8") as f:
                        legacy_meta = json.load(f)
                except FileNotFoundError:
                    continue

                saved_filenames = {
                    record["filename"] for record in _load_user_rag_records(user_id)
                }
                for filename, meta in legacy_meta.items():
                    if filename in saved_filenames:
                        continue
                    file_id = meta.get("file_id") or str(uuid.uuid4())
                    chunks = [
                        doc for doc in legacy_docs
                        if doc.get("file_id") == file_id or doc.get("filename") == filename
                    ]
                    _save_user_rag_record(user_id, file_id, filename, chunks, meta)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users")
        known_users = {row["id"] for row in cur.fetchall()}
        for user_id in known_users:
            cur.execute(
                "SELECT id, filename, metadata_json FROM rag_documents WHERE user_id = ?",
                (user_id,)
            )
            for record in cur.fetchall():
                filename = record["filename"]
                file_id = record["id"]
                meta = json.loads(record["metadata_json"])
                if meta.get("file_id") and meta["file_id"] != file_id:
                    continue
                cur.execute(
                    "SELECT user_id FROM documents WHERE id = ?",
                    (file_id,)
                )
                id_owner = cur.fetchone()
                if id_owner and id_owner["user_id"] != user_id:
                    continue
                cur.execute(
                    "SELECT id FROM documents WHERE user_id = ? AND (id = ? OR filename = ?)",
                    (user_id, file_id, filename)
                )
                if cur.fetchone():
                    continue
                cur.execute(
                    """
                    INSERT INTO documents
                        (id, user_id, filename, chunks_indexed, char_count, page_count, size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        user_id,
                        filename,
                        meta.get("chunks_count", 1),
                        meta.get("char_count", 0),
                        1,
                        0,
                    )
                )
        conn.commit()
        conn.close()
        print("✅ Synced active documents to database.")
    except Exception as e:
        print(f"⚠️ Document DB sync notice: {e}")
