"""
KeepAI Security Headers Middleware
==================================
Adds OWASP-recommended HTTP security headers to protect against
clickjacking, MIME-sniffing, XSS, and unauthorized framing.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 1. Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. Prevent framing / clickjacking attacks
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # 3. Enable legacy browser XSS filtering
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 4. Strict referrer policy to prevent leaking paths
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 5. Restrict permissions for sensitive hardware APIs
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), payment=()"
        )

        return response
