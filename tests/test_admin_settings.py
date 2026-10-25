import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core import config

_test_storage = tempfile.TemporaryDirectory(prefix="keepai-admin-settings-")
config.DB_TYPE = "sqlite"
config.DB_PATH = str(Path(_test_storage.name) / "keepai-test.db")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core import database
from app.core.security import get_current_admin_user
from app.routers import admin, auth
from app.services.platform_settings import (
    get_student_registration_setting,
    set_student_registration_setting,
)
from app.services.user_service import (
    StudentRegistrationDisabledError,
    user_service,
)

database.DB_TYPE = "sqlite"
database.DB_PATH = config.DB_PATH
database.init_db()

app = FastAPI()
app.include_router(admin.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.dependency_overrides[get_current_admin_user] = lambda: {
    "id": "settings-test-admin",
    "username": "settings-admin",
    "role": "admin",
}


class AdminSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_settings")
            conn.commit()
        finally:
            conn.close()

    def test_registration_is_enabled_by_default(self):
        self.assertTrue(get_student_registration_setting()["enabled"])

    def test_admin_can_persist_student_registration_setting(self):
        response = self.client.put(
            "/api/admin/settings/student-registration",
            json={"enabled": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["student_registration"]["enabled"])
        self.assertFalse(get_student_registration_setting()["enabled"])

    def test_admin_settings_api_loads_platform_settings(self):
        response = self.client.get("/api/admin/settings")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["student_registration"]["enabled"])
        self.assertIn("ai_engine", response.json())

    def test_disabled_registration_rejects_password_signup(self):
        set_student_registration_setting(False, "settings-test-admin")

        response = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "New Student",
                "student_id": "NEW-1",
                "email": "new-student@example.test",
                "username": "new_student",
                "password": "test-password",
            },
        )

        self.assertEqual(response.status_code, 403, response.text)

    def test_disabled_registration_still_allows_existing_google_accounts(self):
        existing_user = user_service.get_or_create_google_user(
            email="existing-google@example.test",
            full_name="Existing Student",
            google_id="google-existing-123",
        )
        set_student_registration_setting(False, "settings-test-admin")

        authenticated_user = user_service.get_or_create_google_user(
            email="existing-google@example.test",
            full_name="Existing Student",
            google_id="google-existing-123",
            allow_create=False,
        )

        self.assertEqual(authenticated_user["id"], existing_user["id"])

    def test_disabled_registration_rejects_new_google_accounts(self):
        with self.assertRaises(StudentRegistrationDisabledError):
            user_service.get_or_create_google_user(
                email="new-google@example.test",
                full_name="New Google Student",
                google_id="google-new-123",
                allow_create=False,
            )

    @patch("app.routers.auth.requests.get")
    def test_disabled_registration_rejects_new_google_signups(self, google_verify):
        google_verify.return_value = Mock(
            status_code=200,
            json=lambda: {
                "aud": auth.GOOGLE_OAUTH_CLIENT_ID,
                "azp": auth.GOOGLE_OAUTH_CLIENT_ID,
                "iss": "https://accounts.google.com",
                "exp": int(time.time()) + 300,
                "email_verified": True,
                "email": "paused-google@example.test",
                "sub": "paused-google-123",
                "name": "Paused Google Student",
            },
        )
        set_student_registration_setting(False, "settings-test-admin")

        response = self.client.post(
            "/api/auth/google",
            json={"credential": "verified-google-credential"},
        )

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
