import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
from app.core.security import create_access_token
from app.routers import auth
from app.services.user_service import user_service

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
        return response.json()

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

    def test_student_profile_rejects_identity_changes_and_keeps_database_identity(self):
        registration = self.register_student(student_id="VERIFIED-1")
        headers = {"Authorization": f"Bearer {registration['access_token']}"}

        rejected = self.client.put(
            "/api/auth/profile",
            headers=headers,
            json={
                "full_name": "Changed Name",
                "student_id": "CHANGED-2",
                "teaching_style": "detailed",
                "course_level": "advanced",
            },
        )

        self.assertEqual(rejected.status_code, 422, rejected.text)
        profile = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["user"]["full_name"], "Test Learner")
        self.assertEqual(profile.json()["user"]["student_id"], "VERIFIED-1")

    def test_student_profile_updates_allowed_preferences_only(self):
        registration = self.register_student(student_id="VERIFIED-1")
        headers = {"Authorization": f"Bearer {registration['access_token']}"}

        response = self.client.put(
            "/api/auth/profile",
            headers=headers,
            json={
                "teaching_style": "detailed",
                "course_level": "advanced",
                "theme_preference": "dark",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()["user"]
        self.assertEqual(user["teaching_style"], "detailed")
        self.assertEqual(user["course_level"], "advanced")
        self.assertEqual(user["theme_preference"], "dark")
        self.assertEqual(user["full_name"], "Test Learner")
        self.assertEqual(user["student_id"], "VERIFIED-1")

        profile = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["user"]["theme_preference"], "dark")

    def test_theme_preference_rejects_unsupported_values(self):
        registration = self.register_student()
        response = self.client.put(
            "/api/auth/profile",
            headers={"Authorization": f"Bearer {registration['access_token']}"},
            json={"theme_preference": "midnight"},
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_student_cannot_list_other_users_through_auth_users_endpoint(self):
        registration = self.register_student()
        response = self.client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {registration['access_token']}"},
        )

        self.assertEqual(response.status_code, 403, response.text)

    def test_password_can_be_changed_with_current_password(self):
        self.register_student()
        login_response = self.login("learner")
        token = login_response.json()["access_token"]

        response = self.client.put(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "test-password",
                "new_password": "new-test-password",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.login("learner").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"identifier": "learner", "password": "new-test-password"},
            ).status_code,
            200,
        )

    def test_google_user_can_set_a_password_then_use_email_login(self):
        user = user_service.get_or_create_google_user(
            email="google.learner@example.test",
            full_name="Google Learner",
            google_id="google-subject-123456",
        )
        token = create_access_token({"sub": user["id"], "username": user["username"]})

        response = self.client.put(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": "google-login-password"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        login = self.client.post(
            "/api/auth/login",
            json={
                "identifier": "google.learner@example.test",
                "password": "google-login-password",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["role"], "student")

    def test_google_user_cannot_use_password_login_before_setting_a_password(self):
        user_service.get_or_create_google_user(
            email="google.learner@example.test",
            full_name="Google Learner",
            google_id="google-subject-123456",
        )

        response = self.client.post(
            "/api/auth/login",
            json={
                "identifier": "google.learner@example.test",
                "password": "not-a-configured-password",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_password_change_requires_current_password_after_initial_setup(self):
        self.register_student()
        token = self.login("learner").json()["access_token"]

        response = self.client.put(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": "new-test-password"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Current password is incorrect", response.json()["detail"])

    @staticmethod
    def google_tokeninfo_response(payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    def valid_google_claims(self, email="google.learner@example.test"):
        return {
            "aud": auth.GOOGLE_OAUTH_CLIENT_ID,
            "iss": "https://accounts.google.com",
            "exp": str(int(time.time()) + 300),
            "email_verified": "true",
            "email": email,
            "name": "Google Learner",
            "sub": "google-subject-123456",
        }

    def google_login(self, email="google.learner@example.test"):
        return self.client.post(
            "/api/auth/google",
            json={"credential": "google-id-token"},
        )

    @patch("app.routers.auth.requests.get")
    def test_google_login_creates_a_database_session_for_verified_student(self, google_get):
        google_get.return_value = self.google_tokeninfo_response(self.valid_google_claims())

        response = self.google_login()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["role"], "student")
        self.assertFalse(response.json()["user"]["password_login_enabled"])
        self.assertTrue(response.json()["user"]["google_linked"])

        session = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
        self.assertEqual(session.status_code, 200, session.text)
        self.assertEqual(session.json()["user"]["role"], "student")

    @patch("app.routers.auth.requests.get")
    def test_google_login_routes_existing_admin_account_as_admin(self, google_get):
        user_service.register_admin(
            full_name="Admin User",
            email="admin@example.test",
            username="admin_user",
            password="admin-password",
        )
        google_get.return_value = self.google_tokeninfo_response(
            self.valid_google_claims("admin@example.test")
        )

        response = self.google_login("admin@example.test")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["role"], "admin")
        self.assertTrue(response.json()["user"]["password_login_enabled"])

    @patch("app.routers.auth.requests.get")
    def test_google_login_rejects_a_token_for_another_client(self, google_get):
        claims = self.valid_google_claims()
        claims["aud"] = "different-client.apps.googleusercontent.com"
        google_get.return_value = self.google_tokeninfo_response(claims)

        response = self.google_login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(user_service.list_users())

    @patch("app.routers.auth.requests.get")
    def test_google_login_rejects_a_mismatched_authorized_party(self, google_get):
        claims = self.valid_google_claims()
        claims["azp"] = "different-client.apps.googleusercontent.com"
        google_get.return_value = self.google_tokeninfo_response(claims)

        response = self.google_login()

        self.assertEqual(response.status_code, 401)

    @patch("app.routers.auth.requests.get")
    def test_google_login_rejects_invalid_tokeninfo_response(self, google_get):
        google_get.return_value = self.google_tokeninfo_response({}, status_code=400)

        response = self.google_login()

        self.assertEqual(response.status_code, 401)

    @patch("app.routers.auth.requests.get")
    def test_google_login_reports_tokeninfo_service_unavailable(self, google_get):
        google_get.return_value = self.google_tokeninfo_response({}, status_code=503)

        response = self.google_login()

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
