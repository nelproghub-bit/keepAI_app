import unittest
import json
from unittest.mock import patch

from pydantic import ValidationError

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.core.security import get_current_student_user
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

    @patch.object(learning_tools, "get_tutor_context")
    @patch.object(learning_tools, "get_all_document_chunks")
    def test_selected_document_context_does_not_mix_other_files(
        self,
        get_chunks,
        get_tutor_context,
    ):
        get_chunks.return_value = [
            {"filename": "selected.pdf", "text": "Evidence from the selected document."},
        ]

        context, sources = learning_tools.get_lesson_context(
            "student-id",
            "assessment",
            target_filename="selected.pdf",
        )

        self.assertEqual(context, "Evidence from the selected document.")
        self.assertEqual(sources, ["selected.pdf"])
        get_tutor_context.assert_not_called()

    def test_question_counts_require_supported_formats_and_maximum_100(self):
        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"essay": 1})

        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"multiple_choice": 101})

        with self.assertRaises(ValidationError):
            LessonRequest(question_counts={"matching": 50, "true_false": 51})

    def test_existing_question_count_request_remains_supported(self):
        request = LessonRequest(question_count=10)

        self.assertEqual(request.question_count, 10)
        self.assertIsNone(request.question_counts)

    @patch.object(learning_tools, "generate")
    def test_grounded_generator_requires_verbatim_source_evidence(self, generate):
        lesson = "Human-computer interaction studies how people use and experience technology."
        generated_question = {
            "question": "What does human-computer interaction study?",
            "choices": [
                "Internet of Things networking",
                "Human-computer interaction studies how people use and experience technology",
                "Database normalization",
                "Climate modeling",
            ],
            "correct_answer": "Human-computer interaction studies how people use and experience technology",
            "explanation": "The lesson states this definition.",
            "evidence": "Human-computer interaction studies how people use and experience technology.",
        }
        generate.return_value = json.dumps([generated_question])

        questions = generate_grounded_quiz_questions(
            context=lesson,
            target_count=1,
            topic="Human-computer interaction",
        )

        self.assertEqual(questions[0]["source_excerpt"], generated_question["evidence"])
        self.assertEqual(questions[0]["correct_answer"], generated_question["correct_answer"])
        self.assertIn("SELECTED LESSON", generate.call_args.args[0])
        self.assertIn(lesson, generate.call_args.args[0])
        self.assertTrue(generate.call_args.kwargs["has_sources"])

    @patch.object(learning_tools, "generate")
    def test_unrelated_or_unverifiable_questions_never_return(self, generate):
        generate.return_value = json.dumps(
            [
                {
                    "question": "What is the primary definition of IoT?",
                    "choices": ["IoT", "HCI", "SQL", "CSS"],
                    "correct_answer": "IoT",
                    "explanation": "A general answer.",
                    "evidence": "IoT connects physical devices to exchange data.",
                }
            ]
        )

        with self.assertRaises(HTTPException) as error:
            generate_grounded_quiz_questions(
                context="The lesson discusses human-computer interaction and usability.",
                target_count=1,
                topic="Human-computer interaction",
            )

        self.assertEqual(error.exception.status_code, 502)
        self.assertIn("verifiable evidence", error.exception.detail)
        self.assertEqual(generate.call_count, 3)

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
                "question_counts": counts,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total_questions"], sum(counts.values()))
        self.assertEqual(payload["question_counts"], counts)
        self.assertEqual(
            [question["question_type"] for question in payload["questions"]],
            list(counts.keys()),
        )
        self.assertEqual(len(payload["questions"][-1]["pairs"]), 3)
        generate_questions.assert_called_once_with(
            context="Lesson text",
            target_count=7,
            topic="Lesson review",
        )


if __name__ == "__main__":
    unittest.main()
