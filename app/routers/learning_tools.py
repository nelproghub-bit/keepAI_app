import json
import re
import random
import hashlib
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query
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
    card_type: str = Field(
        default="term-definition",
        pattern="^(term-definition|question-answer|concept-example|fill-blank)$",
    )


class FlashcardProgressRequest(BaseModel):
    document_name: str = Field(min_length=1, max_length=255)
    front: str = Field(min_length=1, max_length=1000)
    mastered: bool

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

FLASHCARD_TYPES = {
    "term-definition",
    "question-answer",
    "concept-example",
    "fill-blank",
}


def _normalize_flashcard_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _flashcard_key(value: str) -> str:
    return hashlib.sha256(_normalize_flashcard_text(value).encode("utf-8")).hexdigest()


def _flashcard_document_key(document_name: str) -> str:
    return hashlib.sha256(document_name.strip().casefold().encode("utf-8")).hexdigest()


def _flashcard_source_sections(document_text: str, max_chars: int = 9000) -> List[str]:
    sections: List[str] = []
    start = 0
    while start < len(document_text):
        end = min(start + max_chars, len(document_text))
        if end < len(document_text):
            boundary = max(
                document_text.rfind("\n", start, end),
                document_text.rfind(". ", start, end),
                document_text.rfind("? ", start, end),
            )
            if boundary > start + max_chars // 2:
                end = boundary + 1
        section = document_text[start:end].strip()
        if section:
            sections.append(section)
        if end >= len(document_text):
            break
        start = max(end - 250, start + 1)
    return sections


def _flashcard_page(source_excerpt: str) -> Optional[int]:
    match = re.search(r"\[Page\s*(\d+)\]", source_excerpt, re.IGNORECASE)
    return int(match.group(1)) if match else None


def build_extractive_flashcards(
    document_text: str,
    card_type: str,
    existing_cards: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Extract only explicit source definitions or examples; never pad with generic prompts."""
    cards = list(existing_cards or [])
    seen_fronts = {_normalize_flashcard_text(card.get("front", "")) for card in cards}
    seen_evidence = {_normalize_flashcard_text(card.get("source_excerpt", "")) for card in cards}
    statement_pattern = re.compile(
        r"^(?P<term>[A-Z][A-Za-z0-9() /&+_-]{1,75}?)\s+"
        r"(?P<link>is defined as|refers to|means|is|are|represents|consists of|includes)\s+"
        r"(?P<answer>[^.!?;]{12,350}[.!?]?)$",
        re.IGNORECASE,
    )
    example_pattern = re.compile(r"\b(for example|for instance|such as|example:)\b", re.IGNORECASE)

    for section in _flashcard_source_sections(document_text):
        page = _flashcard_page(section)
        clean_section = re.sub(r"\[Page\s*\d+\]", "", section, flags=re.IGNORECASE)
        statements = re.split(r"(?<=[.!?])\s+|(?<=;)\s+|\n+", clean_section)
        for raw_statement in statements:
            evidence = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", raw_statement).strip()
            if not 30 <= len(evidence) <= 500:
                continue
            normalized_evidence = _normalize_flashcard_text(evidence)
            if normalized_evidence in seen_evidence:
                continue
            match = statement_pattern.match(evidence)
            label_match = re.match(
                r"^(?P<term>[A-Z][^:]{1,75}):\s*(?P<answer>[^.!?;]{12,350}[.!?]?)$",
                evidence,
            )
            definition = match or label_match
            example_match = example_pattern.search(evidence)
            term = ""
            if definition:
                term = definition.group("term").strip(" -")
                answer = definition.group("answer").strip()
                if card_type == "term-definition":
                    front, back = term, answer
                elif card_type == "question-answer":
                    front, back = f"What does the lesson say about {term}?", answer
                elif card_type == "fill-blank":
                    front = re.sub(re.escape(term), "______", evidence, count=1, flags=re.IGNORECASE)
                    back = term
                elif card_type == "concept-example" and example_match:
                    front, back = f"What example is given for {term}?", evidence[example_match.start():].strip()
                else:
                    continue
            elif card_type == "concept-example" and example_match:
                subject = " ".join(evidence[:example_match.start()].split()[-4:]).strip(" :,-")
                if not subject:
                    continue
                front = f"What example is given for {subject}?"
                back = evidence[example_match.start():].strip()
            else:
                continue

            if (
                len(front) > 180
                or len(back) > 450
                or _normalize_flashcard_text(front) in seen_fronts
                or _normalize_flashcard_text(back) not in normalized_evidence
            ):
                continue
            cards.append(
                {
                    "front": front,
                    "back": back,
                    "source_excerpt": evidence,
                    "source_page": page,
                    "topic": term or "Example",
                    "generation_method": "document_extract",
                }
            )
            seen_fronts.add(_normalize_flashcard_text(front))
            seen_evidence.add(normalized_evidence)
    return cards


def generate_flashcards_from_document(
    document_text: str,
    topic: str,
    card_count: int,
    card_type: str,
) -> List[Dict[str, Any]]:
    """Create concise cards whose answers are directly verifiable in source excerpts."""
    if not document_text.strip():
        raise HTTPException(404, "No readable text was found in the selected document.")

    type_instructions = {
        "term-definition": "Put one exact key term on front and its concise source-stated definition on back.",
        "question-answer": "Put one focused question on front and its concise source-stated answer on back.",
        "concept-example": "Use a concept and an example only when that example is explicitly present in the excerpt.",
        "fill-blank": "Put one source sentence with exactly one key term replaced by ______ on front and that exact term on back.",
    }
    cards: List[Dict[str, Any]] = []
    seen_fronts = set()
    seen_evidence = set()
    generation_failed = False

    for section in _flashcard_source_sections(document_text):
        if len(cards) >= card_count:
            break
        batch_count = min(5, card_count - len(cards))
        prompt = (
            f"Create up to {batch_count} distinct flashcards for focus topic: {topic}. "
            "Use only the supplied excerpt. Preserve the order topics appear in the lecture. "
            f"Format: {type_instructions[card_type]} Each card must contain one idea only. "
            "Keep front under 180 characters and back to one or two short sentences, under 450 characters. "
            "Return JSON array objects with front, back, source_excerpt. source_excerpt must be copied "
            "verbatim from the supplied excerpt, and back must be an exact continuous quote contained "
            "in source_excerpt. Do not invent, infer, add examples, combine concepts, or return duplicates. "
            "Skip unsupported concepts rather than guessing. Return [] if the excerpt has no suitable content.\n"
            f"FOCUS TOPIC: {topic}\nLECTURE EXCERPT:\n{section}"
        )
        try:
            raw = generate(
                prompt,
                system=(
                    "You are a source-grounded study-card generator. The lecture excerpt is the only source "
                    "of truth. Return concise, single-concept cards with answers copied verbatim from their "
                    "cited evidence. Return valid JSON only."
                ),
                has_sources=True,
            )
        except AIProviderError:
            generation_failed = True
            break

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

        normalized_section = _normalize_flashcard_text(section)
        for item in parsed:
            if not isinstance(item, dict):
                continue
            front = item.get("front")
            back = item.get("back")
            evidence = item.get("source_excerpt")
            if (
                not all(isinstance(value, str) and value.strip() for value in (front, back, evidence))
                or len(front.strip()) > 180
                or len(back.strip()) > 450
                or len(evidence.strip()) > 500
            ):
                continue
            normalized_evidence = _normalize_flashcard_text(evidence)
            normalized_back = _normalize_flashcard_text(back)
            normalized_front = _normalize_flashcard_text(front)
            evidence_terms = {
                token for token in re.findall(r"\w+", normalized_evidence)
                if len(token) > 3
            }
            front_terms = {
                token for token in re.findall(r"\w+", normalized_front)
                if len(token) > 3 and token not in {"what", "does", "this", "that", "with", "from", "according"}
            }
            if (
                normalized_evidence not in normalized_section
                or normalized_back not in normalized_evidence
                or normalized_front in seen_fronts
                or normalized_evidence in seen_evidence
                or not normalized_back
                or not front_terms.intersection(evidence_terms)
            ):
                continue
            if card_type == "fill-blank" and "______" not in front:
                continue
            cards.append(
                {
                    "front": front.strip(),
                    "back": back.strip(),
                    "source_excerpt": evidence.strip(),
                    "source_page": _flashcard_page(evidence) or _flashcard_page(section),
                    "topic": topic,
                    "generation_method": "ai",
                }
            )
            seen_fronts.add(normalized_front)
            seen_evidence.add(normalized_evidence)
            if len(cards) == card_count:
                break

    if generation_failed or len(cards) < card_count:
        cards = build_extractive_flashcards(
            document_text,
            card_type,
            existing_cards=cards,
        )

    if not cards:
        raise HTTPException(
            422,
            "This document does not contain enough clear, verifiable material for the selected flashcard type. Try another card type or a more specific lecture document.",
        )

    cards = cards[:card_count]
    normalized_document = _normalize_flashcard_text(document_text)

    def source_position(card: Dict[str, Any]) -> int:
        position = normalized_document.find(
            _normalize_flashcard_text(card["source_excerpt"])
        )
        return position if position >= 0 else len(normalized_document)

    cards.sort(key=source_position)
    for card in cards:
        card["card_key"] = _flashcard_key(card["front"])
    return cards


def _get_flashcard_progress(user_id: str, document_name: str) -> List[str]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT card_key FROM flashcard_progress WHERE user_id = ? AND document_key = ? AND mastered = ?",
            (user_id, _flashcard_document_key(document_name), True),
        )
        return [row["card_key"] for row in cursor.fetchall()]
    finally:
        conn.close()


def _save_flashcard_progress(
    user_id: str,
    document_name: str,
    front: str,
    mastered: bool,
) -> str:
    document_key = _flashcard_document_key(document_name)
    card_key = _flashcard_key(front)
    progress_id = hashlib.sha256(f"{user_id}:{document_key}:{card_key}".encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM flashcard_progress WHERE id = ?",
            (progress_id,),
        )
        if cursor.fetchone():
            cursor.execute(
                "UPDATE flashcard_progress SET card_front = ?, mastered = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (front.strip(), mastered, progress_id, user_id),
            )
        else:
            cursor.execute(
                "INSERT INTO flashcard_progress (id, user_id, document_key, card_key, card_front, mastered) VALUES (?, ?, ?, ?, ?, ?)",
                (progress_id, user_id, document_key, card_key, front.strip(), mastered),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return card_key


@router.get("/learning/flashcards/progress")
def read_flashcard_progress(
    document_name: str = Query(min_length=1, max_length=255),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
):
    owned_name = get_owned_document_name(current_user["id"], document_name)
    return {"mastered_card_keys": _get_flashcard_progress(current_user["id"], owned_name)}


@router.put("/learning/flashcards/progress")
def update_flashcard_progress(
    request: FlashcardProgressRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
):
    owned_name = get_owned_document_name(current_user["id"], request.document_name)
    card_key = _save_flashcard_progress(
        current_user["id"],
        owned_name,
        request.front,
        request.mastered,
    )
    return {"card_key": card_key, "mastered": request.mastered}


@router.post("/learning/flashcards")
def create_flashcards(
    request: FlashcardRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
):
    """Generate verified flashcards from the student's selected source document."""
    uid = current_user["id"]
    document_name = get_owned_document_name(uid, request.document_name)
    card_count = request.card_count or 10
    card_type = request.card_type
    context, sources = get_lesson_context(uid, request.topic, target_filename=document_name)

    chunks = sorted(
        get_all_document_chunks(document_name, uid),
        key=lambda chunk: chunk.get("chunk_index", 0),
    )
    files_meta = _load_user_files_meta(uid)
    document_metadata = files_meta.get(document_name, {})
    full_doc_text = document_metadata.get("full_text") or "\n\n".join(
        chunk.get("text", "") for chunk in chunks if chunk.get("text")
    ) or context
    cards = generate_flashcards_from_document(
        full_doc_text,
        request.topic,
        card_count,
        card_type,
    )
    user_service.increment_stat(uid, "flashcards_studied", len(cards))

    return {
        "topic": request.topic,
        "document_name": document_name or (sources[0] if sources else "Uploaded Document"),
        "card_type": card_type,
        "total_cards": len(cards),
        "generation_mode": (
            "document_extract"
            if any(card.get("generation_method") == "document_extract" for card in cards)
            else "ai"
        ),
        "cards": cards,
        "sources": sources,
    }
