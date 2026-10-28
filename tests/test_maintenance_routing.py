import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config

_test_storage = tempfile.TemporaryDirectory(prefix="keepai-maintenance-routing-")
config.DB_TYPE = "sqlite"
config.DB_PATH = str(Path(_test_storage.name) / "keepai-test.db")

from fastapi.testclient import TestClient
from app.core import database
from app.core.maintenance import MaintenanceModeMiddleware
from app import main as main_module
from app.main import app

database.DB_TYPE = "sqlite"
database.DB_PATH = config.DB_PATH
main_module.FRONTEND_DIR = str(Path(__file__).resolve().parents[1])

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for middleware in app.user_middleware:
    if middleware.cls is MaintenanceModeMiddleware:
        middleware.kwargs["maintenance_page"] = PROJECT_ROOT / "maintenance.html"

client = TestClient(app)


class MaintenanceRoutingTests(unittest.TestCase):
    def test_direct_page_route_returns_html_when_maintenance_is_disabled(self):
        with patch("app.core.maintenance.is_system_maintenance_enabled", return_value=False):
            response = client.get("/maintenance.html")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("A little maintenance. A better study space.", response.text)
        self.assertIn(
            "KeepAI is temporarily offline while we make a few improvements.",
            response.text,
        )

    def test_page_returns_a_branded_503_when_maintenance_is_enabled(self):
        with patch("app.core.maintenance.is_system_maintenance_enabled", return_value=True):
            response = client.get("/maintenance.html")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("A little maintenance. A better study space.", response.text)
        self.assertNotIn('"detail":"Not Found"', response.text)

    def test_database_errors_return_generic_503_responses(self):
        with patch(
            "app.core.maintenance.is_system_maintenance_enabled",
            side_effect=RuntimeError("private database connection detail"),
        ):
            page_response = client.get("/student_dashboard.html")
            api_response = client.get("/api/auth/registration-status")

        with patch(
            "app.main.get_system_maintenance_setting",
            side_effect=RuntimeError("private database connection detail"),
        ):
            status_response = client.get("/api/maintenance-status")

        for response in (page_response, api_response, status_response):
            with self.subTest(path=response.url.path):
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("private database connection detail", response.text)
                self.assertNotIn("Traceback", response.text)

        self.assertIn("A little maintenance. A better study space.", page_response.text)
        self.assertIn("availability could not be verified", status_response.text)

    def test_maintenance_page_assets_remain_accessible_during_maintenance(self):
        with patch("app.core.maintenance.is_system_maintenance_enabled", return_value=True):
            response = client.get("/assets/js/config.js")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("javascript", response.headers["content-type"])

    def test_vercel_routes_direct_maintenance_and_assets_before_fallback(self):
        config_path = PROJECT_ROOT / "vercel.json"
        vercel_config = json.loads(config_path.read_text(encoding="utf-8"))
        routes = vercel_config["routes"]
        maintenance_route = next(
            index for index, route in enumerate(routes)
            if route["src"] == r"/maintenance\.html"
        )
        assets_route = next(
            index for index, route in enumerate(routes)
            if route["src"] == "/assets/(.*)"
        )
        fallback_route = next(
            index for index, route in enumerate(routes)
            if route["src"] == "/(.*)"
        )

        self.assertLess(maintenance_route, fallback_route)
        self.assertLess(assets_route, fallback_route)
        self.assertEqual(routes[maintenance_route]["dest"], "/maintenance.html")
        self.assertEqual(routes[assets_route]["dest"], "/assets/$1")


if __name__ == "__main__":
    unittest.main()
