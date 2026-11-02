import json
import logging
import random
import re
import unicodedata
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, model_validator
from app.core.ai_guardrails import PromptGuardrail
from app.core.security import get_current_student_user
from app.core.database import get_connection
from app.services.user_service import user_service
from app.services.progress_service import record_activity
from app.services.rag_service import get_tutor_context, _load_user_documents, _load_user_files_meta
from app.services.gemini_service import AIProviderError, generate

router = APIRouter(tags=["Learning Tools"])
logger = logging.getLogger(__name__)

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
        metadata = _load_user_files_meta(user_id, target_filename).get(target_filename) or {}
        full_text = metadata.get("full_text", "")
        if isinstance(full_text, str) and full_text.strip():
            return full_text, [target_filename]
        chunks = get_all_document_chunks(target_filename, user_id)
        if chunks:
            combined_text = "\n\n".join(c.get("text", "") for c in chunks)
            return combined_text, [target_filename]
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
        normalized_value = re.sub(
            r"(?<=\w)[\u00ad\u2010-\u2015-]\s*\n\s*(?=\w)",
            "",
            normalized_value,
        )
        normalized_value = re.sub(r"[\u00ad\u2010-\u2015-]", " ", normalized_value)
        return " ".join(re.findall(r"\w+", normalized_value))

    def contains_phrase(normalized_text: str, phrase: str) -> bool:
        normalized_phrase = normalize(phrase)
        return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_text} "

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
    seen_questions: set[str] = set()
    seen_question_tokens: List[set[str]] = []
    section_question_counts: Dict[int, int] = {}
    section_no_progress: Dict[int, int] = {}

    def parse_response(raw: str) -> List[Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].strip()

        parsed: Any = None
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for position, character in enumerate(cleaned):
                if character not in "[{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(cleaned[position:])
                    break
                except json.JSONDecodeError:
                    continue

        if isinstance(parsed, dict):
            parsed = parsed.get("questions", parsed.get("items"))
        return parsed if isinstance(parsed, list) else []

    def accept_items(parsed: List[Any], limit: int) -> int:
        accepted = 0
        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "does", "for",
            "from", "how", "in", "is", "it", "of", "on", "or", "that", "the",
            "this", "to", "what", "when", "where", "which", "who", "why", "with",
        }
        for item in parsed:
            if accepted >= limit or len(questions) >= target_count:
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
                not contains_phrase(normalized_context, evidence)
                or not contains_phrase(normalized_evidence, answer)
            ):
                continue

            if not isinstance(choices, list):
                choices = []
            source_choices = [
                choice.strip()
                for choice in choices
                if (
                    isinstance(choice, str)
                    and choice.strip()
                    and len(choice.strip()) <= 200
                    and contains_phrase(normalized_context, choice)
                )
            ]
            normalized_question = normalize(question)
            question_tokens = set(normalized_question.split()) - stop_words
            if (
                normalized_question in seen_questions
                or (
                    question_tokens
                    and any(
                        len(question_tokens & prior_tokens)
                        / max(len(question_tokens | prior_tokens), 1)
                        >= 0.9
                        for prior_tokens in seen_question_tokens
                    )
                )
            ):
                continue

            seen_questions.add(normalized_question)
            seen_question_tokens.append(question_tokens)
            questions.append(
                {
                    "question": question.strip(),
                    "choices": choices,
                    "correct_answer": answer.strip(),
                    "explanation": evidence.strip(),
                    "source_excerpt": evidence.strip(),
                    "choice_suggestions": source_choices,
                    "generation_method": "ai",
                }
            )
            accepted += 1
        return accepted

    def generate_for_section(
        index: int,
        requested_count: int,
        is_retry: bool,
    ) -> int:
        source_chunk = chunks[index]
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
        if is_retry:
            retry_guidance = (
                "Retry only the remaining request. The prior response contained invalid, duplicate, "
                "or unsupported items. Return new complete questions with an answer found verbatim in "
                "an exact evidence excerpt from this selected document section. Keep evidence at or "
                "below 1000 characters. Do not invent facts or choices.\n"
            )
        prompt = (
            f"Analyze this selected lecture excerpt and create up to {requested_count} unique "
            "multiple-choice assessment questions. "
            f"Difficulty: {difficulty.upper()}. {difficulty_guidance} "
            "Use only this excerpt; do not use prior knowledge, other documents, external sources, "
            "or unsupported assumptions. Identify important concepts and learning objectives in "
            "this section. Questions must be clear, specific, unambiguous, and have exactly one "
            "correct choice. Include four distinct choices copied verbatim from the document when "
            "possible. The correct_answer must be copied verbatim from the evidence excerpt. The "
            "evidence must be an exact excerpt of no more than 1000 characters from this text and "
            "contain the correct answer. Keep evidence concise and use the shortest complete sentence "
            "or passage that supports the answer. Do not create a question if the excerpt cannot "
            "support it. Return a JSON array only; each object must contain question, choices, "
            "correct_answer, evidence.\n"
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
            max_output_tokens=max(1200, requested_count * 450),
        )
        if not isinstance(raw, str):
            return 0
        return accept_items(parse_response(raw), requested_count)

    section_count = min(len(chunks), target_count)
    primary_indices = (
        [0]
        if section_count == 1
        else [
            (position * (len(chunks) - 1)) // (section_count - 1)
            for position in range(section_count)
        ]
    )
    primary_indices = list(dict.fromkeys(primary_indices))
    section_question_counts = {index: 0 for index in primary_indices}
    remaining_allocations = target_count - len(primary_indices)
    total_weight = sum(len(chunks[index]) for index in primary_indices) or len(primary_indices)
    allocations: Dict[int, int] = {index: 1 for index in primary_indices}
    allocation_remainders = []
    for index in primary_indices:
        share = remaining_allocations * len(chunks[index]) / total_weight
        whole_share = int(share)
        allocations[index] += whole_share
        allocation_remainders.append((share - whole_share, index))
    unallocated = target_count - sum(allocations.values())
    for _, index in sorted(allocation_remainders, reverse=True)[:unallocated]:
        allocations[index] += 1

    try:
        for index in primary_indices:
            requested_count = min(5, allocations[index], target_count - len(questions))
            if requested_count:
                section_question_counts[index] += generate_for_section(
                    index,
                    requested_count,
                    is_retry=False,
                )

        max_retry_rounds = max((count + 4) // 5 for count in allocations.values()) + 2
        for _ in range(max_retry_rounds):
            if len(questions) >= target_count:
                break
            made_progress = False
            has_pending_sections = False
            for index in primary_indices:
                deficit = allocations[index] - section_question_counts[index]
                if deficit <= 0 or section_no_progress.get(index, 0) >= 2:
                    continue
                has_pending_sections = True
                requested_count = min(5, deficit, target_count - len(questions))
                added = generate_for_section(index, requested_count, is_retry=True)
                section_question_counts[index] += added
                made_progress = made_progress or added > 0
                section_no_progress[index] = (
                    0 if added else section_no_progress.get(index, 0) + 1
                )
            if not has_pending_sections or not made_progress:
                break

        if len(questions) < target_count:
            primary_set = set(primary_indices)
            fallback_indices = [
                index for index in range(len(chunks)) if index not in primary_set
            ]
            fallback_call_budget = min(
                len(fallback_indices) * 2,
                max(2, target_count * 2),
            )
            for index in fallback_indices:
                no_progress = 0
                while (
                    len(questions) < target_count
                    and fallback_call_budget > 0
                    and no_progress < 2
                ):
                    requested_count = min(5, target_count - len(questions))
                    added = generate_for_section(
                        index,
                        requested_count,
                        is_retry=no_progress > 0,
                    )
                    fallback_call_budget -= 1
                    no_progress = 0 if added else no_progress + 1
                    if added == 0:
                        continue
                    break
                if len(questions) >= target_count or fallback_call_budget <= 0:
                    break
    except AIProviderError as exc:
        raise HTTPException(
            502,
            f"Quiz generation could not reach the AI provider: {exc}",
        ) from exc

    if len(questions) != target_count:
        raise HTTPException(
            502,
            f"Only {len(questions)} of {target_count} requested questions could be verified against "
            "the selected document. The remaining items failed source or uniqueness checks, so this "
            "does not by itself prove the document lacks content. Try fewer questions, use a clearer "
            "or broader document, or generate again. No partial quiz was returned.",
        )

    answer_bank: Dict[str, str] = {}
    for question in questions:
        for choice in [question["correct_answer"], *question["choice_suggestions"]]:
            normalized_choice = normalize(choice)
            if normalized_choice and normalized_choice not in answer_bank:
                answer_bank[normalized_choice] = choice

    for question in questions:
        correct_answer = question["correct_answer"]
        options = [correct_answer]
        seen_options = {normalize(correct_answer)}
        for choice in question["choice_suggestions"]:
            normalized_choice = normalize(choice)
            if normalized_choice not in seen_options and len(options) < 4:
                options.append(choice)
                seen_options.add(normalized_choice)
        if len(options) < 4:
            distractors = [
                choice
                for normalized_choice, choice in answer_bank.items()
                if normalized_choice not in seen_options
            ]
            random.shuffle(distractors)
            for distractor in distractors:
                options.append(distractor)
                seen_options.add(normalize(distractor))
                if len(options) == 4:
                    break
        if len(options) != 4:
            raise HTTPException(
                502,
                "The selected document did not provide enough distinct, source-supported answer choices to build the requested quiz. Try a smaller quiz or select a document with more key concepts.",
            )
        random.shuffle(options)
        question["choices"] = options
        question.pop("choice_suggestions", None)
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
