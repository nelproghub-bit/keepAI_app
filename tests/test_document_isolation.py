import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config

_test_storage = tempfile.TemporaryDirectory(prefix="keepai-document-isolation-")
_storage_path = Path(_test_storage.name)
config.DB_TYPE = "sqlite"
config.DB_PATH = str(_storage_path / "keepai-test.db")
config.CHROMA_PATH = str(_storage_path / "chroma")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.database import get_connection, init_db
from app.core.security import create_access_token
from app.routers import admin, documents, learning_tools, tutor, workspaces
from app.services import rag_service


app = FastAPI()
app.include_router(documents.router, prefix="/api")
app.include_router(tutor.router, prefix="/api")
app.include_router(learning_tools.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


class DocumentIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.student_a_token = create_access_token({"sub": "student-a"})
        cls.student_b_token = create_access_token({"sub": "student-b"})
        cls.admin_token = create_access_token({"sub": "admin-user"})

    def setUp(self):
        rag_service._document_store.clear()
        rag_service._files_meta_store.clear()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            for table in (
                "workspace_documents",
                "documents",
                "rag_documents",
                "workspaces",
                "study_activity",
                "student_stats",
                "users",
            ):
                cursor.execute(f"DELETE FROM {table}")
            for user_id, username, role in (
                ("student-a", "student_a", "student"),
                ("student-b", "student_b", "student"),
                ("admin-user", "admin", "admin"),
            ):
                cursor.execute(
                    """
                    INSERT INTO users (id, username, email, full_name, student_id, password_hash, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        f"{username}@example.test",
                        username,
                        "TEST",
                        "unused",
                        role,
                    ),
                )
                cursor.execute("INSERT INTO student_stats (user_id) VALUES (?)", (user_id,))

            for user_id, doc_id, content in (
                ("student-a", "doc-a", "A_ONLY_MATERIAL"),
                ("student-b", "doc-b", "B_ONLY_MATERIAL"),
            ):
                cursor.execute(
                    """
                    INSERT INTO documents
                        (id, user_id, filename, chunks_indexed, char_count, page_count, size_bytes)
                    VALUES (?, ?, ?, 1, ?, 1, 64)
                    """,
                    (doc_id, user_id, f"{user_id}.txt", len(content)),
                )
                chunks = [{
                    "id": f"{doc_id}_0",
                    "file_id": doc_id,
                    "filename": f"{user_id}.txt",
                    "user_id": user_id,
                    "text": content,
                    "chunk_index": 0,
                    "embedding": None,
                }]
                metadata = {
                    "file_id": doc_id,
                    "filename": f"{user_id}.txt",
                    "chunks_count": 1,
                    "char_count": len(content),
                    "full_text": content,
                    "outline": [],
                }
                cursor.execute(
                    """
                    INSERT INTO rag_documents (id, user_id, filename, chunks_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc_id, user_id, f"{user_id}.txt", json.dumps(chunks), json.dumps(metadata)),
                )
            for user_id, workspace_id, doc_id in (
                ("student-a", "workspace-a", "doc-a"),
                ("student-b", "workspace-b", "doc-b"),
            ):
                cursor.execute(
                    """
                    INSERT INTO workspaces (id, user_id, name, category)
                    VALUES (?, ?, 'Shared display name', 'Same category')
                    """,
                    (workspace_id, user_id),
                )
                cursor.execute(
                    """
                    INSERT INTO workspace_documents (id, workspace_id, document_id)
                    VALUES (?, ?, ?)
                    """,
                    (f"link-{user_id}", workspace_id, doc_id),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_documents_requires_authentication_and_lists_only_owner(self):
        self.assertEqual(self.client.get("/api/documents").status_code, 401)

        response_a = self.client.get(
            "/api/documents", headers=self.headers(self.student_a_token)
        )
        response_b = self.client.get(
            "/api/documents", headers=self.headers(self.student_b_token)
        )

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        files_a = response_a.json()["files"]
        files_b = response_b.json()["files"]
        self.assertEqual([f["file_id"] for f in files_a], ["doc-a"])
        self.assertEqual([f["file_id"] for f in files_b], ["doc-b"])
        self.assertEqual(files_a[0]["workspace_id"], "workspace-a")
        self.assertEqual(files_b[0]["workspace_id"], "workspace-b")

        workspaces_a = self.client.get(
            "/api/workspaces", headers=self.headers(self.student_a_token)
        ).json()["workspaces"]
        workspaces_b = self.client.get(
            "/api/workspaces", headers=self.headers(self.student_b_token)
        ).json()["workspaces"]
        self.assertEqual([(w["id"], w["document_count"]) for w in workspaces_a], [("workspace-a", 1)])
        self.assertEqual([(w["id"], w["document_count"]) for w in workspaces_b], [("workspace-b", 1)])

    def test_upload_owner_comes_from_authenticated_session(self):
        with patch.object(rag_service.ai_service, "embed_many", return_value=[]):
            response = self.client.post(
                "/api/documents/upload",
                headers=self.headers(self.student_a_token),
                data={"user_id": "student-b"},
                files={"file": ("new.txt", b"New private material for student A.")},
            )

        self.assertEqual(response.status_code, 200, response.text)
        uploaded_id = response.json()["file_id"]
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM documents WHERE id = ?", (uploaded_id,))
            self.assertEqual(cursor.fetchone()["user_id"], "student-a")
        finally:
            conn.close()

        listed_by_b = self.client.get(
            "/api/documents", headers=self.headers(self.student_b_token)
        ).json()["files"]
        self.assertNotIn(uploaded_id, [item["file_id"] for item in listed_by_b])

    def test_foreign_document_id_cannot_be_asked_or_deleted(self):
        ask_response = self.client.post(
            "/api/tutor/ask",
            headers=self.headers(self.student_b_token),
            json={
                "question": "Summarize this",
                "document_id": "doc-a",
                "user_id": "student-a",
            },
        )
        delete_response = self.client.delete(
            "/api/documents/doc-a?user_id=student-a",
            headers=self.headers(self.student_b_token),
        )

        self.assertEqual(ask_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM documents WHERE id = ?", ("doc-a",))
            self.assertEqual(cursor.fetchone()["user_id"], "student-a")
        finally:
            conn.close()

    def test_tutor_uses_only_the_selected_owners_content(self):
        prompts = []

        def fake_generate(prompt, **kwargs):
            prompts.append(prompt)
            return "private tutor response"

        with patch.object(tutor, "generate", side_effect=fake_generate):
            response = self.client.post(
                "/api/tutor/ask",
                headers=self.headers(self.student_b_token),
                json={"question": "Explain this lesson", "document_id": "doc-b"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(any("B_ONLY_MATERIAL" in prompt for prompt in prompts))
        self.assertFalse(any("A_ONLY_MATERIAL" in prompt for prompt in prompts))

    def test_learning_tools_use_only_the_authenticated_students_files(self):
        prompts = []

        def fake_generate(prompt, **kwargs):
            prompts.append(prompt)
            return "private summary"

        response = self.client.post(
            "/api/learning/summary",
            headers=self.headers(self.student_b_token),
            json={"topic": "summary", "document_name": "student-a.txt"},
        )
        self.assertEqual(response.status_code, 404)

        with patch.object(learning_tools, "generate", side_effect=fake_generate):
            owned_response = self.client.post(
                "/api/learning/summary",
                headers=self.headers(self.student_b_token),
                json={"topic": "summary", "document_name": "student-b.txt"},
            )

        self.assertEqual(owned_response.status_code, 200, owned_response.text)
        self.assertTrue(any("B_ONLY_MATERIAL" in prompt for prompt in prompts))
        self.assertFalse(any("A_ONLY_MATERIAL" in prompt for prompt in prompts))

    def test_admin_document_listing_is_not_available_to_students(self):
        response = self.client.get(
            "/api/admin/documents", headers=self.headers(self.student_a_token)
        )
        self.assertEqual(response.status_code, 403)

    @classmethod
    def tearDownClass(cls):
        _test_storage.cleanup()


if __name__ == "__main__":
    unittest.main()
