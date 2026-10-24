import unittest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import ALLOWED_ORIGIN_REGEX


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://keep-ai-app.vercel.app"],
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = TestClient(app)


class AdminLoginCorsTests(unittest.TestCase):
    def test_allows_production_and_stable_vercel_aliases(self):
        origins = (
            "https://keep-ai-app.vercel.app",
            "https://keep-ai-app-nelproghub-bits-projects.vercel.app",
            "https://keep-ai-app-git-main-nelproghub-bits-projects.vercel.app",
        )

        for origin in origins:
            with self.subTest(origin=origin):
                response = client.options(
                    "/api/admin/login",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.headers["access-control-allow-origin"],
                    origin,
                )

    def test_rejects_untrusted_preview_and_external_origins(self):
        origins = (
            "https://keep-ai-random-preview-nelproghub-bits-projects.vercel.app",
            "https://example.invalid",
        )

        for origin in origins:
            with self.subTest(origin=origin):
                response = client.options(
                    "/api/admin/login",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
