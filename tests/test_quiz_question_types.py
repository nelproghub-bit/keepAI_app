import unittest
from unittest.mock import patch

from pydantic import ValidationError

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.security import get_current_student_user
from app.routers import learning_tools
from app.routers.learning_tools import (
    LessonRequest,
    build_typed_quiz_questions,
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
        self.assertIn(questions[2]["correct_answer"], {"True", "False"})
        self.assertIn("____", questions[3]["question"])

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

    @patch.object(learning_tools, "record_activity")
    @patch.object(learning_tools.user_service, "increment_stat")
    @patch.object(learning_tools, "synthesize_questions_from_document")
    @patch.object(learning_tools, "get_lesson_context")
    @patch.object(learning_tools, "get_owned_document_name")
    def test_quiz_endpoint_returns_requested_types_and_exact_counts(
        self,
        get_document,
        get_context,
        synthesize,
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
        synthesize.return_value = self.source_questions

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
        synthesize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
