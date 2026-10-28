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
    _parse_flashcard_response,
    _flashcard_concepts_are_similar,
    _source_page_for_excerpt,
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
            conn.execute(
                """
                CREATE TABLE flashcard_decks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    document_key TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    requested_count INTEGER NOT NULL,
                    card_types_json TEXT NOT NULL,
                    cards_json TEXT NOT NULL,
                    is_complete INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        self.assertIn("targeted replacement", generate.call_args_list[1].args[0])
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

    def test_extractive_fallback_resolves_pronoun_definitions_and_rejects_generic_terms(self):
        source = (
            "[Page 7]\n"
            "What is computer networking? It is the exchange of data between connected devices."
        )
        cards = build_extractive_flashcards(source, "term-definition")

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "computer networking")
        self.assertEqual(
            cards[0]["back"],
            "the exchange of data between connected devices.",
        )
        self.assertEqual(cards[0]["source_page"], 7)
        self.assertIn("What is computer networking?", cards[0]["source_excerpt"])
        focused_cards = build_extractive_flashcards(
            source,
            "term-definition",
            focus_topic="computer networking",
        )
        self.assertEqual(len(focused_cards), 1)

        for generic_front in ("What", "Define", "It"):
            with self.subTest(front=generic_front):
                self.assertFalse(
                    _is_valid_flashcard_candidate(
                        generic_front,
                        "the exchange of data between connected devices",
                        source,
                        source,
                        "term-definition",
                        "",
                    )
                )

    @patch.object(learning_tools, "generate", return_value="[]")
    def test_extractive_fallback_rejoins_pdf_line_wrapped_definitions(self, generate):
        source = (
            "[Page 3]\n"
            "Computer networking is the exchange of\n"
            "data between connected devices across a communication channel."
        )

        cards = generate_flashcards_from_document(
            source,
            "",
            1,
            "term-definition",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "Computer networking")
        self.assertIn("exchange of data between connected devices", cards[0]["back"])
        self.assertEqual(cards[0]["source_page"], 3)
        self.assertEqual(cards[0]["generation_method"], "document_extract")

    def test_extractive_fallback_uses_a_lesson_heading_for_pronoun_definition(self):
        source = (
            "[Page 5]\n"
            "Computer Networking\n"
            "It is the exchange of data between connected devices."
        )

        cards = build_extractive_flashcards(source, "term-definition")

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "Computer Networking")
        self.assertIn("exchange of data between connected devices", cards[0]["back"])
        self.assertEqual(cards[0]["source_page"], 5)

    def test_structured_candidate_parser_and_semantic_validation(self):
        parsed = _parse_flashcard_response(
            '```json\n{"cards":['
            '{"front":"What","back":"answer","source_excerpt":"A sufficiently long exact source passage."},'
            '{"front":"Usability","back":"the ease with which users complete tasks",'
            '"source_excerpt":"Usability is the ease with which users complete tasks."}]}\n```'
        )

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].front, "What")
        self.assertEqual(parsed[1].front, "Usability")
        self.assertFalse(
            _is_valid_flashcard_candidate(
                parsed[0].front,
                parsed[0].back,
                parsed[0].source_excerpt,
                parsed[0].source_excerpt,
                "term-definition",
                "",
            )
        )
        self.assertEqual(
            _source_page_for_excerpt(
                "[Page 2]\nAn earlier sentence.\n[Page 9]\nUsability is the ease with which users complete tasks.",
                "Usability is the ease with which users complete tasks.",
            ),
            9,
        )
        self.assertTrue(
            _flashcard_concepts_are_similar(
                ("computer", "interaction"),
                ("human", "computer", "interaction"),
            )
        )
        self.assertFalse(
            _flashcard_concepts_are_similar(
                ("network", "security"),
                ("network", "protocol"),
            )
        )

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
                "What does a router forward?",
                "reliability",
                (
                    "A router forwards network packets between connected networks. "
                    "Reliability is the ability of a system to perform consistently."
                ),
                (
                    "A router forwards network packets between connected networks. "
                    "Reliability is the ability of a system to perform consistently."
                ),
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
        self.assertFalse(
            _is_valid_flashcard_candidate(
                "Usability",
                "the ability of a system to perform consistently",
                (
                    "Usability is the ease with which users can complete tasks. "
                    "Reliability is the ability of a system to perform consistently."
                ),
                (
                    "Usability is the ease with which users can complete tasks. "
                    "Reliability is the ability of a system to perform consistently."
                ),
                "term-definition",
                "",
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
    def test_generation_returns_available_verified_cards_when_fewer_are_requested(self, generate):
        cards = generate_flashcards_from_document(
            "Usability is the ease with which users can complete tasks.",
            "",
            30,
            "term-definition",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["front"], "Usability")
        self.assertEqual(cards[0]["generation_method"], "ai")

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

    @patch.object(learning_tools, "generate", return_value="[]")
    def test_source_backed_fallback_meets_supported_counts_through_100(self, generate):
        source = "\n".join(
            f"[Page {index + 1}] Concept{index} is an important learning concept used to explain subject {index}."
            for index in range(100)
        )

        for requested_count in (10, 25, 50, 75, 100):
            with self.subTest(requested_count=requested_count):
                cards = generate_flashcards_from_document(
                    source,
                    "",
                    requested_count,
                    "term-definition",
                )

                self.assertEqual(len(cards), requested_count)
                self.assertEqual(
                    len({card["card_key"] for card in cards}),
                    requested_count,
                )
                self.assertTrue(
                    all(card["source_excerpt"] in source for card in cards)
                )

    @patch.object(learning_tools, "generate")
    def test_partial_ai_batches_are_replaced_from_remaining_source_definitions(self, generate):
        source = "\n".join(
            f"[Page {index + 1}] Concept{index} is an important learning concept used to explain subject {index}."
            for index in range(60)
        )
        evidence = (
            "[Page 1] Concept0 is an important learning concept used to explain subject 0."
        )
        generate.return_value = json.dumps(
            [
                {
                    "front": "Concept0",
                    "back": "an important learning concept used to explain subject 0",
                    "source_excerpt": evidence,
                }
            ]
        )

        cards = generate_flashcards_from_document(
            source,
            "",
            50,
            "term-definition",
        )

        self.assertEqual(len(cards), 50)
        self.assertEqual(len({card["card_key"] for card in cards}), 50)
        self.assertEqual(
            len({card["source_excerpt"] for card in cards}),
            50,
        )

    @patch.object(learning_tools, "generate", return_value="[]")
    def test_multiple_selected_types_receive_the_requested_verified_quotas(self, generate):
        source = "\n".join(
            f"[Page {index + 1}] Topic{index} is a distinct learning concept, "
            f"for example, a framework used to explain subject {index}."
            for index in range(12)
        )
        selected_types = [
            "term-definition",
            "question-answer",
            "concept-example",
            "fill-blank",
        ]

        cards = generate_flashcards_from_document(source, "", 10, selected_types)

        self.assertEqual(len(cards), 10)
        self.assertEqual(
            {
                card_type: sum(card["card_type"] == card_type for card in cards)
                for card_type in selected_types
            },
            {
                "term-definition": 3,
                "question-answer": 3,
                "concept-example": 2,
                "fill-blank": 2,
            },
        )
        self.assertEqual(
            len({card["source_excerpt"] for card in cards}),
            len(cards),
        )

    @patch.object(learning_tools, "_generate_flashcards_for_type")
    def test_multi_type_generation_splits_exact_total_evenly(self, generate_type):
        types = ["term-definition", "question-answer", "fill-blank"]

        def generate_for_type(_, __, count, card_type, existing_cards=None):
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

    @patch.object(learning_tools, "_generate_flashcards_for_type")
    def test_multi_type_generation_keeps_verified_cards_when_a_type_has_no_matches(self, generate_type):
        def generate_for_type(_, __, count, card_type, existing_cards=None):
            if card_type == "question-answer":
                raise HTTPException(422, "No supported question-answer cards.")
            return [{
                "front": f"{card_type} card",
                "back": "Answer",
                "source_excerpt": "Evidence",
                "card_type": card_type,
                "card_key": card_type,
            }]

        generate_type.side_effect = generate_for_type

        cards = generate_flashcards_from_document(
            "Selected lesson text.",
            "",
            6,
            ["term-definition", "question-answer"],
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["card_type"], "term-definition")
        self.assertEqual(generate_type.call_count, 2)

    @patch.object(learning_tools.user_service, "increment_stat")
    @patch.object(learning_tools, "generate_flashcards_from_document")
    @patch.object(learning_tools, "get_lesson_context")
    def test_upload_endpoint_generates_and_reuses_user_scoped_deck(
        self,
        get_lesson_context,
        generate_cards,
        increment_stat,
    ):
        source = (
            "Usability is the ease with which users can complete tasks. "
            "Reliability is the ability of a system to perform consistently."
        )
        generate_cards.return_value = [
            {
                "front": "Usability",
                "back": "the ease with which users can complete tasks",
                "source_excerpt": "Usability is the ease with which users can complete tasks.",
                "source_page": 1,
                "card_type": "term-definition",
                "generation_method": "ai",
            },
            {
                "front": "Reliability",
                "back": "the ability of a system to perform consistently",
                "source_excerpt": "Reliability is the ability of a system to perform consistently.",
                "source_page": 1,
                "card_type": "term-definition",
                "generation_method": "ai",
            },
        ]

        def upload():
            return self.client.post(
                "/api/learning/flashcards/upload",
                data={
                    "topic": "",
                    "card_count": "2",
                    "card_types": "term-definition",
                },
                files={"file": ("lesson.txt", source.encode("utf-8"), "text/plain")},
            )

        response = upload()
        cached_response = upload()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total_cards"], 2)
        self.assertEqual(response.json()["display_name"], "lesson.txt")
        self.assertTrue(response.json()["document_name"].startswith("flashcard-upload://"))
        self.assertEqual(cached_response.status_code, 200, cached_response.text)
        self.assertEqual(cached_response.json()["cards"], response.json()["cards"])
        generate_cards.assert_called_once()
        get_lesson_context.assert_not_called()
        self.assertEqual(increment_stat.call_count, 2)

        document_name = response.json()["document_name"]
        progress = self.client.get(
            "/api/learning/flashcards/progress",
            params={"document_name": document_name},
        )
        self.assertEqual(progress.status_code, 200, progress.text)
        saved = self.client.put(
            "/api/learning/flashcards/progress",
            json={
                "document_name": document_name,
                "front": "Usability",
                "mastered": True,
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        app.dependency_overrides[get_current_student_user] = lambda: {
            "id": "different-student",
            "username": "different-student",
            "role": "student",
        }
        try:
            denied = self.client.get(
                "/api/learning/flashcards/progress",
                params={"document_name": document_name},
            )
            self.assertEqual(denied.status_code, 404)
        finally:
            app.dependency_overrides[get_current_student_user] = lambda: {
                "id": "flashcard-test-student",
                "username": "flashcard-student",
                "role": "student",
            }

    def test_upload_rejects_unsupported_file_types(self):
        response = self.client.post(
            "/api/learning/flashcards/upload",
            data={"card_count": "1", "card_types": "term-definition"},
            files={"file": ("notes.exe", b"not a lesson", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)

    def test_library_flashcard_generation_endpoint_is_retired(self):
        response = self.client.post(
            "/api/learning/flashcards",
            json={"document_name": "lesson.txt"},
        )
        self.assertEqual(response.status_code, 410)

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
