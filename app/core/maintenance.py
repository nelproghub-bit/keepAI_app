import logging
from pathlib import Path
from typing import Union

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.services.platform_settings import is_system_maintenance_enabled

logger = logging.getLogger(__name__)

PUBLIC_PAGE_PATHS = {
    "/",
    "/index.html",
    "/student",
    "/student_login",
    "/student_login.html",
    "/student_portal.html",
    "/student_dashboard.html",
    "/maintenance.html",
}
ADMIN_API_PREFIX = "/api/admin"
MAINTENANCE_STATUS_PATH = "/api/maintenance-status"
HEALTH_PATHS = {"/health", "/api/health"}

# Auth endpoints that must remain accessible during maintenance so that
# administrators can verify their session, sign in to the admin portal,
# and update their profile/password without being blocked.
ADMIN_AUTH_PASSTHROUGH_PATHS = {
    "/api/auth/me",
    "/api/auth/profile",
    "/api/auth/password",
    "/api/auth/login",
    "/api/auth/token",
}


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, maintenance_page: Union[str, Path]):
        super().__init__(app)
        self.maintenance_page = maintenance_page

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        is_public_page = path in PUBLIC_PAGE_PATHS
        is_api_request = path.startswith("/api/")
        if (
            (not is_public_page and not is_api_request)
            or path == MAINTENANCE_STATUS_PATH
            or path in HEALTH_PATHS
            or path in ADMIN_AUTH_PASSTHROUGH_PATHS
            or path == ADMIN_API_PREFIX
            or path.startswith(f"{ADMIN_API_PREFIX}/")
        ):
            return await call_next(request)

        try:
            maintenance_enabled = is_system_maintenance_enabled()
        except Exception:
            logger.exception("Could not read the system maintenance setting for %s", path)
            if path in PUBLIC_PAGE_PATHS:
                return FileResponse(
                    self.maintenance_page,
                    status_code=503,
                    headers={"Retry-After": "60", "Cache-Control": "no-store"},
                )
            return JSONResponse(
                status_code=503,
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
                content={
                    "detail": "KeepAI is temporarily unavailable. Please try again shortly.",
                    "maintenance": True,
                },
            )

        if not maintenance_enabled:
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse(
                status_code=503,
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
                content={
                    "detail": "KeepAI is temporarily unavailable while we complete scheduled maintenance.",
                    "maintenance": True,
                },
            )

        if path in PUBLIC_PAGE_PATHS:
            return FileResponse(
                self.maintenance_page,
                status_code=503,
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
            )

        return await call_next(request)
