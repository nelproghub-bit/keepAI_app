import tempfile
import time
import json
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
from app.core.maintenance import MaintenanceModeMiddleware
from app.routers import admin, auth
from app.services.platform_settings import (
    get_system_maintenance_setting,
    get_student_registration_setting,
    set_system_maintenance_setting,
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
app.add_middleware(
    MaintenanceModeMiddleware,
    maintenance_page=Path(__file__).resolve().parents[1] / "maintenance.html",
)
app.dependency_overrides[get_current_admin_user] = lambda: {
    "id": "settings-test-admin",
    "username": "settings-admin",
    "role": "admin",
}

@app.get("/api/maintenance-status")
def maintenance_status():
    return {"maintenance": get_system_maintenance_setting()["enabled"]}


class AdminSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_settings")
            cursor.execute("DELETE FROM announcement_reads")
            cursor.execute("DELETE FROM announcements")
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
        self.assertFalse(response.json()["system_maintenance"]["enabled"])
        self.assertIn("ai_engine", response.json())

    def test_admin_identity_corrections_require_reason_and_are_audited(self):
        student = user_service.register(
            full_name="Original Student",
            student_id="STUDENT-OLD",
            email="identity-correction@example.test",
            username="identity_correction_student",
            password="test-password",
        )

        rejected = self.client.put(
            f"/api/admin/users/{student['id']}",
            json={"full_name": "Corrected Student", "student_id": "STUDENT-NEW"},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)

        corrected = self.client.put(
            f"/api/admin/users/{student['id']}",
            json={
                "full_name": "Corrected Student",
                "student_id": "STUDENT-NEW",
                "identity_correction_reason": "Verified against official student records.",
            },
        )
        self.assertEqual(corrected.status_code, 200, corrected.text)

        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT full_name, student_id FROM users WHERE id = ?",
                (student["id"],),
            )
            updated_user = cursor.fetchone()
            cursor.execute(
                """
                SELECT admin_user_id, target_user_id, action, changes_json, reason
                FROM admin_identity_audit_log
                WHERE target_user_id = ?
                """,
                (student["id"],),
            )
            audit = cursor.fetchone()
        finally:
            conn.close()

        self.assertEqual(updated_user["full_name"], "Corrected Student")
        self.assertEqual(updated_user["student_id"], "STUDENT-NEW")
        self.assertEqual(audit["admin_user_id"], "settings-test-admin")
        self.assertEqual(audit["action"], "student_identity_corrected")
        self.assertEqual(audit["reason"], "Verified against official student records.")
        self.assertEqual(json.loads(audit["changes_json"])["student_id"]["old"], "STUDENT-OLD")
        self.assertEqual(json.loads(audit["changes_json"])["student_id"]["new"], "STUDENT-NEW")

    def test_maintenance_mode_blocks_public_access_but_keeps_admin_available(self):
        set_system_maintenance_setting(True, "settings-test-admin")

        page_response = self.client.get("/student_dashboard.html")
        api_response = self.client.get("/api/auth/registration-status")
        status_response = self.client.get("/api/maintenance-status")
        admin_response = self.client.get("/api/admin/settings")

        self.assertEqual(page_response.status_code, 503)
        self.assertIn("System Maintenance", page_response.text)
        self.assertEqual(api_response.status_code, 503)
        self.assertTrue(api_response.json()["maintenance"])
        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.json()["maintenance"])
        self.assertEqual(admin_response.status_code, 200, admin_response.text)

    @patch("app.routers.admin.send_announcement_push")
    def test_turning_maintenance_off_publishes_recovery_announcement(self, send_push):
        send_push.return_value = {"configured": True, "sent": 2, "failed": 0}
        set_system_maintenance_setting(True, "settings-test-admin")

        response = self.client.put(
            "/api/admin/settings/maintenance",
            json={"enabled": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["system_maintenance"]["enabled"])
        self.assertEqual(payload["recovery_announcement"]["title"], "KeepAI is back online")
        self.assertEqual(payload["recovery_announcement"]["kind"], "maintenance")
        self.assertEqual(payload["recovery_announcement"]["push_delivery"]["sent"], 2)
        send_push.assert_called_once()

        repeated_response = self.client.put(
            "/api/admin/settings/maintenance",
            json={"enabled": False},
        )
        self.assertEqual(repeated_response.status_code, 200, repeated_response.text)
        self.assertIsNone(repeated_response.json()["recovery_announcement"])

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
