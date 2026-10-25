import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import get_current_student_user
from app.routers import learning_tools
from app.routers.learning_tools import (
    FlashcardRequest,
    build_extractive_flashcards,
    generate_flashcards_from_document,
)


app = FastAPI()
app.include_router(learning_tools.router, prefix="/api")
app.dependency_overrides[get_current_student_user] = lambda: {
    "id": "flashcard-test-student",
    "username": "flashcard-student",
    "role": "student",
}


class FlashcardFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "flashcard-progress.db"
        conn = sqlite3.connect(self.database_path)
        try:
            conn.execute(
                """
                CREATE TABLE flashcard_progress (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    document_key TEXT NOT NULL,
                    card_key TEXT NOT NULL,
                    card_front TEXT NOT NULL,
                    mastered INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        self.connection_patch = patch.object(
            learning_tools,
            "get_connection",
            side_effect=self.open_database,
        )
        self.connection_patch.start()
        self.document_patch = patch.object(
            learning_tools,
            "get_owned_document_name",
            side_effect=lambda _, document_name: document_name,
        )
        self.document_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.document_patch.stop()
        self.connection_patch.stop()
        self.temp_dir.cleanup()

    def open_database(self):
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    @patch.object(learning_tools, "generate")
    def test_ai_flashcards_require_verbatim_evidence_and_keep_page(self, generate):
        excerpt = "[Page 4]\nUsability is the ease with which users can complete tasks."
        generated = {
            "front": "Usability",
            "back": "the ease with which users can complete tasks",
            "source_excerpt": "Usability is the ease with which users can complete tasks.",
        }
        generate.return_value = json.dumps([generated])

        cards = generate_flashcards_from_document(
            excerpt,
            "Usability",
            1,
            "term-definition",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["source_page"], 4)
        self.assertEqual(cards[0]["source_excerpt"], generated["source_excerpt"])
        self.assertEqual(cards[0]["generation_method"], "ai")
        self.assertIn(generated["back"], generated["source_excerpt"])
        self.assertTrue(cards[0]["card_key"])
        self.assertTrue(generate.call_args.kwargs["has_sources"])

    @patch.object(learning_tools, "generate")
    def test_invalid_ai_content_is_discarded_and_only_source_definitions_fallback(self, generate):
        generate.return_value = json.dumps(
            [
                {
                    "front": "Internet of Things",
                    "back": "A network of connected devices.",
                    "source_excerpt": "Internet of Things is a network of connected devices.",
                }
            ]
        )
        source = (
            "[Page 1]\n"
            "Human-computer interaction is the study of how people interact with computers. "
            "Usability is the ease with which users can complete tasks. "
            "Experience is a person's overall perception of a product."
        )

        cards = generate_flashcards_from_document(
            source,
            "Human-computer interaction",
            2,
            "term-definition",
        )

        self.assertEqual(len(cards), 2)
        self.assertEqual([card["front"] for card in cards], ["Human-computer interaction", "Usability"])
        self.assertTrue(all(card["generation_method"] == "document_extract" for card in cards))
        self.assertTrue(all(card["source_excerpt"] in source for card in cards))

    def test_arbitrary_paragraphs_are_not_turned_into_flashcards(self):
        cards = build_extractive_flashcards(
            "A sequence of unrelated words with no definition or explicit example.",
            "term-definition",
        )

        self.assertEqual(cards, [])
        with self.assertRaises(HTTPException) as error:
            generate_flashcards_from_document(
                "A sequence of unrelated words with no definition or explicit example.",
                "Unrelated",
                5,
                "term-definition",
            )
        self.assertEqual(error.exception.status_code, 422)

    def test_extractive_fallback_uses_specific_terms_and_explicit_examples(self):
        definitions = build_extractive_flashcards(
            "Usability: The ease with which users can complete tasks.",
            "term-definition",
        )
        examples = build_extractive_flashcards(
            "The system uses a queue, for example, a print queue manages pending jobs.",
            "concept-example",
        )

        self.assertEqual(definitions[0]["front"], "Usability")
        self.assertEqual(examples[0]["front"], "What example is given for system uses a queue?")
        self.assertEqual(examples[0]["back"], "for example, a print queue manages pending jobs.")
        self.assertIn(examples[0]["back"], examples[0]["source_excerpt"])

    def test_invalid_flashcard_type_is_rejected(self):
        with self.assertRaises(Exception):
            FlashcardRequest(card_type="unsupported")

    def test_mastery_progress_persists_per_user_and_document(self):
        first = self.client.put(
            "/api/learning/flashcards/progress",
            json={
                "document_name": "lecture.docx",
                "front": "Usability",
                "mastered": True,
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        card_key = first.json()["card_key"]

        restored = self.client.get(
            "/api/learning/flashcards/progress",
            params={"document_name": "lecture.docx"},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["mastered_card_keys"], [card_key])

        app.dependency_overrides[get_current_student_user] = lambda: {
            "id": "different-student",
            "username": "different-student",
            "role": "student",
        }
        try:
            other_user = self.client.get(
                "/api/learning/flashcards/progress",
                params={"document_name": "lecture.docx"},
            )
            self.assertEqual(other_user.status_code, 200, other_user.text)
            self.assertEqual(other_user.json()["mastered_card_keys"], [])
        finally:
            app.dependency_overrides[get_current_student_user] = lambda: {
                "id": "flashcard-test-student",
                "username": "flashcard-student",
                "role": "student",
            }


if __name__ == "__main__":
    unittest.main()
