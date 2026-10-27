"""
KeepAI Authentication Rate Limiting & Brute-Force Protection Module
==================================================================
Protects student and administrator login endpoints against credential stuffing,
brute-force attacks, and denial-of-service abuse using exponential backoff
and lockout mechanisms.
"""

import time
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status


class BruteForceProtector:
    """
    In-memory tracker for failed login attempts by identifier and client IP.
    Applies temporary account lockout after repeated failed attempts.
    """

    def __init__(self, max_failures: int = 5, lockout_duration_secs: int = 900):
        self.max_failures = max_failures
        self.lockout_duration_secs = lockout_duration_secs
        # Maps key -> {"failures": int, "lockout_until": float, "last_attempt": float}
        self._attempts: Dict[str, Dict[str, Any]] = {}

    def _cleanup_old_entries(self):
        """Prune records older than 1 hour to prevent memory bloat"""
        now = time.time()
        expired = [
            k for k, v in self._attempts.items()
            if now - v.get("last_attempt", 0) > 3600 and v.get("lockout_until", 0) < now
        ]
        for k in expired:
            self._attempts.pop(k, None)

    def _get_key(self, identifier: str, client_ip: str) -> str:
        ident_clean = (identifier or "").strip().lower()
        ip_clean = (client_ip or "unknown").strip()
        return f"{ident_clean}::{ip_clean}"

    def check_lockout(self, identifier: str, client_ip: str) -> Tuple[bool, int]:
        """
        Check if the identifier/IP combination is currently locked out.
        Returns (is_locked, remaining_seconds).
        """
        self._cleanup_old_entries()
        key = self._get_key(identifier, client_ip)
        record = self._attempts.get(key)
        if not record:
            return False, 0

        now = time.time()
        lockout_until = record.get("lockout_until", 0)
        if lockout_until > now:
            remaining = int(lockout_until - now)
            return True, max(remaining, 1)

        return False, 0

    def record_failure(self, identifier: str, client_ip: str) -> Tuple[int, bool, int]:
        """
        Record a failed authentication attempt.
        Returns (failure_count, is_now_locked, remaining_lockout_seconds).
        """
        self._cleanup_old_entries()
        key = self._get_key(identifier, client_ip)
        now = time.time()

        if key not in self._attempts:
            self._attempts[key] = {
                "failures": 1,
                "lockout_until": 0,
                "last_attempt": now,
            }
            return 1, False, 0

        record = self._attempts[key]
        record["last_attempt"] = now
        record["failures"] += 1

        if record["failures"] >= self.max_failures:
            record["lockout_until"] = now + self.lockout_duration_secs
            remaining = self.lockout_duration_secs
            return record["failures"], True, remaining

        return record["failures"], False, 0

    def record_success(self, identifier: str, client_ip: str):
        """Clear failed attempts upon successful authentication."""
        key = self._get_key(identifier, client_ip)
        self._attempts.pop(key, None)


# Global protector instances
login_protector = BruteForceProtector(max_failures=5, lockout_duration_secs=900)  # 15 mins
admin_login_protector = BruteForceProtector(max_failures=5, lockout_duration_secs=900)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, taking proxy headers into account safely."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the first untrusted client IP
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def enforce_login_rate_limit(request: Request, identifier: str, is_admin: bool = False):
    """Dependency helper to reject requests from locked-out clients."""
    client_ip = get_client_ip(request)
    protector = admin_login_protector if is_admin else login_protector
    is_locked, remaining = protector.check_lockout(identifier, client_ip)
    if is_locked:
        minutes = max(1, (remaining + 59) // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many consecutive failed login attempts. Account temporarily locked for security. Please try again in {minutes} minute(s).",
            headers={"Retry-After": str(remaining)},
        )
