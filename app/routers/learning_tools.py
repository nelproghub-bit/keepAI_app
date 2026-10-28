import json
import re
import random
import hashlib
import unicodedata
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, model_validator
from app.core.ai_guardrails import PromptGuardrail
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
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
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
    topic: str = Field(default="", max_length=500)
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
    # Quiz requests use only the selected document and all of its stored content.
    if target_filename:
        chunks = get_all_document_chunks(target_filename, user_id)
        if chunks:
            combined_text = "\n\n".join(c.get("text", "") for c in chunks)
            return combined_text, [target_filename]
        metadata = _load_user_files_meta(user_id).get(target_filename) or {}
        full_text = metadata.get("full_text", "")
        if full_text.strip():
            return full_text, [target_filename]
        raise HTTPException(404, "No readable content was found in the selected document.")

    ctx = get_tutor_context(user_id, topic, target_filename=target_filename)
    if ctx and ctx.get("has_materials"):
        return ctx["context"], ctx["sources"]

    if not ctx or not ctx.get("has_materials"):
        raise HTTPException(404, "No lesson content found. Please upload a PDF or document in the Library first.")
    return ctx["context"], ctx["sources"]

def generate_grounded_quiz_questions(
    context: str,
    target_count: int,
    difficulty: str = "medium",
) -> List[Dict[str, Any]]:
    """Generate quiz questions only when their answer is supported by source evidence."""
    if not context.strip():
        raise HTTPException(404, "No readable content was found in the selected document.")

    def normalize(value: str) -> str:
        normalized_value = unicodedata.normalize("NFKC", value).casefold()
        normalized_value = re.sub(r"[\u2010-\u2015-]", " ", normalized_value)
        return " ".join(re.findall(r"\w+", normalized_value))

    def split_source(text: str, max_chars: int = 10000) -> List[str]:
        parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
        chunks: List[str] = []
        current = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(current) + len(part) + 1 > max_chars and current:
                chunks.append(current)
                current = ""
            if len(part) > max_chars:
                for start in range(0, len(part), max_chars):
                    segment = part[start:start + max_chars]
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.append(segment)
            else:
                current = f"{current}\n{part}".strip()
        if current:
            chunks.append(current)
        return chunks or [text]

    difficulty_guidance = {
        "easy": (
            "Ask straightforward recall questions about basic concepts, definitions, terminology, "
            "and information directly stated in the lesson."
        ),
        "medium": (
            "Ask moderately challenging comprehension questions that test understanding and connect "
            "related concepts that are explicitly discussed in the lesson."
        ),
        "hard": (
            "Ask challenging critical-thinking, analysis, or application questions that require deeper "
            "understanding. Any conclusion required to answer must be fully inferable from the lesson."
        ),
    }[difficulty]

    questions: List[Dict[str, Any]] = []
    chunks = split_source(context)
    normalized_context = normalize(context)
    seen_questions = set()
    max_rounds = (target_count + 4) // 5 + 2
    no_progress_rounds = 0
    try:
        for round_index in range(max_rounds):
            round_question_count = len(questions)
            for index, source_chunk in enumerate(chunks):
                remaining = target_count - len(questions)
                if not remaining:
                    break
                normalized_chunk = normalize(source_chunk)
                proportional_target = max(
                    1,
                    (target_count * len(source_chunk) + len(context) - 1)
                    // max(len(context), 1),
                )
                chunk_target = min(5, proportional_target, remaining)
                exclusions = ""
                if seen_questions:
                    exclusions = (
                        "Do not repeat or closely paraphrase these already accepted questions: "
                        + PromptGuardrail.contain_untrusted_input(
                            json.dumps(sorted(seen_questions)[-30:], ensure_ascii=False),
                            "student_query",
                        )
                        + "\n"
                    )
                retry_guidance = ""
                if round_index:
                    retry_guidance = (
                        "Your previous response did not pass source validation. Return only complete "
                        "questions whose answer appears in an exact evidence excerpt from this section. "
                        "Keep evidence at or below 1000 characters, and include four distinct choices "
                        "that each appear in the selected document. Do not return an explanation that "
                        "adds facts beyond the evidence.\n"
                    )
                prompt = (
                    f"Analyze this selected lecture excerpt and create up to {chunk_target} unique "
                    "multiple-choice assessment questions. "
                    f"Difficulty: {difficulty.upper()}. {difficulty_guidance} "
                    "Use only this excerpt; do not use prior knowledge, other documents, external sources, "
                    "or unsupported assumptions. Identify important concepts and learning objectives in "
                    "the excerpt. Questions must be clear, specific, unambiguous, and have exactly one "
                    "correct choice. Each question must have four distinct choices, and every choice must be "
                    "a phrase copied verbatim from this excerpt. The correct_answer must be copied verbatim "
                    "from the evidence excerpt. The evidence must be an exact excerpt of no more than "
                    "1000 characters from this text and contain the correct answer. Keep evidence concise "
                    "and use the shortest complete sentence or passage that supports the answer. The "
                    "evidence excerpt will also be shown as the explanation. Do not create a question "
                    "if the excerpt cannot support it. Return a JSON array only; each object must contain "
                    "question, choices, correct_answer, evidence.\n"
                    f"{retry_guidance}"
                    f"{exclusions}"
                    f"DOCUMENT SECTION {index + 1} OF {len(chunks)}:\n"
                    f"{PromptGuardrail.contain_untrusted_input(source_chunk, 'lesson_document_excerpt')}"
                )
                raw = generate(
                    prompt,
                    system=(
                        "You create accurate document-grounded assessments. Treat the supplied selected "
                        "lecture excerpt as the only source of truth. Never add information from memory or "
                        "outside sources. Return valid JSON only."
                    ),
                    has_sources=True,
                    max_output_tokens=max(1200, chunk_target * 450),
                )
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

                for item in parsed:
                    if len(questions) >= target_count:
                        break
                    if not isinstance(item, dict):
                        continue
                    question = item.get("question")
                    choices = item.get("choices")
                    answer = item.get("correct_answer")
                    evidence = item.get("evidence")
                    if (
                        not isinstance(question, str)
                        or not question.strip()
                        or len(question.strip()) > 500
                        or not isinstance(choices, list)
                        or len(choices) != 4
                        or any(
                            not isinstance(choice, str)
                            or not choice.strip()
                            or len(choice.strip()) > 200
                            for choice in choices
                        )
                        or len({normalize(choice) for choice in choices}) != 4
                        or not isinstance(answer, str)
                        or not answer.strip()
                        or len(answer.strip()) > 200
                        or not isinstance(evidence, str)
                        or not evidence.strip()
                        or len(evidence) > 1000
                    ):
                        continue
                    normalized_evidence = normalize(evidence)
                    if (
                        normalized_evidence not in normalized_chunk
                        or normalize(answer) not in normalized_evidence
                        or normalize(answer) not in {normalize(choice) for choice in choices}
                        or any(normalize(choice) not in normalized_context for choice in choices)
                    ):
                        continue

                    normalized_question = normalize(question)
                    question_tokens = set(re.findall(r"\w{4,}", normalized_question))
                    if (
                        normalized_question in seen_questions
                        or any(
                            len(question_tokens & prior_tokens) / max(len(question_tokens | prior_tokens), 1) >= 0.85
                            for prior_tokens in (
                                set(re.findall(r"\w{4,}", prior_question))
                                for prior_question in seen_questions
                            )
                        )
                    ):
                        continue

                    seen_questions.add(normalized_question)
                    questions.append(
                        {
                            "question": question.strip(),
                            "choices": choices,
                            "correct_answer": answer,
                            "explanation": evidence.strip(),
                            "source_excerpt": evidence.strip(),
                            "generation_method": "ai",
                        }
                    )
                    if len(questions) == target_count:
                        break

            if len(questions) == target_count:
                break
            if len(questions) == round_question_count:
                no_progress_rounds += 1
                if no_progress_rounds >= 2:
                    break
            else:
                no_progress_rounds = 0
    except AIProviderError as exc:
        raise HTTPException(
            502,
            f"Quiz generation could not reach the AI provider: {exc}",
        ) from exc

    if len(questions) != target_count:
        raise HTTPException(
            502,
            "The selected document does not contain enough accurate, unique questions at this difficulty level. Try fewer questions or choose another difficulty.",
        )
    return questions


def build_typed_quiz_questions(
    source_questions: List[Dict[str, Any]],
    question_counts: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Format grounded source items without reusing facts across requested questions."""
    result: List[Dict[str, Any]] = []
    source_index = 0
    supported_types = {
        "identification",
        "multiple_choice",
        "true_false",
        "fill_blank",
        "matching",
    }
    if any(
        question_type not in supported_types
        or not isinstance(count, int)
        or count < 0
        for question_type, count in question_counts.items()
    ):
        raise HTTPException(422, "One or more quiz format counts are invalid.")
    expected_source_count = sum(
        count * (3 if question_type == "matching" else 1)
        for question_type, count in question_counts.items()
    )
    if expected_source_count > len(source_questions):
        raise HTTPException(
            502,
            "The selected document did not provide enough unique source questions for the requested formats. Try fewer questions.",
        )

    def normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    for question_type, count in question_counts.items():
        if question_type == "matching":
            for _ in range(count):
                pair_sources = source_questions[source_index:source_index + 3]
                source_index += 3
                pairs = [
                    {"left": item["question"], "right": item["correct_answer"]}
                    for item in pair_sources
                ]
                if (
                    len(pairs) != 3
                    or len({normalized(pair["left"]) for pair in pairs}) != 3
                    or len({normalized(pair["right"]) for pair in pairs}) != 3
                ):
                    raise HTTPException(
                        502,
                        "The generated matching activity contains repeated or incomplete pairs. Please try again.",
                    )
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
            source = source_questions[source_index]
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
                        "_source_answer": correct_answer,
                        "explanation": (
                            explanation if is_true
                            else f"The correct answer is: {correct_answer}. {explanation}"
                        ),
                        "source_excerpt": source.get("source_excerpt", ""),
                    }
                )
            elif question_type == "fill_blank":
                evidence = source.get("source_excerpt", "")
                answer_matches = list(re.finditer(
                    re.escape(correct_answer),
                    evidence,
                    flags=re.IGNORECASE,
                ))
                if len(answer_matches) != 1:
                    raise HTTPException(
                        502,
                        "The generated fill-in-the-blank item could not be tied to one clear answer in the source. Please try again.",
                    )
                match = answer_matches[0]
                blanked_statement = (
                    evidence[:match.start()] + "____" + evidence[match.end():]
                )
                result.append(
                    {
                        "question_type": question_type,
                        "question": f"Complete the statement from the lesson: {blanked_statement}",
                        "correct_answer": correct_answer,
                        "accepted_answers": [correct_answer],
                        "explanation": explanation,
                        "source_excerpt": evidence,
                    }
                )

    actual_counts: Dict[str, int] = {}
    seen_items = set()
    for item in result:
        item_type = item.get("question_type")
        actual_counts[item_type] = actual_counts.get(item_type, 0) + 1

        if item_type == "matching":
            pairs = item.get("pairs", [])
            choices = item.get("choices", [])
            evidence = normalized(item.get("source_excerpt", ""))
            item_key = (
                item_type,
                tuple(sorted(
                    (normalized(pair["left"]), normalized(pair["right"]))
                    for pair in pairs
                )),
            )
            if (
                len(pairs) != 3
                or len(choices) != 3
                or {normalized(choice) for choice in choices}
                != {normalized(pair["right"]) for pair in pairs}
                or any(
                    normalized(pair["right"]) not in evidence
                    for pair in pairs
                )
            ):
                raise HTTPException(
                    502,
                    "The generated matching activity failed format validation. Please try again.",
                )
        else:
            question = item.get("question")
            answer = item.get("correct_answer")
            evidence = item.get("source_excerpt")
            evidence_answer = item.get("_source_answer", answer)
            if not all(
                isinstance(value, str) and value.strip()
                for value in (question, answer, evidence, evidence_answer)
            ):
                raise HTTPException(
                    502,
                    "A generated quiz item is missing its question, answer, or source evidence. Please try again.",
                )
            item_key = (item_type, normalized(question))
            if normalized(evidence_answer) not in normalized(evidence):
                raise HTTPException(
                    502,
                    "A generated quiz answer could not be verified against its source evidence. Please try again.",
                )
            if item_type in {"multiple_choice", "true_false"}:
                choices = item.get("choices", [])
                expected_choice_count = 4 if item_type == "multiple_choice" else 2
                if (
                    not isinstance(choices, list)
                    or len(choices) != expected_choice_count
                    or len({normalized(choice) for choice in choices}) != len(choices)
                    or normalized(answer) not in {normalized(choice) for choice in choices}
                ):
                    raise HTTPException(
                        502,
                        "A generated quiz item does not meet its selected answer format. Please try again.",
                    )
            elif item_type == "fill_blank" and "____" not in question:
                raise HTTPException(
                    502,
                    "A generated fill-in-the-blank item is missing its blank. Please try again.",
                )

        if item_key in seen_items:
            raise HTTPException(
                502,
                "The generated quiz contains duplicate questions or matching pairs. Please try again.",
            )
        seen_items.add(item_key)
        item.pop("_source_answer", None)

    expected_counts = {
        question_type: count
        for question_type, count in question_counts.items()
        if count > 0
    }
    if actual_counts != expected_counts:
        raise HTTPException(
            502,
            "Quiz generation did not produce the exact number of questions requested for each format. Please try again.",
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
        "Summarize the following lesson about "
        f"{PromptGuardrail.contain_untrusted_input(request.topic, 'student_query')} "
        "using simple, clear, and easy-to-understand words. "
        "Use short headings, bullet points, and plain definitions so any student can understand quickly. Do not add "
        "unsupported facts.\n\nLESSON:\n"
        f"{PromptGuardrail.contain_untrusted_input(context, 'lesson_document_excerpt')}",
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
    if not request.document_name:
        raise HTTPException(400, "Select a source document before generating a quiz.")
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
        difficulty=request.difficulty,
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
        "difficulty": request.difficulty,
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
    focus_topic: str = "",
) -> List[Dict[str, Any]]:
    """Extract only explicit source definitions or examples; never pad with generic prompts."""
    cards = list(existing_cards or [])
    seen_fronts = {_normalize_flashcard_text(card.get("front", "")) for card in cards}
    seen_evidence = {_normalize_flashcard_text(card.get("source_excerpt", "")) for card in cards}
    seen_answers = {_normalize_flashcard_text(card.get("back", "")) for card in cards}
    focus_terms = {
        token for token in re.findall(r"\w+", _normalize_flashcard_text(focus_topic))
        if len(token) > 2
    }
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
            evidence_terms = set(re.findall(r"\w+", normalized_evidence))
            if focus_terms and not focus_terms.intersection(evidence_terms):
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
                    front, back = term, evidence[example_match.start():].strip()
                else:
                    continue
            elif card_type == "concept-example" and example_match:
                subject = evidence[:example_match.start()].strip(" ,:.-")
                if not subject:
                    continue
                front = subject
                back = evidence[example_match.start():].strip()
            else:
                continue

            normalized_front = _normalize_flashcard_text(front)
            normalized_back = _normalize_flashcard_text(back)
            if (
                len(front) > 180
                or len(back) > 450
                or normalized_front in seen_fronts
                or normalized_back in seen_answers
                or normalized_back not in normalized_evidence
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
            seen_fronts.add(normalized_front)
            seen_evidence.add(normalized_evidence)
            seen_answers.add(normalized_back)
    return cards


def _is_valid_flashcard_candidate(
    front: str,
    back: str,
    evidence: str,
    section: str,
    card_type: str,
    focus_topic: str,
) -> bool:
    normalized_front = _normalize_flashcard_text(front)
    normalized_back = _normalize_flashcard_text(back)
    normalized_evidence = _normalize_flashcard_text(evidence)
    normalized_section = _normalize_flashcard_text(section)
    if (
        not normalized_front
        or not normalized_back
        or len(front) > 180
        or len(back) > 450
        or len(evidence) > 500
        or normalized_evidence not in normalized_section
        or normalized_back not in normalized_evidence
    ):
        return False

    evidence_terms = set(re.findall(r"\w+", normalized_evidence))
    front_terms = {
        token for token in re.findall(r"\w+", normalized_front)
        if len(token) > 2
        and token not in {
            "what", "does", "the", "this", "that", "with", "from",
            "according", "example", "illustrated",
        }
    }
    if not front_terms.intersection(evidence_terms):
        return False

    if focus_topic:
        focus_terms = {
            token for token in re.findall(r"\w+", _normalize_flashcard_text(focus_topic))
            if len(token) > 2
        }
        if focus_terms and not focus_terms.intersection(evidence_terms):
            return False

    if card_type == "term-definition":
        return normalized_front in normalized_evidence and not normalized_front.endswith("?")
    if card_type == "question-answer":
        return (
            front.rstrip().endswith("?")
            and re.match(
                r"^(?:who|what|when|where|why|which|how|define|explain|describe|identify|name|list)\b",
                front.strip(),
                re.IGNORECASE,
            ) is not None
        )
    if card_type == "concept-example":
        example_match = re.search(
            r"\b(?:for example|for instance|such as|example:|e\.g\.?)\b",
            normalized_evidence,
            re.IGNORECASE,
        )
        return (
            normalized_front in normalized_evidence
            and example_match is not None
            and normalized_evidence.find(normalized_back) >= example_match.start()
        )
    if card_type == "fill-blank":
        return (
            front.count("______") == 1
            and normalized_back in normalized_evidence
            and normalized_front.replace("______", normalized_back, 1) == normalized_evidence
        )
    return False


def generate_flashcards_from_document(
    document_text: str,
    topic: str,
    card_count: int,
    card_type: str,
) -> List[Dict[str, Any]]:
    """Create concise cards whose answers are directly verifiable in source excerpts."""
    if not document_text.strip():
        raise HTTPException(404, "No readable text was found in the selected document.")
    if card_type not in FLASHCARD_TYPES:
        raise HTTPException(422, "Choose a supported flashcard type.")
    if not 1 <= card_count <= 100:
        raise HTTPException(422, "Choose between 1 and 100 flashcards.")

    focus_topic = topic.strip()
    type_instructions = {
        "term-definition": "Put one exact key term on front and its concise source-stated definition on back.",
        "question-answer": "Put one clear, grammatical question ending in ? on front and its concise source-stated answer on back.",
        "concept-example": "Put the exact concept on front and an explicitly stated example on back. The evidence must contain an example marker such as 'for example', 'for instance', or 'such as'.",
        "fill-blank": "Put one exact source sentence on front with exactly one key term replaced by ______, and that exact missing text on back.",
    }
    cards: List[Dict[str, Any]] = []
    seen_fronts = set()
    seen_evidence = set()
    seen_answers = set()
    generation_failed = False

    for section in _flashcard_source_sections(document_text):
        if len(cards) >= card_count:
            break
        batch_count = min(5, card_count - len(cards))
        focus_instruction = (
            f"Prioritize content relevant to this focus topic: "
            f"{PromptGuardrail.contain_untrusted_input(focus_topic, 'student_query')}. "
            if focus_topic
            else "Cover the full selected lesson. "
        )
        prompt = (
            f"Create up to {batch_count} distinct, high-value flashcards for {focus_topic or 'the selected lesson'}. "
            "Use only the supplied excerpt. Prioritize essential concepts, key terms, explicit definitions, "
            "important processes, and memorable examples. Exclude trivial, repetitive, or low-value details. "
            "Preserve the order topics appear in the lecture. "
            f"{focus_instruction}"
            f"Format: {type_instructions[card_type]} Each card must contain one idea only. "
            "Keep front under 180 characters and back to one or two short sentences, under 450 characters. "
            "Return JSON array objects with front, back, source_excerpt. source_excerpt must be copied "
            "verbatim from the supplied excerpt, and back must be an exact continuous quote contained "
            "in source_excerpt. Do not invent, infer, add examples, combine concepts, or return duplicates. "
            "Skip unsupported concepts rather than guessing. Return [] if the excerpt has no suitable content.\n"
            "LECTURE EXCERPT:\n"
            f"{PromptGuardrail.contain_untrusted_input(section, 'lesson_document_excerpt')}"
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
            if (
                not _is_valid_flashcard_candidate(
                    front.strip(),
                    back.strip(),
                    evidence.strip(),
                    section,
                    card_type,
                    focus_topic,
                )
                or normalized_front in seen_fronts
                or normalized_evidence in seen_evidence
                or normalized_back in seen_answers
            ):
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
            seen_answers.add(normalized_back)
            if len(cards) == card_count:
                break

    if generation_failed or len(cards) < card_count:
        cards = build_extractive_flashcards(
            document_text,
            card_type,
            existing_cards=cards,
            focus_topic=focus_topic,
        )

    if not cards:
        raise HTTPException(
            422,
            "This document does not contain enough clear, verifiable material for the selected flashcard type. Try another card type or a more specific lecture document.",
        )

    if len(cards) < card_count:
        raise HTTPException(
            422,
            f"Only {len(cards)} distinct, source-verified cards are available for this type and focus. "
            f"Reduce the requested count from {card_count}, choose another type, or select a document with more relevant material.",
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

    generation_methods = {card.get("generation_method") for card in cards}
    if generation_methods == {"document_extract"}:
        generation_mode = "document_extract"
    elif len(generation_methods) > 1:
        generation_mode = "mixed"
    else:
        generation_mode = "ai"

    return {
        "topic": request.topic,
        "document_name": document_name or (sources[0] if sources else "Uploaded Document"),
        "card_type": card_type,
        "total_cards": len(cards),
        "generation_mode": generation_mode,
        "cards": cards,
        "sources": sources,
    }
