import uuid
from typing import Any, Dict

from app.core.database import get_connection


STUDENT_REGISTRATION_SETTING = "student_registration_enabled"
DEFAULT_STUDENT_REGISTRATION_ENABLED = True
SYSTEM_MAINTENANCE_SETTING = "system_maintenance_enabled"
DEFAULT_SYSTEM_MAINTENANCE_ENABLED = False


def get_student_registration_setting() -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT setting_value, updated_by, updated_at
            FROM admin_settings
            WHERE setting_key = ?
            """,
            (STUDENT_REGISTRATION_SETTING,),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "enabled": DEFAULT_STUDENT_REGISTRATION_ENABLED,
                "updated_by": None,
                "updated_at": None,
            }
        return {
            "enabled": row["setting_value"] == "true",
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def set_student_registration_setting(enabled: bool, admin_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT setting_key FROM admin_settings WHERE setting_key = ?",
            (STUDENT_REGISTRATION_SETTING,),
        )
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE admin_settings
                SET setting_value = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE setting_key = ?
                """,
                (str(enabled).lower(), admin_id, STUDENT_REGISTRATION_SETTING),
            )
        else:
            cursor.execute(
                """
                INSERT INTO admin_settings
                    (setting_key, setting_value, updated_by)
                VALUES (?, ?, ?)
                """,
                (STUDENT_REGISTRATION_SETTING, str(enabled).lower(), admin_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_student_registration_setting()


def is_student_registration_enabled() -> bool:
    return bool(get_student_registration_setting()["enabled"])


def get_system_maintenance_setting() -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT setting_value, updated_by, updated_at
            FROM admin_settings
            WHERE setting_key = ?
            """,
            (SYSTEM_MAINTENANCE_SETTING,),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "enabled": DEFAULT_SYSTEM_MAINTENANCE_ENABLED,
                "updated_by": None,
                "updated_at": None,
            }
        return {
            "enabled": row["setting_value"] == "true",
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def set_system_maintenance_setting(enabled: bool, admin_id: str) -> Dict[str, Any]:
    conn = get_connection()
    recovery_announcement = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT setting_value FROM admin_settings WHERE setting_key = ?",
            (SYSTEM_MAINTENANCE_SETTING,),
        )
        row = cursor.fetchone()
        was_enabled = bool(row and row["setting_value"] == "true")

        if row:
            cursor.execute(
                """
                UPDATE admin_settings
                SET setting_value = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE setting_key = ?
                """,
                (str(enabled).lower(), admin_id, SYSTEM_MAINTENANCE_SETTING),
            )
        else:
            cursor.execute(
                """
                INSERT INTO admin_settings
                    (setting_key, setting_value, updated_by)
                VALUES (?, ?, ?)
                """,
                (SYSTEM_MAINTENANCE_SETTING, str(enabled).lower(), admin_id),
            )

        if was_enabled and not enabled:
            announcement_id = f"announcement_{uuid.uuid4().hex[:16]}"
            title = "KeepAI is back online"
            message = (
                "Scheduled maintenance is complete. KeepAI is available again, "
                "and you can continue your studies as usual. Thank you for your patience."
            )
            cursor.execute(
                """
                INSERT INTO announcements (id, title, message, kind, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (announcement_id, title, message, "maintenance", admin_id),
            )
            cursor.execute(
                """
                SELECT id, title, message, kind, created_at
                FROM announcements
                WHERE id = ?
                """,
                (announcement_id,),
            )
            recovery_announcement = dict(cursor.fetchone())
            if recovery_announcement.get("created_at"):
                recovery_announcement["created_at"] = str(
                    recovery_announcement["created_at"]
                )

        cursor.execute(
            """
            SELECT setting_value, updated_by, updated_at
            FROM admin_settings
            WHERE setting_key = ?
            """,
            (SYSTEM_MAINTENANCE_SETTING,),
        )
        setting_row = cursor.fetchone()
        conn.commit()
        setting = {
            "enabled": setting_row["setting_value"] == "true",
            "updated_by": setting_row["updated_by"],
            "updated_at": setting_row["updated_at"],
        }
        return {
            "setting": setting,
            "recovery_announcement": recovery_announcement,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def is_system_maintenance_enabled() -> bool:
    return bool(get_system_maintenance_setting()["enabled"])
