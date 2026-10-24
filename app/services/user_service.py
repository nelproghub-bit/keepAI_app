import uuid
import json
import sqlite3
from typing import Optional, Dict, Any
from app.core.database import get_connection
from app.core.security import hash_password, verify_password

class UserService:
    """Service handling student registration, authentication, and academic profile state"""

    def __init__(self):
        self._ensure_seed_student()

    def _ensure_seed_student(self):
        """Seed a default academic user if database is empty"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM users")
            row = cur.fetchone()
            if row and row["count"] == 0:
                seed_id = "student_arnel"
                hashed = hash_password("password123")
                cur.execute(
                    """
                    INSERT INTO users (id, username, email, full_name, student_id, password_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (seed_id, "arnel", "arnel.gubi@university.edu", "Arnel Gubi", "BSIT 412", hashed)
                )
                cur.execute(
                    """
                    INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (seed_id, 3, 2, 1, 5, 45, json.dumps(["Database Normalization", "AI Architecture"]))
                )
                conn.commit()
                print("[KeepAI] Seeded default student account (arnel / password123)")
        except Exception as e:
            print(f"Seed student notice: {e}")
        finally:
            conn.close()

    def register(
        self, 
        full_name: str, 
        student_id: str, 
        email: str, 
        username: str, 
        password: str
    ) -> Dict[str, Any]:
        """Register a new student account securely"""
        username_clean = username.strip().lower()
        email_clean = email.strip().lower()
        full_name_clean = full_name.strip()
        student_id_clean = student_id.strip()

        if len(username_clean) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if not email_clean or "@" not in email_clean:
            raise ValueError("A valid university or student email address is required.")
        if not full_name_clean:
            raise ValueError("Full student name is required.")

        conn = get_connection()
        try:
            cur = conn.cursor()
            # Check unique username or email
            cur.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
            if cur.fetchone():
                raise ValueError(f"Username '{username_clean}' is already registered.")

            cur.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
            if cur.fetchone():
                raise ValueError(f"Email '{email_clean}' is already registered.")

            new_id = str(uuid.uuid4())
            pw_hash = hash_password(password)

            cur.execute(
                """
                INSERT INTO users (id, username, email, full_name, student_id, password_hash, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id, username_clean, email_clean, full_name_clean, student_id_clean or "Student", pw_hash, "student")
            )

            cur.execute(
                """
                INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans)
                VALUES (?, 0, 0, 0, 0, 0, '[]')
                """,
                (new_id,)
            )

            conn.commit()

            return {
                "id": new_id,
                "username": username_clean,
                "email": email_clean,
                "full_name": full_name_clean,
                "student_id": student_id_clean or "Student",
                "role": "student"
            }
        finally:
            conn.close()

    def get_or_create_google_user(
        self, 
        email: str, 
        full_name: str, 
        google_id: str, 
        picture: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate or register a student using Google Identity Services credentials"""
        email_clean = email.strip().lower()
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, username, email, full_name, student_id FROM users WHERE email = ?", 
                (email_clean,)
            )
            user = cur.fetchone()
            if user:
                return dict(user)
            
            # Create a new student account linked to Google
            new_id = f"usr_g_{google_id[-8:]}" if len(google_id) >= 8 else str(uuid.uuid4())
            base_username = email_clean.split("@")[0].replace(".", "_")
            username_clean = base_username
            
            cur.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
            if cur.fetchone():
                username_clean = f"{base_username}_{google_id[-4:]}"
                
            pw_hash = hash_password(str(uuid.uuid4()))
            student_id = f"G-{google_id[-6:]}" if len(google_id) >= 6 else "GoogleStudent"
            clean_name = full_name.strip() or base_username
            
            cur.execute(
                """
                INSERT INTO users (id, username, email, full_name, student_id, password_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_id, username_clean, email_clean, clean_name, student_id, pw_hash)
            )
            
            try:
                cur.execute(
                    """
                    INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans)
                    VALUES (?, 0, 0, 0, 0, 0, '[]')
                    """,
                    (new_id,)
                )
            except Exception:
                pass
                
            conn.commit()
            return {
                "id": new_id,
                "username": username_clean,
                "email": email_clean,
                "full_name": clean_name,
                "student_id": student_id
            }
        finally:
            conn.close()

    def authenticate(self, identifier: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a student with username, email, or a unique student ID."""
        ident_clean = identifier.strip().lower()
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, username, email, full_name, student_id, password_hash, role
                FROM users
                WHERE username = ? OR email = ? OR LOWER(student_id) = ?
                """,
                (ident_clean, ident_clean, ident_clean)
            )
            matching_users = cur.fetchall()
            if len(matching_users) != 1:
                return None
            row = matching_users[0]

            user_dict = dict(row)
            if not verify_password(password, user_dict["password_hash"]):
                return None

            # Update last_login
            cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_dict["id"],))
            conn.commit()

            return {
                "id": user_dict["id"],
                "username": user_dict["username"],
                "email": user_dict["email"],
                "full_name": user_dict["full_name"],
                "student_id": user_dict["student_id"],
                "role": user_dict.get("role", "student"),
                "teaching_style": user_dict.get("teaching_style") or "simple",
                "course_level": user_dict.get("course_level") or "intermediate"
            }
        finally:
            conn.close()

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Fetch student academic progress metrics and study plans"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans
                FROM student_stats
                WHERE user_id = ?
                """,
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                data = dict(row)
                try:
                    plans = json.loads(data.get("study_plans") or "[]")
                except Exception:
                    plans = []
                data["study_plans"] = plans
                return data
            return {
                "questions_asked": 0,
                "summaries_generated": 0,
                "quizzes_attempted": 0,
                "questions_tested": 0,
                "study_minutes": 0,
                "study_plans": []
            }
        finally:
            conn.close()

    def update_stats(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update student statistics"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            # Ensure row exists
            cur.execute("SELECT user_id FROM student_stats WHERE user_id = ?", (user_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans) VALUES (?, 0, 0, 0, 0, 0, '[]')",
                    (user_id,)
                )

            fields = []
            values = []
            allowed = ["questions_asked", "summaries_generated", "quizzes_attempted", "questions_tested", "study_minutes"]
            for k in allowed:
                if k in updates:
                    fields.append(f"{k} = ?")
                    values.append(int(updates[k]))
            if "study_plans" in updates:
                fields.append("study_plans = ?")
                values.append(json.dumps(updates["study_plans"]))

            if fields:
                fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(user_id)
                query = f"UPDATE student_stats SET {', '.join(fields)} WHERE user_id = ?"
                cur.execute(query, tuple(values))
                conn.commit()

            return self.get_stats(user_id)
        finally:
            conn.close()

    def increment_stat(self, user_id: str, stat_name: str, delta: int = 1):
        """Increment a specific counter stat"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM student_stats WHERE user_id = ?", (user_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans) VALUES (?, 0, 0, 0, 0, 0, '[]')",
                    (user_id,)
                )
            if stat_name in ["questions_asked", "summaries_generated", "quizzes_attempted", "questions_tested", "study_minutes"]:
                cur.execute(
                    f"UPDATE student_stats SET {stat_name} = {stat_name} + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (delta, user_id)
                )
                conn.commit()
        finally:
            conn.close()

    def update_profile(
        self, 
        user_id: str, 
        full_name: Optional[str] = None, 
        student_id: Optional[str] = None,
        teaching_style: Optional[str] = None,
        course_level: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update student profile and academic study preferences"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            fields = []
            values = []
            if full_name:
                fields.append("full_name = ?")
                values.append(full_name.strip())
            if student_id:
                fields.append("student_id = ?")
                values.append(student_id.strip())
            if teaching_style:
                fields.append("teaching_style = ?")
                values.append(teaching_style.strip())
            if course_level:
                fields.append("course_level = ?")
                values.append(course_level.strip())

            if fields:
                values.append(user_id)
                cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(values))
                conn.commit()
            
            cur.execute("SELECT id, username, email, full_name, student_id, teaching_style, course_level FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def list_users(self, limit: int = 50) -> list:
        """List registered students for admin overview"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, username, email, full_name, student_id, role, created_at, last_login FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def get_admin_count(self) -> int:
        """Count how many admin accounts exist in the database"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin'")
            row = cur.fetchone()
            return int(row["count"]) if row else 0
        except Exception as e:
            print(f"Error checking admin count: {e}")
            return 0
        finally:
            conn.close()

    def register_admin(
        self,
        full_name: str,
        email: str,
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """Register the single allowed admin account. Rejects if an admin already exists."""
        admin_count = self.get_admin_count()
        if admin_count >= 1:
            raise ValueError("Admin registration is closed. Only one admin account is allowed in this system.")

        username_clean = username.strip().lower()
        email_clean = email.strip().lower()
        full_name_clean = full_name.strip()

        if len(username_clean) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if not email_clean or "@" not in email_clean:
            raise ValueError("A valid email address is required.")
        if not full_name_clean:
            raise ValueError("Administrator full name is required.")

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
            if cur.fetchone():
                raise ValueError(f"Username '{username_clean}' is already registered.")

            cur.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
            if cur.fetchone():
                raise ValueError(f"Email '{email_clean}' is already registered.")

            new_id = f"admin_{uuid.uuid4().hex[:12]}"
            pw_hash = hash_password(password)

            cur.execute(
                """
                INSERT INTO users (id, username, email, full_name, student_id, password_hash, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id, username_clean, email_clean, full_name_clean, "Administrator", pw_hash, "admin")
            )

            try:
                cur.execute(
                    """
                    INSERT INTO student_stats (user_id, questions_asked, summaries_generated, quizzes_attempted, questions_tested, study_minutes, study_plans)
                    VALUES (?, 0, 0, 0, 0, 0, '[]')
                    """,
                    (new_id,)
                )
            except Exception:
                pass

            conn.commit()

            return {
                "id": new_id,
                "username": username_clean,
                "email": email_clean,
                "full_name": full_name_clean,
                "student_id": "Administrator",
                "role": "admin"
            }
        finally:
            conn.close()

    def authenticate_admin(self, identifier: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate an administrator with username or email and verify admin role"""
        user = self.authenticate(identifier, password)
        if not user:
            return None
        if user.get("role") != "admin":
            return None
        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a student user and their associated records"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id = ? AND role != 'admin'", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_students_with_stats(self) -> list:
        """List all students with their activity stats for admin view"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.username, u.email, u.full_name, u.student_id, u.role, u.created_at, u.last_login,
                       COALESCE(s.questions_asked, 0) as questions_asked,
                       COALESCE(s.quizzes_attempted, 0) as quizzes_attempted,
                       COALESCE(s.summaries_generated, 0) as summaries_generated,
                       COALESCE(s.study_minutes, 0) as study_minutes
                FROM users u
                LEFT JOIN student_stats s ON u.id = s.user_id
                WHERE u.role != 'admin'
                ORDER BY u.created_at DESC
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"Error listing students: {e}")
            return []
        finally:
            conn.close()

user_service = UserService()
