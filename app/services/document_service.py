import io
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any

def extract_pdf_structured(data: bytes) -> Dict[str, Any]:
    """
    Extract structured text from PDF page by page using PyMuPDF.
    Preserves page boundaries, extracts major headings/outlines,
    and returns full text with clear page markers.
    """
    try:
        pdf_document = fitz.open(stream=data, filetype="pdf")
        pages = []
        full_text_parts = []
        outline = []
        total_pages = len(pdf_document)
        
        print(f"📄 Processing PDF: {total_pages} pages")
        
        for page_num in range(total_pages):
            page = pdf_document.load_page(page_num)
            raw_text = page.get_text("text") or ""
            cleaned = raw_text.strip()
            
            if cleaned:
                page_str = f"[Page {page_num + 1}]\n{cleaned}"
                pages.append({
                    "page_num": page_num + 1,
                    "text": cleaned,
                    "tagged_text": page_str
                })
                full_text_parts.append(page_str)
                
                # Extract potential headings / questions from this page
                lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
                for line in lines:
                    # Look for section indicators like "A. ...", "1. ...", "Chapter ...", or short bold-like lines
                    if re.match(r'^([A-Z]\.|\d+\.|\bChapter\b|\bSection\b|\bPart\b)', line, re.IGNORECASE):
                        if len(line) <= 120:
                            outline.append(f"Page {page_num + 1}: {line}")
        
        pdf_document.close()
        
        full_text = "\n\n".join(full_text_parts)
        print(f"✅ Extracted {len(full_text)} characters across {len(pages)} non-empty pages (out of {total_pages})")
        
        return {
            "full_text": full_text,
            "page_count": total_pages,
            "pages": pages,
            "outline": outline[:25]  # Cap outline entries to prevent bloat
        }
        
    except Exception as e:
        print(f"❌ PDF extraction error: {e}")
        return {
            "full_text": "",
            "page_count": 0,
            "pages": [],
            "outline": [],
            "error": str(e)
        }

def extract_pdf(data: bytes) -> str:
    """
    Extract text from PDF using PyMuPDF for accurate text extraction.
    Returns full text with clear [Page X] tags.
    """
    structured = extract_pdf_structured(data)
    return structured.get("full_text", "")

def _paginate_paragraphs(paragraphs: List[str], outline: List[str]) -> Dict[str, Any]:
    pages = []
    full_text_parts = []
    current_page_lines = []
    current_len = 0
    page_num = 1
    
    for p in paragraphs:
        current_page_lines.append(p)
        current_len += len(p)
        if current_len >= 1400:
            p_text = '\n\n'.join(current_page_lines)
            page_str = f"[Page {page_num}]\n{p_text}"
            pages.append({'page_num': page_num, 'text': p_text, 'tagged_text': page_str})
            full_text_parts.append(page_str)
            page_num += 1
            current_page_lines = []
            current_len = 0
            
    if current_page_lines or not pages:
        p_text = '\n\n'.join(current_page_lines) if current_page_lines else ''
        page_str = f"[Page {page_num}]\n{p_text}"
        pages.append({'page_num': page_num, 'text': p_text, 'tagged_text': page_str})
        full_text_parts.append(page_str)
        
    full_text = "\n\n".join(full_text_parts)
    print(f"✅ Extracted {len(full_text)} characters across {len(pages)} pages")
    return {
        "full_text": full_text,
        "page_count": len(pages),
        "pages": pages,
        "outline": outline[:25]
    }

def extract_docx_structured(data: bytes) -> Dict[str, Any]:
    """
    Extract structured text and headings from a DOCX file.
    Supports python-docx with pure-python zipfile+xml fallback.
    """
    paragraphs = []
    outline = []
    
    # Attempt 1: python-docx
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        for p in doc.paragraphs:
            txt = p.text.strip()
            if txt:
                paragraphs.append(txt)
                style_name = getattr(p.style, 'name', '') or ''
                if any(h in style_name for h in ('Heading', 'Title')):
                    outline.append(txt[:120])
                elif re.match(r'^([A-Z]\.|\d+\.|\bChapter\b|\bModule\b|\bLecture\b|\bTopic\b|\bUnit\b|\bPart\b)', txt, re.IGNORECASE) and len(txt) <= 120:
                    outline.append(txt[:120])
                    
        for tbl in doc.tables:
            for row in tbl.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    paragraphs.append(" | ".join(row_cells))
    except Exception as e:
        print(f"⚠️ python-docx notice: {e}. Trying zipfile XML fallback.")
        # Attempt 2: zipfile + xml.etree.ElementTree
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml_content = z.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                for p_elem in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                    p_text = ''.join(t.text for t in p_elem.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if t.text).strip()
                    if p_text:
                        paragraphs.append(p_text)
                        if re.match(r'^([A-Z]\.|\d+\.|\bChapter\b|\bModule\b|\bLecture\b|\bTopic\b|\bUnit\b)', p_text, re.IGNORECASE) and len(p_text) <= 120:
                            outline.append(p_text[:120])
        except Exception as zerr:
            print(f"❌ DOCX extraction error: {zerr}")
            return {
                "full_text": "",
                "page_count": 0,
                "pages": [],
                "outline": [],
                "error": str(zerr)
            }

    if not paragraphs:
        return {
            "full_text": "",
            "page_count": 0,
            "pages": [],
            "outline": [],
            "error": "No text extracted from DOCX document"
        }

    return _paginate_paragraphs(paragraphs, outline)

def extract_txt_structured(data: bytes) -> Dict[str, Any]:
    """Extract structured text from plaintext / markdown files"""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = data.decode("latin-1", errors="replace")
        
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    outline = []
    for p in paragraphs:
        for line in p.split("\n"):
            line = line.strip()
            if line.startswith(('#', '##', '###', 'Chapter', 'Module', 'Section')):
                outline.append(line[:120])
                
    return _paginate_paragraphs(paragraphs, outline)

def extract_document_structured(data: bytes, filename: str) -> Dict[str, Any]:
    """Dispatcher to extract structured text based on file extension"""
    fn_lower = filename.lower()
    if fn_lower.endswith(".pdf"):
        return extract_pdf_structured(data)
    elif fn_lower.endswith((".docx", ".doc")):
        return extract_docx_structured(data)
    elif fn_lower.endswith((".txt", ".md", ".csv")):
        return extract_txt_structured(data)
    else:
        try:
            return extract_pdf_structured(data)
        except Exception:
            return extract_txt_structured(data)

def split_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    """
    Split text into overlapping chunks for context preservation while retaining
    page references ([Page X]).
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    
    if not text.strip():
        return []
    
    # Track current page marker
    current_page = "[Page 1]"
    
    # Split by double newlines (paragraphs)
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # Update current page marker if paragraph begins with [Page X]
        page_match = re.search(r'\[Page\s*(\d+)\]', paragraph)
        if page_match:
            current_page = f"[Page {page_match.group(1)}]"
        
        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(paragraph) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                
                # Start new chunk with overlap
                if overlap > 0 and len(current_chunk) > overlap:
                    overlap_text = current_chunk[-overlap:].strip()
                    break_point = max(
                        overlap_text.rfind('. '),
                        overlap_text.rfind('\n'),
                        overlap_text.rfind(' ')
                    )
                    if break_point > 0:
                        current_chunk = current_page + "\n" + overlap_text[break_point:].strip() + "\n\n"
                    else:
                        current_chunk = current_page + "\n"
                else:
                    current_chunk = current_page + "\n"
        
        if current_chunk:
            current_chunk += "\n\n" + paragraph
        else:
            current_chunk = paragraph
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Handle any extra-long chunks
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 1.3:
            final_chunks.append(chunk)
        else:
            sentences = chunk.split('. ')
            temp_chunk = ""
            for sentence in sentences:
                if len(temp_chunk) + len(sentence) <= chunk_size:
                    temp_chunk += sentence + ". "
                else:
                    if temp_chunk:
                        final_chunks.append(temp_chunk.strip())
                    temp_chunk = sentence + ". "
            if temp_chunk:
                final_chunks.append(temp_chunk.strip())
    
    print(f"📊 Split into {len(final_chunks)} chunks (avg {sum(len(c) for c in final_chunks) // len(final_chunks) if final_chunks else 0} chars each)")
    return final_chunks
