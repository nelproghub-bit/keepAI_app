import base64
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pydantic import ValidationError

from app.routers import push
from app.routers.push import PushSubscriptionRequest
from app.core.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY


class FakeCursor:
    def __init__(self, existing=None, rowcount=1):
        self.existing = existing
        self.rowcount = rowcount
        self.calls = []

    def execute(self, query, args=None):
        self.calls.append((query, args))

    def fetchone(self):
        return self.existing


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class PushSubscriptionValidationTests(unittest.TestCase):
    def test_configured_vapid_key_pair_is_valid_and_publicly_advertised(self):
        self.assertTrue(VAPID_PRIVATE_KEY)
        self.assertTrue(VAPID_PUBLIC_KEY)
        vapid = Vapid.from_string(VAPID_PRIVATE_KEY)
        public_bytes = vapid.public_key.public_bytes(
            encoding=Encoding.X962,
            format=PublicFormat.UncompressedPoint,
        )
        encoded_public = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
        self.assertEqual(encoded_public, VAPID_PUBLIC_KEY)
        self.assertEqual(push.get_push_public_key(), {
            "enabled": True,
            "public_key": VAPID_PUBLIC_KEY,
        })

    def test_accepts_supported_push_service_endpoints(self):
        endpoints = (
            "https://fcm.googleapis.com/fcm/send/example",
            "https://updates.push.services.mozilla.com/wpush/v2/example",
            "https://wns2.notify.windows.com/w/?token=example",
            "https://web.push.apple.com/QWxhZGRpbjpvcGVuIHNlc2FtZQ",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                subscription = PushSubscriptionRequest.model_validate(
                    {
                        "endpoint": endpoint,
                        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
                    }
                )
                self.assertEqual(subscription.endpoint, endpoint)

    def test_rejects_untrusted_or_insecure_endpoints(self):
        endpoints = (
            "http://fcm.googleapis.com/fcm/send/example",
            "https://localhost/private",
            "https://127.0.0.1/private",
            "https://example.com/push",
            "https://fcm.googleapis.com:8443/fcm/send/example",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValidationError):
                    PushSubscriptionRequest.model_validate(
                        {
                            "endpoint": endpoint,
                            "keys": {"p256dh": "public-key", "auth": "auth-secret"},
                        }
                    )

    def test_saves_a_subscription_for_the_authenticated_user(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        subscription = PushSubscriptionRequest.model_validate(
            {
                "endpoint": "https://fcm.googleapis.com/fcm/send/example",
                "keys": {"p256dh": "public-key", "auth": "auth-secret"},
            }
        )
        with (
            patch.object(push, "_vapid_configured", return_value=True),
            patch.object(push, "get_connection", return_value=connection),
        ):
            result = push.save_push_subscription(subscription, {"id": "student-1"})

        self.assertEqual(result, {"enabled": True})
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)
        self.assertIn("INSERT INTO push_subscriptions", cursor.calls[-1][0])
        self.assertEqual(cursor.calls[-1][1][1], "student-1")

    def test_removes_only_the_authenticated_users_subscription(self):
        cursor = FakeCursor(rowcount=1)
        connection = FakeConnection(cursor)
        subscription = PushSubscriptionRequest.model_validate(
            {
                "endpoint": "https://fcm.googleapis.com/fcm/send/example",
                "keys": {"p256dh": "public-key", "auth": "auth-secret"},
            }
        )
        with patch.object(push, "get_connection", return_value=connection):
            result = push.remove_push_subscription(subscription, {"id": "student-1"})

        self.assertEqual(result, {"removed": True})
        self.assertIn("AND user_id = ?", cursor.calls[-1][0])
        self.assertEqual(cursor.calls[-1][1][1], "student-1")
        self.assertTrue(connection.committed)


if __name__ == "__main__":
    unittest.main()
