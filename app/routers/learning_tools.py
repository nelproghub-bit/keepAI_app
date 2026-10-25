import json
import re
import random
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator
from app.core.security import get_current_student_user
from app.core.database import get_connection
from app.services.user_service import user_service
from app.services.progress_service import record_activity
from app.services.rag_service import get_tutor_context, _load_user_documents, _load_user_files_meta
from app.services.gemini_service import AIProviderError, generate

router = APIRouter(tags=["Learning Tools"])

class LessonRequest(BaseModel):
    topic: str = Field(default="Quiz", max_length=500)
    document_name: Optional[str] = None
    question_count: Optional[int] = Field(default=5, ge=1, le=100)
    question_counts: Optional[Dict[str, int]] = None

    @model_validator(mode="after")
    def validate_question_counts(self):
        if self.question_counts is None:
            return self
        valid_types = {
            "identification",
            "multiple_choice",
            "true_false",
            "fill_blank",
            "matching",
        }
        if not self.question_counts or set(self.question_counts) - valid_types:
            raise ValueError("Choose at least one supported question type.")
        if any(count < 1 for count in self.question_counts.values()):
            raise ValueError("Each selected question type must have at least one question.")
        if sum(self.question_counts.values()) > 100:
            raise ValueError("The total quiz size cannot exceed 100 questions.")
        return self


QUESTION_COUNT_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*-?\s*(?:questions?|quizzes|quiz|items?|mcqs?|multiple\s*choice)\b", re.IGNORECASE),
    re.compile(r"\b(?:quiz|exam|test)\s+(?:of|with|for)\s+(\d{1,3})\b", re.IGNORECASE),
)


def requested_question_count(topic: str) -> Optional[int]:
    for pattern in QUESTION_COUNT_PATTERNS:
        match = pattern.search(topic)
        if match:
            count = int(match.group(1))
            if 1 <= count <= 100:
                return count
    return None

class FlashcardRequest(BaseModel):
    topic: str = Field(default="Flashcards", max_length=500)
    document_name: Optional[str] = None
    card_count: Optional[int] = Field(default=10, ge=1, le=100)
    card_type: Optional[str] = Field(default="term-definition")  # term-definition | question-answer | concept-example | fill-blank

def get_all_document_chunks(target_filename: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve chunks only from the supplied owner's isolated document store."""
    if not user_id:
        return []
    documents = _load_user_documents(user_id)
    if target_filename:
        documents = [
            document for document in documents
            if document.get("filename", "").lower() == target_filename.lower()
        ]
    return documents

def get_owned_document_name(user_id: str, document_name: Optional[str]) -> Optional[str]:
    """Resolve an optional selected filename to a document owned by this student."""
    if not document_name:
        return None
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT filename FROM documents
            WHERE user_id = ? AND LOWER(filename) = LOWER(?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, document_name),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row["filename"]

def get_lesson_context(user_id: str, topic: str, target_filename: Optional[str] = None) -> tuple[str, list[str]]:
    # If a specific document is requested, prioritize loading that exact document!
    if target_filename:
        chunks = get_all_document_chunks(target_filename, user_id)
        if chunks:
            combined_text = "\n\n".join(c.get("text", "") for c in chunks)
            return combined_text[:12000], [target_filename]

    ctx = get_tutor_context(user_id, topic, target_filename=target_filename)
    if ctx and ctx.get("has_materials"):
        return ctx["context"], ctx["sources"]

    if not ctx or not ctx.get("has_materials"):
        raise HTTPException(404, "No lesson content found. Please upload a PDF or document in the Library first.")
    return ctx["context"], ctx["sources"]

def extract_document_facts(context: str, target_filename: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract factual statements, definitions, and concepts directly from the document text."""
    chunks = get_all_document_chunks(target_filename, user_id)
    raw_texts = [c.get("text", "") for c in chunks if c.get("text")]
    full_text = "\n\n".join(raw_texts) if raw_texts else context
    
    facts = []
    lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 15]
    
    for line in lines:
        if line.startswith("===") or line.startswith("[Page") or line.startswith("IT ELEC"):
            continue
        # Match any educational definition, explanation, or outcome pattern
        lower_line = line.lower()
        if any(marker in lower_line for marker in [
            " is a ", " is an ", " is the ", " are ", " are the ", " defined as ", 
            " refers to ", " means ", " involves ", " focuses on ", " goal ", " objective ",
            " principle", " example:", " component", " purpose", " usability", " interface"
        ]):
            facts.append(line)
            
    return facts


def build_extractive_quiz_fallback(
    context: str,
    target_count: int,
    existing_questions: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build simple, verifiable quiz items from statements copied from the lesson."""
    questions = list(existing_questions or [])
    seen_questions = {
        re.sub(r"\s+", " ", item.get("question", "")).strip().casefold()
        for item in questions
    }
    statements = []
    for part in re.split(r"(?<=[.!?])\s+|(?<=;)\s+|\n+", context):
        statement = re.sub(r"^\s*(?:[-*•]\s*|\d+[.)]\s*|\[Page\s*\d+\]\s*)+", "", part).strip()
        if (
            len(statement) >= 30
            and len(statement) <= 500
            and not statement.startswith("===")
            and not statement.startswith("[Page")
        ):
            statements.append(statement)

    definition_pattern = re.compile(
        r"^(?P<term>[^.!?:;]{2,90}?)\s+"
        r"(?P<link>is defined as|is|are|means|refers to|represents|consists of|includes|involves)\s+"
        r"(?P<definition>[^.!?;]{12,300}[.!?]?)$",
        re.IGNORECASE,
    )
    definitions = []
    for statement in statements:
        match = definition_pattern.match(statement)
        if not match:
            continue
        term = match.group("term").strip(" \t-–—")
        answer = match.group("definition").strip()
        if len(term) >= 2 and len(answer) >= 12:
            definitions.append((statement, term, answer))

    for evidence, term, answer in definitions:
        question_text = f"According to the selected lesson, what is {term}?"
        normalized_question = re.sub(r"\s+", " ", question_text).strip().casefold()
        if normalized_question in seen_questions:
            continue
        distractors = []
        for _, other_term, other_answer in definitions:
            if other_term.casefold() != term.casefold() and other_answer.casefold() != answer.casefold():
                if other_answer not in distractors:
                    distractors.append(other_answer)
            if len(distractors) == 3:
                break
        if len(distractors) < 3:
            continue
        choices = [answer, *distractors]
        random.shuffle(choices)
        questions.append(
            {
                "question": question_text,
                "choices": choices,
                "correct_answer": answer,
                "explanation": f"The selected document states: {evidence}",
                "source_excerpt": evidence,
                "generation_method": "extractive",
            }
        )
        seen_questions.add(normalized_question)
        if len(questions) == target_count:
            return questions

    stop_words = {
        "about", "after", "also", "among", "because", "been", "being", "between",
        "could", "does", "during", "each", "from", "have", "into", "more", "most",
        "other", "over", "same", "should", "some", "such", "than", "that", "their",
        "them", "then", "there", "these", "they", "this", "those", "through", "under",
        "using", "very", "what", "when", "where", "which", "while", "with", "would",
        "your", "have", "will", "were", "also", "user", "users", "system", "systems",
    }
    term_pool = []
    for candidate in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", context):
        if candidate.casefold() not in stop_words and candidate.casefold() not in {
            term.casefold() for term in term_pool
        }:
            term_pool.append(candidate)

    for statement in statements:
        terms = []
        for candidate in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", statement):
            if (
                candidate.casefold() not in stop_words
                and candidate.casefold() not in {term.casefold() for term in terms}
            ):
                terms.append(candidate)
        terms.sort(key=lambda value: (-len(value), value.casefold()))
        for term in terms[:2]:
            question_text = (
                "Complete the statement from the selected lesson: "
                f'"{re.sub(re.escape(term), "____", statement, count=1, flags=re.IGNORECASE)}"'
            )
            normalized_question = re.sub(r"\s+", " ", question_text).strip().casefold()
            if normalized_question in seen_questions:
                continue
            distractors = []
            for offset in range(len(term_pool)):
                candidate = term_pool[(offset + len(questions)) % len(term_pool)]
                if candidate.casefold() != term.casefold() and candidate.casefold() not in {
                    choice.casefold() for choice in distractors
                }:
                    distractors.append(candidate)
                if len(distractors) == 3:
                    break
            if len(distractors) < 3:
                continue
            choices = [term, *distractors]
            random.shuffle(choices)
            questions.append(
                {
                    "question": question_text,
                    "choices": choices,
                    "correct_answer": term,
                    "explanation": f"The selected document states: {statement}",
                    "source_excerpt": statement,
                    "generation_method": "extractive",
                }
            )
            seen_questions.add(normalized_question)
            if len(questions) == target_count:
                return questions

    return questions[:target_count]


def generate_grounded_quiz_questions(
    context: str,
    target_count: int,
    topic: str,
) -> List[Dict[str, Any]]:
    """Generate quiz questions only when their answer is supported by source evidence."""
    if not context.strip():
        raise HTTPException(404, "No readable content was found in the selected document.")

    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    questions: List[Dict[str, Any]] = []
    seen_questions = set()
    attempts = 0
    max_attempts = ((target_count + 2) // 3) + 2

    while len(questions) < target_count and attempts < max_attempts:
        batch_count = min(3, target_count - len(questions))
        attempts += 1
        prompt = (
            f"Create exactly {batch_count} multiple-choice questions for the focus topic: {topic}. "
            "Use only facts explicitly stated in the selected lesson. Do not use prior knowledge, "
            "other documents, or invented facts. Each question must have four distinct choices, "
            "one correct_answer copied exactly from its evidence, and a concise explanation. "
            "The evidence field must be an exact excerpt copied from the lesson and must contain "
            "the correct_answer verbatim. If the lesson does not support a requested question, "
            "do not invent one. Return a JSON array only, with each object containing: question, "
            "choices, correct_answer, explanation, evidence.\n"
            f"FOCUS TOPIC: {topic}\nSELECTED LESSON:\n{context}"
        )
        try:
            raw = generate(
                prompt,
                system=(
                    "You create document-grounded assessments. Treat the selected lesson as the only "
                    "source of truth. Never fill gaps with general knowledge. Return valid JSON only."
                ),
                has_sources=True,
            )
        except AIProviderError as exc:
            questions = build_extractive_quiz_fallback(
                context,
                target_count,
                existing_questions=questions,
            )
            if len(questions) == target_count:
                return questions
            raise HTTPException(
                502,
                "The quiz AI is unavailable, and the selected document does not contain enough clear statements to build this many questions. Try fewer questions or try again later.",
            ) from exc

        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        try:
            parsed = json.loads(cleaned.strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue

        normalized_context = normalize(context)
        for item in parsed:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            choices = item.get("choices")
            answer = item.get("correct_answer")
            explanation = item.get("explanation")
            evidence = item.get("evidence")
            if (
                not isinstance(question, str)
                or not question.strip()
                or not isinstance(choices, list)
                or len(choices) != 4
                or any(not isinstance(choice, str) or not choice.strip() for choice in choices)
                or len({normalize(choice) for choice in choices}) != 4
                or not isinstance(answer, str)
                or not isinstance(explanation, str)
                or not isinstance(evidence, str)
                or not evidence.strip()
                or len(evidence) > 500
            ):
                continue
            normalized_evidence = normalize(evidence)
            if (
                normalized_evidence not in normalized_context
                or normalize(answer) not in normalized_evidence
                or normalize(answer) not in {normalize(choice) for choice in choices}
            ):
                continue
            normalized_question = normalize(question)
            if normalized_question in seen_questions:
                continue

            seen_questions.add(normalized_question)
            questions.append(
                {
                    "question": question.strip(),
                    "choices": choices,
                    "correct_answer": answer,
                    "explanation": explanation.strip(),
                    "source_excerpt": evidence.strip(),
                    "generation_method": "ai",
                }
            )
            if len(questions) == target_count:
                break

    if len(questions) != target_count:
        questions = build_extractive_quiz_fallback(
            context,
            target_count,
            existing_questions=questions,
        )
    if len(questions) != target_count:
        raise HTTPException(
            502,
            "The quiz AI could not create enough questions with verifiable evidence from the selected document. Try fewer questions or a narrower focus topic.",
        )
    return questions


def build_typed_quiz_questions(
    source_questions: List[Dict[str, Any]],
    question_counts: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Format grounded multiple-choice source items into requested assessment types."""
    result: List[Dict[str, Any]] = []
    source_index = 0

    for question_type, count in question_counts.items():
        if question_type == "matching":
            for _ in range(count):
                pair_sources = [
                    source_questions[(source_index + offset) % len(source_questions)]
                    for offset in range(min(3, len(source_questions)))
                ]
                source_index += len(pair_sources)
                pairs = [
                    {
                        "left": item["question"],
                        "right": item["correct_answer"],
                    }
                    for item in pair_sources
                ]
                choices = [pair["right"] for pair in pairs]
                random.shuffle(choices)
                result.append(
                    {
                        "question_type": question_type,
                        "question": "Match each study question with its correct answer.",
                        "pairs": pairs,
                        "choices": choices,
                        "explanation": "Review each question and connect it to the answer supported by the lesson.",
                        "source_excerpt": "\n\n".join(
                            item["source_excerpt"]
                            for item in pair_sources
                            if item.get("source_excerpt")
                        ),
                    }
                )
            continue

        for question_number in range(count):
            source = source_questions[source_index % len(source_questions)]
            source_index += 1
            correct_answer = source["correct_answer"]
            question = source["question"]
            explanation = source.get("explanation", "")

            if question_type == "multiple_choice":
                result.append({**source, "question_type": question_type})
            elif question_type == "identification":
                result.append(
                    {
                        "question_type": question_type,
                        "question": question,
                        "correct_answer": correct_answer,
                        "accepted_answers": [correct_answer],
                        "explanation": explanation,
                        "source_excerpt": source.get("source_excerpt", ""),
                    }
                )
            elif question_type == "true_false":
                choices = source.get("choices", [])
                is_true = question_number % 2 == 0 and correct_answer in choices
                statement_answer = (
                    correct_answer
                    if is_true
                    else next(
                        (choice for choice in choices if choice != correct_answer),
                        correct_answer,
                    )
                )
                result.append(
                    {
                        "question_type": question_type,
                        "question": (
                            f'The answer to "{question}" is "{statement_answer}". '
                            "True or false?"
                        ),
                        "choices": ["True", "False"],
                        "correct_answer": "True" if is_true else "False",
                        "explanation": (
                            explanation if is_true
                            else f"The correct answer is: {correct_answer}. {explanation}"
                        ),
                        "source_excerpt": source.get("source_excerpt", ""),
                    }
                )
            elif question_type == "fill_blank":
                result.append(
                    {
                        "question_type": question_type,
                        "question": f'The answer to "{question}" is ____.',
                        "correct_answer": correct_answer,
                        "accepted_answers": [correct_answer],
                        "explanation": explanation,
                        "source_excerpt": source.get("source_excerpt", ""),
                    }
                )

    return result


@router.post("/learning/summary")
def create_summary(
    request: LessonRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_name)
    context, sources = get_lesson_context(uid, request.topic, target_filename=document_name)
    
    user_service.increment_stat(current_user["id"], "summaries_generated", 1)

    result = generate(
        f"Summarize the following lesson about {request.topic} using simple, clear, and easy-to-understand words. "
        "Use short headings, bullet points, and plain definitions so any student can understand quickly. Do not add "
        f"unsupported facts.\n\nLESSON:\n{context}",
        system="You are KeepAI, a helpful study assistant. Explain concepts in simple, clear, everyday words."
    )
    record_activity(
        current_user["id"],
        "summary_generated",
        "Generated a lesson summary",
        document_name or request.topic,
    )
    return {"summary": result, "sources": sources}

@router.post("/learning/quiz")
def create_quiz(
    request: LessonRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_name)
    
    if request.question_counts:
        question_counts = request.question_counts
        source_count = sum(
            count * (3 if question_type == "matching" else 1)
            for question_type, count in question_counts.items()
        )
    else:
        num_questions = request.question_count or 5
        topic_count = requested_question_count(request.topic)
        if topic_count is not None:
            num_questions = topic_count
        num_questions = max(1, min(100, num_questions))
        question_counts = {"multiple_choice": num_questions}
        source_count = num_questions

    # 2. Extract lesson context for the specified document
    context, sources = get_lesson_context(uid, request.topic, target_filename=document_name)
    
    source_questions = generate_grounded_quiz_questions(
        context=context,
        target_count=source_count,
        topic=request.topic,
    )
    typed_questions = build_typed_quiz_questions(source_questions, question_counts)
    user_service.increment_stat(current_user["id"], "quizzes_attempted", 1)
    generation_mode = (
        "document_extract"
        if any(question.get("generation_method") == "extractive" for question in source_questions)
        else "ai"
    )

    if current_user:
        record_activity(
            current_user["id"],
            "quiz_generated",
            "Generated a practice quiz",
            document_name or request.topic,
        )
    return {
        "topic": request.topic,
        "document_name": document_name or (sources[0] if sources else "Uploaded Document"),
        "total_questions": len(typed_questions),
        "question_counts": question_counts,
        "generation_mode": generation_mode,
        "questions": typed_questions,
        "sources": sources
    }


# ==================== FLASHCARD SYNTHESIZER & ENDPOINT ====================

FLASHCARD_TYPE_PROMPTS = {
    "term-definition": (
        "Generate {count} high-quality flashcards in a Term & Definition format based strictly on the lesson below. "
        "Each card should have a clear key term, principle, or concept on the 'front' and an accurate, "
        "student-friendly explanation/definition on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "question-answer": (
        "Generate {count} Question & Answer flashcards based strictly on the lesson below. "
        "Each card should have an insightful study question on the 'front' and a clear, "
        "accurate answer on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "concept-example": (
        "Generate {count} Concept & Example flashcards based strictly on the lesson below. "
        "Each card should have a core concept or rule on the 'front' and a concrete, "
        "real-world example or application on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
    "fill-blank": (
        "Generate {count} Fill-in-the-Blank flashcards based strictly on the lesson below. "
        "Each card should have a statement with a crucial concept replaced by '______' on the 'front' "
        "and the correct term plus brief context on the 'back'. "
        "Return valid JSON only as an array of objects with keys: 'front' and 'back'. "
        "No markdown fences.\n\nTOPIC: {topic}\nLESSON:\n{context}"
    ),
}

def synthesize_flashcards_from_document(
    document_text: str,
    target_count: int,
    card_type: str,
    existing_cards: List[Dict[str, str]],
    document_name: Optional[str] = None
) -> List[Dict[str, str]]:
    """Synthesize up to target_count flashcards directly from the document content."""
    cards = list(existing_cards)
    seen = {c["front"].strip().lower() for c in cards if "front" in c}

    def add_card(front: str, back: str):
        f = front.strip()
        b = back.strip()
        if f and b and f.lower() not in seen and len(f) >= 3 and len(b) >= 5:
            seen.add(f.lower())
            cards.append({"front": f, "back": b})

    # Clean lines
    raw_lines = [l.strip() for l in document_text.split("\n") if l.strip()]
    lines = []
    for l in raw_lines:
        if l.startswith("[Page") or l.startswith("===") or l.startswith("---") or l.startswith("IT ELEC"):
            continue
        lines.append(l)

    # 1. Numbered concepts (e.g., "1. Usability", "2. Effectiveness") with explanations
    for i in range(len(lines) - 1):
        if len(cards) >= target_count:
            break
        l = lines[i]
        m = re.match(r"^(\d+[\.\)]\s*)([A-Z][A-Za-z0-9\s\(\)\/\-]+)$", l)
        if m:
            term = m.group(2).strip()
            exp_lines = []
            for j in range(i + 1, min(i + 8, len(lines))):
                if re.match(r"^\d+[\.\)]\s*[A-Z]", lines[j]):
                    break
                exp_lines.append(lines[j])
            exp_text = " ".join(exp_lines).strip()
            if exp_text:
                if card_type == "term-definition":
                    add_card(term, exp_text)
                elif card_type == "question-answer":
                    add_card(f"What is {term} and why is it important?", exp_text)
                elif card_type == "concept-example":
                    add_card(f"Concept: {term}", f"Description & Example:\n{exp_text}")
                elif card_type == "fill-blank":
                    snippet = exp_text[:110] + "…" if len(exp_text) > 110 else exp_text
                    add_card(f"In this lesson, ______ is described as: {snippet}", f"Answer: {term}\n\n{exp_text}")

    # 2. Key-Value pairs with colons (e.g. "Usability: The system should be easy to use")
    for l in lines:
        if len(cards) >= target_count:
            break
        if ":" in l and not l.startswith("http"):
            parts = l.split(":", 1)
            k, v = parts[0].strip(), parts[1].strip()
            k_clean = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", k).strip()
            if 1 <= len(k_clean.split()) <= 6 and len(v) > 10:
                if card_type == "term-definition":
                    add_card(k_clean, v)
                elif card_type == "question-answer":
                    add_card(f"What is {k_clean}?", v)
                elif card_type == "concept-example":
                    add_card(f"Topic: {k_clean}", f"Details:\n{v}")
                elif card_type == "fill-blank":
                    snippet = v[:120] + "…" if len(v) > 120 else v
                    add_card(f"______: {snippet}", f"Answer: {k_clean}")

    # 3. Sentences with definitions ("is a", "is defined as", "refers to", "focuses on")
    for l in lines:
        if len(cards) >= target_count:
            break
        cl = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", l).strip()
        for pat in [
            r"^([A-Z][A-Za-z0-9\s\(\)\/\-]{2,45}?)\s+is\s+(?:a|an|the|defined\s+as)\s+(.+)$",
            r"^([A-Z][A-Za-z0-9\s\(\)\/\-]{2,45}?)\s+(?:refers\s+to|focuses\s+on|aims\s+to|involves)\s+(.+)$"
        ]:
            m = re.match(pat, cl, re.IGNORECASE)
            if m:
                t, d = m.group(1).strip(), m.group(2).strip()
                if len(t.split()) <= 6 and len(d) > 15:
                    if card_type == "term-definition":
                        add_card(t, f"{t} is {d}")
                    elif card_type == "question-answer":
                        add_card(f"How does the material define {t}?", f"{t} is {d}")
                    elif card_type == "concept-example":
                        add_card(f"Key Concept: {t}", f"{t} is {d}")
                    elif card_type == "fill-blank":
                        snippet = d[:120] + "…" if len(d) > 120 else d
                        add_card(f"______ is {snippet}", f"Answer: {t}\n\nFull Statement: {t} is {d}")

    # 4. Questions in the text (e.g. "What is Human-Computer Interaction?")
    for i, l in enumerate(lines):
        if len(cards) >= target_count:
            break
        if l.endswith("?") and len(l) > 10:
            ans = " ".join(lines[i+1:min(i+5, len(lines))]).strip()
            if ans and not ans.endswith("?"):
                q_clean = re.sub(r"^\d+[\.\)]\s*", "", l).strip()
                if card_type == "question-answer":
                    add_card(q_clean, ans)
                elif card_type == "term-definition":
                    term_guess = re.sub(r"^(What is|Why is|How does|Explain)\s+", "", q_clean, flags=re.I).replace("?", "").strip()
                    add_card(term_guess, ans)
                elif card_type == "concept-example":
                    add_card(f"Question / Scenario: {q_clean}", ans)
                elif card_type == "fill-blank":
                    snippet = ans[:110] + "…" if len(ans) > 110 else ans
                    add_card(f"Regarding '{q_clean}': ______ states: {snippet}", f"Answer: {ans}")

    # 5. Core educational sentences and statements to fill up to target_count (up to 100)
    fact_lines = [l for l in lines if len(l) > 25 and not l.startswith("[") and not l.startswith("=") and not l.endswith("?")]
    
    variation_templates = [
        ("Review Point", "What does the text highlight regarding"),
        ("Key Principle", "Explain the concept of"),
        ("Core Takeaway", "Summarize the significance of"),
        ("Design Concept", "How should we understand"),
        ("Study Check", "According to the lesson, what is true about")
    ]

    counter = 0
    while len(cards) < target_count and fact_lines:
        fl = fact_lines[counter % len(fact_lines)]
        cl = re.sub(r"^[✔❌\-\*\•\d+\.\)]\s*", "", fl).strip()
        words = cl.split()
        if len(words) >= 6:
            lead4 = " ".join(words[:4])
            lead2 = " ".join(words[:2])
            card_num = len(cards) + 1
            v_label, v_query = variation_templates[counter % len(variation_templates)]

            if card_type == "term-definition":
                split_idx = min(4, max(1, len(words) // 4))
                head = " ".join(words[:split_idx])
                add_card(f"{v_label} {card_num}: {head}…", cl)
            elif card_type == "question-answer":
                add_card(f"Item {card_num}: {v_query} '{lead4}…'?", cl)
            elif card_type == "concept-example":
                add_card(f"Concept Application {card_num}: {lead4}…", f"Lesson Details:\n{cl}")
            elif card_type == "fill-blank":
                blanked = "______ " + " ".join(words[2:])
                add_card(f"Card {card_num}: {blanked}", f"Answer: {lead2}\n\nFull Statement:\n{cl}")
        counter += 1
        if counter > len(fact_lines) * 5:
            break

    return cards[:target_count]


@router.post("/learning/flashcards")
def create_flashcards(
    request: FlashcardRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user)
):
    """Generate AI-powered flashcards from an uploaded lesson document."""
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_name)
    card_count = max(1, min(100, request.card_count or 10))
    card_type = request.card_type or "term-definition"

    context, sources = get_lesson_context(uid, request.topic, target_filename=document_name)

    # Load all raw chunks of target document for comprehensive synthesis
    all_chunks = get_all_document_chunks(document_name, uid)
    full_doc_text = "\n\n".join(c.get("text", "") for c in all_chunks) if all_chunks else context

    # Choose prompt template by card type (default to term-definition)
    prompt_template = FLASHCARD_TYPE_PROMPTS.get(card_type, FLASHCARD_TYPE_PROMPTS["term-definition"])

    # LLM request: batch up to min(25, card_count)
    batch_size = min(25, card_count)
    parsed_cards: List[Dict[str, str]] = []

    prompt = prompt_template.format(
        count=batch_size,
        topic=request.topic,
        context=context[:8000]
    )

    try:
        raw = generate(
            prompt,
            system=(
                "You are KeepAI, a helpful study assistant. Generate clear, accurate flashcards "
                "grounded strictly in the provided lesson material. Use simple, student-friendly language. "
                "Return only a valid JSON array — no markdown, no extra text."
            )
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and "front" in item and "back" in item:
                    parsed_cards.append({
                        "front": str(item["front"]).strip(),
                        "back": str(item["back"]).strip()
                    })
    except Exception as e:
        print(f"Flashcard LLM generation notice: {e}")

    # Synthesize additional cards directly from the document text to reach card_count (up to 100)
    final_cards = synthesize_flashcards_from_document(
        document_text=full_doc_text,
        target_count=card_count,
        card_type=card_type,
        existing_cards=parsed_cards,
        document_name=document_name or (sources[0] if sources else None)
    )

    # Track usage stats
    user_service.increment_stat(current_user["id"], "flashcards_studied", len(final_cards))

    return {
        "topic": request.topic,
        "document_name": document_name or (sources[0] if sources else "Uploaded Document"),
        "card_type": card_type,
        "total_cards": len(final_cards),
        "cards": final_cards,
        "sources": sources
    }
