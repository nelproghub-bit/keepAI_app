import unittest
import json
from unittest.mock import patch

from pydantic import ValidationError

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.core.security import get_current_student_user
from app.services.gemini_service import AIProviderError, AIService
from app.routers import learning_tools
from app.routers.learning_tools import (
    LessonRequest,
    build_typed_quiz_questions,
    generate_grounded_quiz_questions,
)

app = FastAPI()
app.include_router(learning_tools.router, prefix="/api")
app.dependency_overrides[get_current_student_user] = lambda: {
    "id": "quiz-types-test-student",
    "username": "quiz-types-student",
    "role": "student",
}


class QuizQuestionTypeTests(unittest.TestCase):
    def setUp(self):
        self.source_questions = [
            {
                "question": f"What is concept {number}?",
                "choices": [
                    f"Correct concept {number}",
                    f"Incorrect concept {number} A",
                    f"Incorrect concept {number} B",
                    f"Incorrect concept {number} C",
                ],
                "correct_answer": f"Correct concept {number}",
                "explanation": f"Lesson explanation {number}.",
                "source_excerpt": f"According to the lesson, Correct concept {number} is accurate.",
            }
            for number in range(1, 8)
        ]
        self.client = TestClient(app)

    def test_builds_each_requested_question_type_and_counts_matching_as_one(self):
        counts = {
            "identification": 1,
            "multiple_choice": 1,
            "true_false": 1,
            "fill_blank": 1,
            "matching": 1,
        }

        questions = build_typed_quiz_questions(self.source_questions, counts)

        self.assertEqual(len(questions), sum(counts.values()))
        self.assertEqual(
            [question["question_type"] for question in questions],
            list(counts.keys()),
        )
        self.assertEqual(len(questions[-1]["pairs"]), 3)
        self.assertEqual(len(questions[-1]["choices"]), 3)
        self.assertIn("Correct concept 5", questions[-1]["source_excerpt"])
        self.assertIn("Correct concept 1", questions[0]["source_excerpt"])
        self.assertIn(questions[2]["correct_answer"], {"True", "False"})
        self.assertIn("____", questions[3]["question"])
        self.assertNotIn("Correct concept 4", questions[3]["question"])

    @patch.object(learning_tools, "get_tutor_context")
    @patch.object(learning_tools, "get_all_document_chunks")
    def test_selected_document_context_does_not_mix_other_files(
        self,
        get_chunks,
        get_tutor_context,
    ):
        full_document_text = "Evidence from the selected document. " * 500
        get_chunks.return_value = [
            {"filename": "selected.pdf", "text": full_document_text},
        ]

        context, sources = learning_tools.get_lesson_context(
            "student-id",
            "assessment",
            target_filename="selected.pdf",
        )

        self.assertEqual(context, full_document_text)
        self.assertEqual(sources, ["selected.pdf"])
        get_tutor_context.assert_not_called()

    def test_question_counts_require_supported_formats_and_maximum_100(self):
        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"essay": 1})

        with self.assertRaises(ValidationError):
            LessonRequest(difficulty="very hard")

        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"multiple_choice": 101})

        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"matching": 50, "true_false": 51})

    def test_existing_question_count_request_remains_supported(self):
        request = LessonRequest(question_count=10)

        self.assertEqual(request.question_count, 10)
        self.assertIsNone(request.question_counts)

    @patch("app.services.gemini_service.GEMINI_API_KEY", "test-key")
    @patch("app.services.gemini_service.requests.post")
    def test_gemini_generation_applies_quiz_output_token_budget(self, post):
        post.return_value.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}],
        }

        response = AIService()._generate_gemini(
            "Generate quiz items",
            "Use only the source.",
            max_output_tokens=2250,
        )

        self.assertEqual(response, "[]")
        self.assertEqual(
            post.call_args.kwargs["json"]["generationConfig"]["maxOutputTokens"],
            2250,
        )

    def test_quiz_endpoint_requires_a_selected_source_document(self):
        response = self.client.post(
            "/api/learning/quiz",
            json={"question_counts": {"multiple_choice": 1}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Select a source document", response.json()["detail"])

    @patch.object(learning_tools, "generate")
    def test_grounded_generator_requires_verbatim_source_evidence(self, generate):
        lesson = (
            "Human-computer interaction studies how people use and experience technology. "
            "Usability is the ease with which users can complete tasks. "
            "Interface design organizes visible controls and interactions. "
            "User research observes people using products."
        )
        generated_question = {
            "question": "Which field studies how people use and experience technology?",
            "choices": [
                "Human-computer interaction",
                "Usability",
                "Interface design",
                "User research",
            ],
            "correct_answer": "Human-computer interaction",
            "explanation": "Human-computer interaction studies how people use and experience technology.",
            "evidence": "Human-computer interaction studies how people use and experience technology.",
        }
        generate.return_value = json.dumps([generated_question])

        questions = generate_grounded_quiz_questions(
            context=lesson,
            target_count=1,
            difficulty="easy",
        )

        self.assertEqual(questions[0]["source_excerpt"], generated_question["evidence"])
        self.assertEqual(questions[0]["correct_answer"], generated_question["correct_answer"])
        self.assertIn("EASY", generate.call_args.args[0])
        self.assertIn("basic concepts, definitions, terminology", generate.call_args.args[0])
        self.assertIn("User research observes people using products.", generate.call_args.args[0])
        self.assertTrue(generate.call_args.kwargs["has_sources"])

    @patch.object(learning_tools, "generate")
    def test_generator_retries_once_after_an_unusable_ai_response(self, generate):
        evidence = "Usability is the ease with which users can complete tasks."
        item = {
            "question": "What is usability?",
            "choices": ["Usability", "User experience", "Interface design", "User research"],
            "correct_answer": "Usability",
            "explanation": evidence,
            "evidence": evidence,
        }
        generate.side_effect = ["not valid JSON", json.dumps([item])]

        questions = generate_grounded_quiz_questions(
            context=(
                f"{evidence} User experience describes a person's overall perception of a product. "
                "Interface design organizes visible controls and interactions. "
                "User research observes people using products."
            ),
            target_count=1,
            difficulty="easy",
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(generate.call_count, 2)

    @patch.object(learning_tools, "generate")
    def test_generator_processes_later_document_sections_after_reaching_count(self, generate):
        first_section = (
            "Human-computer interaction studies how people use and experience technology. "
            "Usability is the ease with which users can complete tasks. "
            "Interface design organizes visible controls and interactions. "
            "User research observes people using products."
        )
        second_section = "A later section describes the evaluation of those interactions."
        filler = "This lesson section records additional context. " * 220
        item = {
            "question": "Which field studies how people use and experience technology?",
            "choices": [
                "Human-computer interaction",
                "Usability",
                "Interface design",
                "User research",
            ],
            "correct_answer": "Human-computer interaction",
            "explanation": "Human-computer interaction studies how people use and experience technology.",
            "evidence": "Human-computer interaction studies how people use and experience technology.",
        }
        generate.side_effect = [json.dumps([item]), "[]"]

        questions = generate_grounded_quiz_questions(
            context=f"{first_section}\n\n{filler}\n\n{second_section}",
            target_count=1,
            difficulty="medium",
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(generate.call_count, 2)
        self.assertIn(second_section, generate.call_args.args[0])

    @patch.object(learning_tools, "generate")
    def test_generator_batches_thirty_questions_without_truncating_output(self, generate):
        definitions = [
            f"TopicTerm{number} refers to the distinct concept described in section {number}."
            for number in range(30)
        ]
        lesson = " ".join(definitions)
        question_batches = []
        for batch_start in range(0, 30, 5):
            batch = []
            for number in range(batch_start, batch_start + 5):
                term = f"TopicTerm{number}"
                evidence = definitions[number]
                choices = [
                    term,
                    f"TopicTerm{(number + 1) % 30}",
                    f"TopicTerm{(number + 2) % 30}",
                    f"TopicTerm{(number + 3) % 30}",
                ]
                batch.append(
                    {
                        "question": f"Which term is described here: {term}?",
                        "choices": choices,
                        "correct_answer": term,
                        "explanation": evidence,
                        "evidence": evidence,
                    }
                )
            question_batches.append(json.dumps(batch))
        generate.side_effect = question_batches

        questions = generate_grounded_quiz_questions(
            context=lesson,
            target_count=30,
            difficulty="easy",
        )

        self.assertEqual(len(questions), 30)
        self.assertEqual(generate.call_count, 6)
        self.assertTrue(
            all(call.kwargs["max_output_tokens"] >= 2000 for call in generate.call_args_list)
        )

    @patch.object(learning_tools, "generate")
    def test_provider_outage_reports_ai_error_without_extracting_questions(self, generate):
        generate.side_effect = AIProviderError("provider unavailable")

        with self.assertRaises(HTTPException) as error:
            generate_grounded_quiz_questions(
                context="A selected lesson contains some text.",
                target_count=1,
                difficulty="medium",
            )

        self.assertEqual(error.exception.status_code, 502)
        self.assertIn("quiz AI is unavailable", error.exception.detail)
        self.assertEqual(generate.call_count, 1)

    @patch.object(learning_tools, "generate")
    def test_unsupported_choices_are_rejected_instead_of_replaced(self, generate):
        generate.return_value = json.dumps(
            [
                {
                    "question": "Which field connects devices?",
                    "choices": ["IoT", "HCI", "SQL", "CSS"],
                    "correct_answer": "IoT",
                    "explanation": "The lesson discusses human-computer interaction and usability.",
                    "evidence": "The lesson discusses human-computer interaction and usability.",
                }
            ]
        )

        source_context = "The lesson discusses human-computer interaction and usability."
        with self.assertRaises(HTTPException) as error:
            generate_grounded_quiz_questions(
                context=source_context,
                target_count=1,
                difficulty="hard",
            )

        self.assertEqual(error.exception.status_code, 502)
        self.assertIn("does not contain enough", error.exception.detail)
        self.assertEqual(generate.call_count, 2)

    @patch.object(learning_tools, "record_activity")
    @patch.object(learning_tools.user_service, "increment_stat")
    @patch.object(learning_tools, "generate_grounded_quiz_questions")
    @patch.object(learning_tools, "get_lesson_context")
    @patch.object(learning_tools, "get_owned_document_name")
    def test_quiz_endpoint_returns_requested_types_and_exact_counts(
        self,
        get_document,
        get_context,
        generate_questions,
        increment_stat,
        record_activity,
    ):
        counts = {
            "identification": 1,
            "multiple_choice": 1,
            "true_false": 1,
            "fill_blank": 1,
            "matching": 1,
        }
        get_document.return_value = "lesson.pdf"
        get_context.return_value = ("Lesson text", ["lesson.pdf"])
        generate_questions.return_value = self.source_questions

        response = self.client.post(
            "/api/learning/quiz",
            json={
                "topic": "Lesson review",
                "document_name": "lesson.pdf",
                "difficulty": "hard",
                "question_counts": counts,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total_questions"], sum(counts.values()))
        self.assertEqual(payload["question_counts"], counts)
        self.assertEqual(payload["difficulty"], "hard")
        self.assertEqual(payload["generation_mode"], "ai")
        self.assertEqual(
            [question["question_type"] for question in payload["questions"]],
            list(counts.keys()),
        )
        self.assertEqual(len(payload["questions"][-1]["pairs"]), 3)
        generate_questions.assert_called_once_with(
            context="Lesson text",
            target_count=7,
            difficulty="hard",
        )


if __name__ == "__main__":
    unittest.main()
