from typing import Any, Dict

from app.core.database import get_connection


STUDENT_REGISTRATION_SETTING = "student_registration_enabled"
DEFAULT_STUDENT_REGISTRATION_ENABLED = True


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
