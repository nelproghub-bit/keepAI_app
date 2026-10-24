import tempfile
import unittest
from pathlib import Path

from app.core import config

_test_storage = tempfile.TemporaryDirectory(prefix="keepai-auth-identifiers-")
config.DB_TYPE = "sqlite"
config.DB_PATH = str(Path(_test_storage.name) / "keepai-test.db")

from app.core import database

database.DB_TYPE = "sqlite"
database.DB_PATH = config.DB_PATH
database.init_db()

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import auth

app = FastAPI()
app.include_router(auth.router, prefix="/api")


class StudentLoginIdentifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM student_stats")
            cursor.execute("DELETE FROM users")
            conn.commit()
        finally:
            conn.close()

    def register_student(self, student_id="S1", username="learner", email="learner@example.test"):
        response = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Test Learner",
                "student_id": student_id,
                "username": username,
                "email": email,
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def login(self, identifier):
        return self.client.post(
            "/api/auth/login",
            json={"identifier": identifier, "password": "test-password"},
        )

    def test_login_accepts_username_email_and_short_student_id(self):
        self.register_student(student_id="S1")

        for identifier in ("LEARNER", "LEARNER@EXAMPLE.TEST", "s1"):
            with self.subTest(identifier=identifier):
                response = self.login(identifier)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["user"]["student_id"], "S1")

    def test_duplicate_student_ids_are_not_used_as_ambiguous_login_identifiers(self):
        self.register_student(
            student_id="DUPLICATE-42",
            username="learner_one",
            email="one@example.test",
        )
        self.register_student(
            student_id="duplicate-42",
            username="learner_two",
            email="two@example.test",
        )

        response = self.login("Duplicate-42")

        self.assertEqual(response.status_code, 401)

    def test_login_requires_a_nonempty_identifier(self):
        response = self.client.post(
            "/api/auth/login",
            json={"identifier": "", "password": "test-password"},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
