import json
import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from app.routers import health, documents, tutor, learning_tools, auth, workspaces, admin, progress, announcements
from app.core.config import ALLOWED_ORIGINS
from app.services.knowledge_loader import initialize_knowledge_base
from app.services.rag_service import sync_initial_documents_to_db

app = FastAPI(
    title="KeepAI API - Simple & Smart Study Assistant",
    description="Helpful, friendly AI study assistant powered by Google Gemini AI",
    version="1.2.0",
)

# CORS middleware for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(tutor.router, prefix="/api")
app.include_router(learning_tools.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(announcements.router, prefix="/api")

@app.get("/health")
def deployment_health():
    return {"status": "ok"}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist")
FRONTEND_DIR = DIST_DIR if os.path.isdir(DIST_DIR) else BASE_DIR

@app.get("/assets/js/config.js", response_class=PlainTextResponse)
def frontend_config():
    built_config_path = os.path.join(FRONTEND_DIR, "assets", "js", "config.js")
    if FRONTEND_DIR != BASE_DIR and os.path.isfile(built_config_path):
        return FileResponse(
            built_config_path,
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    api_base_url = os.getenv("VITE_API_URL", "").strip().rstrip("/")
    if not api_base_url:
        config_path = os.path.join(BASE_DIR, "assets", "js", "config.js")
        return FileResponse(config_path, media_type="application/javascript")

    app_version = os.getenv("VERCEL_GIT_COMMIT_SHA", "local")[:12]
    config = (
        f"const API_BASE_URL = {json.dumps(api_base_url)};\n"
        f"window.APP_VERSION = {json.dumps(app_version)};\n"
        "window.API_BASE_URL = API_BASE_URL;\n"
        "window.API_URL = API_BASE_URL;\n"
        "window.API_BASE = `${API_BASE_URL}/api`;\n"
        "window.API_IS_DEVELOPMENT = ['localhost', '127.0.0.1'].includes(window.location.hostname);\n"
    )
    return PlainTextResponse(
        config,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )

# PWA root routes
icons_dir = os.path.join(BASE_DIR, "icons")
if os.path.exists(icons_dir):
    app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

frontend_assets_dir = os.path.join(FRONTEND_DIR, "assets")
if os.path.exists(frontend_assets_dir):
    app.mount("/assets", StaticFiles(directory=frontend_assets_dir), name="assets")

@app.get("/manifest.json")
def get_manifest():
    manifest_path = os.path.join(FRONTEND_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    return {"error": "manifest not found"}

@app.get("/sw.js")
def get_sw():
    sw_path = os.path.join(FRONTEND_DIR, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    return {"error": "service worker not found"}

@app.on_event("startup")
async def startup_event():
    """Initialize the training-enhanced knowledge system and sync database"""
    print("🚀 Starting KeepAI Training-Enhanced System...")
    initialize_knowledge_base()
    sync_initial_documents_to_db()
    print("✅ KeepAI Ready!")

@app.get("/")
def root():
    student_path = os.path.join(FRONTEND_DIR, "student_login.html")
    if os.path.exists(student_path):
        return FileResponse(student_path)
    return {
        "message": "KeepAI Simple & Smart Study Assistant", 
        "version": "1.2.0"
    }

@app.get("/admin")
@app.get("/admin_dashboard.html")
def admin_page():
    admin_path = os.path.join(FRONTEND_DIR, "admin_dashboard.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    return {"error": "admin_dashboard.html not found"}

@app.get("/admin_panel.html")
def admin_panel_page():
    admin_panel_path = os.path.join(FRONTEND_DIR, "admin_panel.html")
    if os.path.exists(admin_panel_path):
        return FileResponse(admin_panel_path)
    return {"error": "admin_panel.html not found"}

@app.get("/student")
@app.get("/student_login")
@app.get("/student_login.html")
@app.get("/student_portal.html")
def student_login_page():
    student_path = os.path.join(FRONTEND_DIR, "student_login.html")
    if os.path.exists(student_path):
        return FileResponse(student_path)
    return {"error": "student_login.html not found"}

@app.get("/student_dashboard.html")
def student_dashboard_page():
    dashboard_path = os.path.join(FRONTEND_DIR, "student_dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"error": "student_dashboard.html not found"}
