import tempfile
import unittest
from pathlib import Path

from app.core import config

_test_storage = tempfile.TemporaryDirectory(prefix="keepai-announcements-")
config.DB_TYPE = "sqlite"
config.DB_PATH = str(Path(_test_storage.name) / "keepai-test.db")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import database
from app.core.security import get_current_user
from app.routers import announcements

database.DB_TYPE = "sqlite"
database.DB_PATH = config.DB_PATH
database.init_db()

_active_user = {"id": "announcement-test-user"}
app = FastAPI()
app.include_router(announcements.router, prefix="/api")
app.dependency_overrides[get_current_user] = lambda: _active_user


class AnnouncementDismissalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        _active_user["id"] = "announcement-test-user"
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM announcement_dismissals")
            cursor.execute("DELETE FROM announcement_reads")
            cursor.execute("DELETE FROM announcements")
            cursor.execute(
                """
                INSERT INTO announcements (id, title, message, kind, is_active, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("announcement-1", "Update one", "First notification", "info", True, "admin"),
            )
            cursor.execute(
                """
                INSERT INTO announcements (id, title, message, kind, is_active, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("announcement-2", "Update two", "Second notification", "maintenance", True, "admin"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_clear_hides_notifications_only_for_the_current_user(self):
        cleared = self.client.delete("/api/announcements")

        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["dismissed_count"], 2)
        self.assertEqual(self.client.get("/api/announcements").json()["announcements"], [])

        _active_user["id"] = "another-student"
        other_user_notifications = self.client.get("/api/announcements")
        self.assertEqual(other_user_notifications.status_code, 200, other_user_notifications.text)
        self.assertEqual(len(other_user_notifications.json()["announcements"]), 2)

    def test_clear_all_is_idempotent(self):
        first_clear = self.client.delete("/api/announcements")
        second_clear = self.client.delete("/api/announcements")

        self.assertEqual(first_clear.json()["dismissed_count"], 2)
        self.assertEqual(second_clear.json()["dismissed_count"], 0)


if __name__ == "__main__":
    unittest.main()
