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
    _is_valid_flashcard_candidate,
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
        self.assertIn("<student_query>", generate.call_args.args[0])
        self.assertIn("<lesson_document_excerpt>", generate.call_args.args[0])
        self.assertTrue(generate.call_args.kwargs["has_sources"])

    @patch.object(learning_tools, "generate")
    def test_invalid_response_is_retried_and_wrapped_json_is_parsed(self, generate):
        evidence = "Usability is the ease with which users can complete tasks."
        card = {
            "front": "Usability",
            "back": "the ease with which users can complete tasks",
            "source_excerpt": evidence,
        }
        generate.side_effect = [
            "not JSON",
            f'```json\n{{"flashcards": [{json.dumps(card)}]}}\n```',
        ]

        cards = generate_flashcards_from_document(
            evidence,
            "",
            1,
            "term-definition",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("focused retry", generate.call_args_list[1].args[0])
        self.assertGreaterEqual(
            generate.call_args_list[0].kwargs["max_output_tokens"],
            450,
        )

    @patch.object(learning_tools, "generate")
    def test_generation_distributes_cards_across_the_selected_document(self, generate):
        parts = []
        expected = {}
        for index in range(3):
            term = f"Topic{index}"
            evidence = f"{term} is the important concept for subject {index}."
            expected[term] = evidence
            parts.append(evidence + " " + (f"Additional material for subject {index}. " * 220))
        document = "\n\n".join(parts)

        def generate_for_section(prompt, **kwargs):
            matches = [
                (term, evidence)
                for term, evidence in expected.items()
                if evidence in prompt
            ]
            term, evidence = matches[-1]
            return json.dumps(
                [
                    {
                        "front": term,
                        "back": f"the important concept for subject {term[-1]}",
                        "source_excerpt": evidence,
                    }
                ]
            )

        generate.side_effect = generate_for_section

        cards = generate_flashcards_from_document(
            document,
            "",
            3,
            "term-definition",
        )

        self.assertEqual(len(cards), 3)
        self.assertEqual({card["front"] for card in cards}, set(expected))
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(
            {card["card_type"] for card in cards},
            {"term-definition"},
        )

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
            "",
            2,
            "term-definition",
        )

        self.assertEqual(len(cards), 2)
        self.assertEqual([card["front"] for card in cards], ["Human-computer interaction", "Usability"])
        self.assertTrue(all(card["generation_method"] == "document_extract" for card in cards))
        self.assertTrue(all(card["source_excerpt"] in source for card in cards))

    @patch.object(learning_tools, "generate", return_value="[]")
    def test_arbitrary_paragraphs_are_not_turned_into_flashcards(self, generate):
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
        self.assertEqual(examples[0]["front"], "The system uses a queue")
        self.assertEqual(examples[0]["back"], "for example, a print queue manages pending jobs.")
        self.assertIn(examples[0]["back"], examples[0]["source_excerpt"])

    def test_quality_checks_enforce_selected_flashcard_format(self):
        examples = [
            (
                "term-definition",
                "Usability",
                "The ease with which users can complete tasks.",
                "Usability is the ease with which users can complete tasks.",
            ),
            (
                "question-answer",
                "What does a router forward?",
                "network packets",
                "A router forwards network packets between connected networks.",
            ),
            (
                "concept-example",
                "The system uses a queue",
                "for example, a print queue stores pending jobs.",
                "The system uses a queue, for example, a print queue stores pending jobs.",
            ),
            (
                "fill-blank",
                "The ______ protocol uses a broker to route messages.",
                "MQTT",
                "The MQTT protocol uses a broker to route messages.",
            ),
        ]
        for card_type, front, back, evidence in examples:
            with self.subTest(card_type=card_type):
                self.assertTrue(
                    _is_valid_flashcard_candidate(front, back, evidence, evidence, card_type, "")
                )

        self.assertFalse(
            _is_valid_flashcard_candidate(
                "A router forwards network packets.",
                "network packets",
                "A router forwards network packets between connected networks.",
                "A router forwards network packets between connected networks.",
                "question-answer",
                "",
            )
        )
        self.assertFalse(
            _is_valid_flashcard_candidate(
                "The ______ protocol uses a broker to route messages.",
                "broker",
                "The MQTT protocol uses a broker to route messages.",
                "The MQTT protocol uses a broker to route messages.",
                "fill-blank",
                "",
            )
        )
        self.assertFalse(
            _is_valid_flashcard_candidate(
                "Usability",
                "the ease with which users can complete tasks",
                "Usability is the ease with which users can complete tasks.",
                (
                    "Usability is the ease with which users can complete tasks. "
                    "Reliability is the ability of a system to perform consistently."
                ),
                "term-definition",
                "Reliability",
            )
        )

    def test_extractive_fallback_respects_focus_topic(self):
        source = (
            "Usability is the ease with which users can complete tasks. "
            "Reliability is the ability of a system to perform consistently."
        )
        cards = build_extractive_flashcards(
            source,
            "term-definition",
            focus_topic="usability",
        )

        self.assertEqual([card["front"] for card in cards], ["Usability"])

    @patch.object(
        learning_tools,
        "generate",
        return_value=json.dumps(
            [{
                "front": "Usability",
                "back": "the ease with which users can complete tasks",
                "source_excerpt": "Usability is the ease with which users can complete tasks.",
            }]
        ),
    )
    def test_generation_fails_instead_of_returning_fewer_than_requested(self, generate):
        with self.assertRaises(HTTPException) as error:
            generate_flashcards_from_document(
                "Usability is the ease with which users can complete tasks.",
                "",
                2,
                "term-definition",
            )

        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("Only 1 distinct", error.exception.detail)

    @patch.object(learning_tools, "generate")
    def test_generation_never_returns_more_cards_than_requested(self, generate):
        source = (
            "Usability is the ease with which users can complete tasks. "
            "Reliability is the ability of a system to perform consistently. "
            "Availability is the percentage of time a system remains operational."
        )
        generate.return_value = json.dumps(
            [{
                "front": "Usability",
                "back": "the ease with which users can complete tasks",
                "source_excerpt": "Usability is the ease with which users can complete tasks.",
            }]
        )

        cards = generate_flashcards_from_document(
            source,
            "",
            2,
            "term-definition",
        )

        self.assertEqual(len(cards), 2)
        self.assertEqual([card["front"] for card in cards], ["Usability", "Reliability"])
        self.assertEqual(len({card["card_key"] for card in cards}), 2)

    @patch.object(learning_tools, "_generate_flashcards_for_type")
    def test_multi_type_generation_splits_exact_total_evenly(self, generate_type):
        types = ["term-definition", "question-answer", "fill-blank"]

        def generate_for_type(_, __, count, card_type):
            return [
                {
                    "front": f"{card_type} card {index}",
                    "back": f"Answer {index}",
                    "source_excerpt": f"Evidence {index}",
                    "card_type": card_type,
                    "card_key": f"{card_type}-{index}",
                }
                for index in range(count)
            ]

        generate_type.side_effect = generate_for_type

        cards = learning_tools.generate_flashcards_from_document(
            "Selected lesson text.",
            "",
            10,
            types,
        )

        self.assertEqual(len(cards), 10)
        self.assertEqual(
            [call.args[2] for call in generate_type.call_args_list],
            [4, 3, 3],
        )
        self.assertEqual(
            {card_type: sum(card["card_type"] == card_type for card in cards) for card_type in types},
            {"term-definition": 4, "question-answer": 3, "fill-blank": 3},
        )

    @patch.object(learning_tools.user_service, "increment_stat")
    @patch.object(learning_tools, "generate_flashcards_from_document")
    @patch.object(learning_tools, "get_lesson_context")
    def test_endpoint_generates_exact_count_from_only_the_selected_document(
        self,
        get_lesson_context,
        generate_cards,
        increment_stat,
    ):
        get_lesson_context.return_value = ("SELECTED DOCUMENT ONLY", ["selected.docx"])
        generate_cards.return_value = [
            {"front": "Term 1", "back": "Definition 1", "source_excerpt": "Evidence 1", "card_type": "term-definition"},
            {"front": "Term 2", "back": "Definition 2", "source_excerpt": "Evidence 2", "card_type": "term-definition"},
        ]

        response = self.client.post(
            "/api/learning/flashcards",
            json={
                "document_name": "selected.docx",
                "card_count": 2,
                "card_type": "term-definition",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total_cards"], 2)
        self.assertEqual(len(response.json()["cards"]), 2)
        self.assertEqual(response.json()["document_name"], "selected.docx")
        self.assertEqual(generate_cards.call_args.args[0], "SELECTED DOCUMENT ONLY")
        self.assertEqual(generate_cards.call_args.args[2:], (2, "term-definition"))
        increment_stat.assert_called_once()

    @patch.object(learning_tools.user_service, "increment_stat")
    @patch.object(learning_tools, "generate_flashcards_from_document")
    @patch.object(learning_tools, "get_lesson_context")
    def test_endpoint_splits_total_evenly_across_selected_types(
        self,
        get_lesson_context,
        generate_cards,
        increment_stat,
    ):
        selected_types = ["term-definition", "question-answer", "fill-blank"]
        get_lesson_context.return_value = ("selected source", ["selected.docx"])

        def make_cards(_, __, count, card_types):
            quotient, remainder = divmod(count, len(card_types))
            return [
                {
                    "front": f"{card_type} {index}",
                    "back": f"Answer {index}",
                    "source_excerpt": f"Evidence {index}",
                    "card_type": card_type,
                }
                for position, card_type in enumerate(card_types)
                for index in range(quotient + (position < remainder))
            ]

        generate_cards.side_effect = make_cards
        response = self.client.post(
            "/api/learning/flashcards",
            json={
                "document_name": "selected.docx",
                "card_count": 10,
                "card_types": selected_types,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total_cards"], 10)
        self.assertEqual(generate_cards.call_count, 1)
        self.assertEqual(generate_cards.call_args.args[2:], (10, selected_types))
        self.assertEqual(response.json()["card_types"], selected_types)
        self.assertEqual(
            {
                card_type: sum(card["card_type"] == card_type for card in response.json()["cards"])
                for card_type in selected_types
            },
            {"term-definition": 4, "question-answer": 3, "fill-blank": 3},
        )
        self.assertEqual(
            {card["card_type"] for card in response.json()["cards"]},
            set(selected_types),
        )
        increment_stat.assert_called_once()

    def test_invalid_flashcard_type_is_rejected(self):
        with self.assertRaises(Exception):
            FlashcardRequest(card_type="unsupported")

    def test_request_supports_unique_selected_types_and_one_card_per_type(self):
        request = FlashcardRequest(
            card_count=3,
            card_types=["term-definition", "question-answer", "fill-blank"],
        )

        self.assertEqual(len(request.card_types), 3)
        self.assertEqual(FlashcardRequest(card_count=100).card_count, 100)
        with self.assertRaises(Exception):
            FlashcardRequest(card_count=1, card_types=["term-definition", "question-answer"])
        with self.assertRaises(Exception):
            FlashcardRequest(card_count=101)
        with self.assertRaises(Exception):
            FlashcardRequest(card_types=["term-definition", "term-definition"])
        with self.assertRaises(Exception):
            FlashcardRequest(card_types=["unsupported"])

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
