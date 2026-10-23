from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.database import get_connection


def record_activity(
    user_id: str,
    event_type: str,
    description: str,
    subject: Optional[str] = None,
    duration_seconds: int = 0,
    score_percent: Optional[float] = None,
) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO study_activity
                (id, user_id, event_type, description, subject, duration_seconds, score_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                user_id,
                event_type[:40],
                description[:255],
                subject[:255] if subject else None,
                max(0, duration_seconds),
                score_percent,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_progress(user_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    retention_start = now - timedelta(days=366)
    conn = get_connection()
    try:
        cur = conn.cursor()
        study_seconds = 0
        active_dates = set()
        subject_counts: Dict[str, int] = {}
        recent_activity = []
        study_event_types = {
            "study_time",
            "tutor_question",
            "summary_generated",
            "quiz_generated",
            "quiz_completed",
            "flashcard_mastered",
        }
        offset = 0
        while True:
            cur.execute(
                """
                SELECT event_type, description, subject, duration_seconds, score_percent, created_at
                FROM study_activity
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 500 OFFSET ?
                """,
                (user_id, offset),
            )
            batch = cur.fetchall()
            if not batch:
                break

            stop_reading = False
            for raw_row in batch:
                row = dict(raw_row)
                created_at = _as_utc(row.get("created_at"))
                if not created_at:
                    continue
                if created_at < retention_start:
                    stop_reading = True
                    break

                event_type = row.get("event_type")
                if event_type in study_event_types:
                    active_dates.add(created_at.date())
                if event_type == "study_time" and created_at >= week_start:
                    study_seconds += int(row.get("duration_seconds") or 0)

                subject = (row.get("subject") or "").strip()
                if subject and event_type in study_event_types and event_type != "study_time" and created_at >= now - timedelta(days=30):
                    subject_counts[subject] = subject_counts.get(subject, 0) + 1
                if event_type != "study_time" and len(recent_activity) < 10:
                    recent_activity.append({
                        "type": event_type,
                        "description": row.get("description") or "Study activity",
                        "subject": subject or None,
                        "created_at": created_at.isoformat(),
                        "score_percent": row.get("score_percent"),
                    })
            if stop_reading:
                break
            offset += len(batch)

        cur.execute(
            """
            SELECT AVG(score_percent) AS average_score, COUNT(*) AS quiz_count
            FROM study_activity
            WHERE user_id = ? AND event_type = 'quiz_completed' AND score_percent IS NOT NULL
            """,
            (user_id,),
        )
        score_row = dict(cur.fetchone())
        cur.execute("SELECT COUNT(*) AS workspace_count FROM workspaces WHERE user_id = ?", (user_id,))
        workspace_count = int(dict(cur.fetchone())["workspace_count"])
    finally:
        conn.close()

    streak = 0
    day = now.date()
    if day not in active_dates:
        day -= timedelta(days=1)
    while day in active_dates:
        streak += 1
        day -= timedelta(days=1)

    subjects = [
        {"name": name, "activities": count}
        for name, count in sorted(subject_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    average_score = score_row.get("average_score")
    return {
        "study_streak_days": streak,
        "weekly_study_minutes": study_seconds // 60,
        "active_workspaces": workspace_count,
        "average_quiz_score": round(float(average_score), 1) if average_score is not None else None,
        "completed_quizzes": int(score_row.get("quiz_count") or 0),
        "subject_activity": subjects,
        "recent_activity": recent_activity,
        "last_updated": now.isoformat(),
    }
