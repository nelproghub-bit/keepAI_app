import hashlib
import json
import logging
from urllib.parse import urlsplit
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from pywebpush import WebPushException, webpush

from app.core.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT
from app.core.database import get_connection
from app.core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Push notifications"])

ALLOWED_PUSH_DOMAINS = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, endpoint: str) -> str:
        parsed = urlsplit(endpoint)
        hostname = (parsed.hostname or "").lower()
        trusted_host = any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in ALLOWED_PUSH_DOMAINS
        )
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("Unsupported browser push endpoint.")
        return endpoint


def _vapid_configured() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


@router.get("/push/public-key")
def get_push_public_key():
    return {
        "enabled": _vapid_configured(),
        "public_key": VAPID_PUBLIC_KEY if _vapid_configured() else None,
    }


@router.post("/push/subscription", status_code=status.HTTP_201_CREATED)
def save_push_subscription(
    subscription: PushSubscriptionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not _vapid_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured on this server.",
        )

    subscription_id = hashlib.sha256(subscription.endpoint.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM push_subscriptions WHERE id = ?",
            (subscription_id,),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE push_subscriptions
                SET user_id = ?, endpoint = ?, p256dh = ?, auth_secret = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    current_user["id"],
                    subscription.endpoint,
                    subscription.keys.p256dh,
                    subscription.keys.auth,
                    subscription_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO push_subscriptions
                    (id, user_id, endpoint, p256dh, auth_secret)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    subscription_id,
                    current_user["id"],
                    subscription.endpoint,
                    subscription.keys.p256dh,
                    subscription.keys.auth,
                ),
            )
        conn.commit()
        return {"enabled": True}
    finally:
        conn.close()


@router.delete("/push/subscription")
def remove_push_subscription(
    subscription: PushSubscriptionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    subscription_id = hashlib.sha256(subscription.endpoint.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM push_subscriptions WHERE id = ? AND user_id = ?",
            (subscription_id, current_user["id"]),
        )
        removed = cursor.rowcount > 0
        conn.commit()
        return {"removed": removed}
    finally:
        conn.close()


def send_announcement_push(
    announcement_id: str,
    title: str,
    message: str,
    kind: str,
) -> Dict[str, Any]:
    if not _vapid_configured():
        logger.warning(
            "Push delivery skipped for announcement %s: VAPID keys are not configured.",
            announcement_id,
        )
        return {"configured": False, "sent": 0, "failed": 0}

    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT push_subscriptions.id, push_subscriptions.endpoint,
                       push_subscriptions.p256dh, push_subscriptions.auth_secret,
                       users.role
                FROM push_subscriptions
                JOIN users ON users.id = push_subscriptions.user_id
                """
            )
            subscriptions = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.exception(
            "Could not load push subscriptions for announcement %s.",
            announcement_id,
        )
        return {"configured": True, "sent": 0, "failed": 1}

    stale_ids = []
    sent = 0
    failed = 0
    for item in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": item["endpoint"],
                    "keys": {
                        "p256dh": item["p256dh"],
                        "auth": item["auth_secret"],
                    },
                },
                data=json.dumps(
                    {
                        "title": title[:120],
                        "body": message[:240],
                        "url": (
                            "/admin_dashboard.html#announcements"
                            if item["role"] == "admin"
                            else "/student_dashboard.html?showNotifications=1"
                        ),
                        "tag": f"keepai-announcement-{announcement_id}",
                        "kind": kind,
                    }
                ),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
                ttl=86400,
                timeout=8,
            )
            sent += 1
        except WebPushException as error:
            response = getattr(error, "response", None)
            response_status = getattr(response, "status_code", None)
            if response_status in (404, 410):
                stale_ids.append(item["id"])
                logger.info(
                    "Removing expired push subscription %s (HTTP %s).",
                    item["id"],
                    response_status,
                )
            else:
                failed += 1
                logger.warning(
                    "Push delivery failed for subscription %s (HTTP %s): %s",
                    item["id"],
                    response_status or "unknown",
                    error,
                )
        except Exception:
            failed += 1
            logger.exception("Unexpected push delivery error for subscription %s.", item["id"])

    if stale_ids:
        try:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.executemany(
                    "DELETE FROM push_subscriptions WHERE id = ?",
                    [(subscription_id,) for subscription_id in stale_ids],
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.exception("Could not remove expired push subscriptions.")

    return {"configured": True, "sent": sent, "failed": failed}
