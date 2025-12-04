# app/main.py

import os
import pathlib
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Routers (imports must match your files)
from app.auth.login import router as auth_router
from app.auth.signup import router as signup_router
from app.auth.logout import router as logout_router
from app.auth.token import router as token_router

from app.dashboard_router import router as dashboard_router
from app.employees.router import router as employee_router

from app.leaves.router import router as leaves_router
from app.salary.router import router as salary_router
from app.tasks.router import router as task_router

from app.attendance.router import router as attendance_router

# Create FastAPI app
app = FastAPI(title="Office Management System")

# Session secret (use an env var in production)
SESSION_SECRET = os.getenv("SESSION_SECRET", "replace_with_a_strong_secret_here")

# Add SessionMiddleware (server-side session support)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=False,
    same_site="lax"
)

# Static files (package-relative, robust to cwd)
BASE_DIR = pathlib.Path(__file__).resolve().parent
static_dir = BASE_DIR / "static"

if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    # fallback to project-relative path
    fallback = pathlib.Path("app") / "static"
    if fallback.is_dir():
        app.mount("/static", StaticFiles(directory=str(fallback)), name="static")

# ---------------------------------------------------------------------
# ENABLE FILE DOWNLOADS (mount upload folder so files can be served)
# ---------------------------------------------------------------------
# Your salary slips are saved in: app/static/uploads/salary_slips
UPLOAD_ROOT = BASE_DIR / "static" / "uploads" / "salary_slips"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# Serve the uploaded payslips at /salary_slips/<filename>
app.mount(
    "/salary_slips",
    StaticFiles(directory=str(UPLOAD_ROOT)),
    name="salary_slips"
)
# ---------------------------------------------------------------------

# ==================== DEBUG ENDPOINTS (BEFORE ROUTERS) ====================

@app.get("/debug/session")
def debug_session(request: Request):
    """Check current session data"""
    try:
        return {
            "session": dict(request.session),
            "cookies": list(request.cookies.keys())
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/routes")
def debug_routes():
    """List all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append({
                "path": route.path,
                "name": getattr(route, "name", "N/A"),
                "methods": list(getattr(route, "methods", []))
            })
    return {"routes": routes}

# Root endpoint (simple JSON)
@app.get("/")
def home():
    return {
        "message": "Office Management System running!",
        "endpoints": {
            "login": "/login",
            "signup": "/signup",
            "dashboard": "/dashboard",
            "attendance": "/attendance/",
            "employees": "/employees/",
            "leaves": "/leaves",
            "salary": "/salary/",
            "tasks": "/tasks/"
        }
    }

# ==================== INCLUDE ROUTERS ====================
# Keep ordering sensible (auth & API first, then UI routes)

# Auth endpoints (login, signup, logout, token)
app.include_router(auth_router)     # from app.auth.login
app.include_router(signup_router)   # from app.auth.signup
app.include_router(logout_router)   # from app.auth.logout
app.include_router(token_router)    # from app.auth.token

# API routers used by frontend JS
app.include_router(leaves_router)      # registers /api/leaves (router probably has its own prefix)
app.include_router(employee_router)
app.include_router(attendance_router)  # attendance API (me/my, checkin, checkout, etc.)
app.include_router(salary_router)
app.include_router(task_router)

# Dashboard UI pages registered both at root and under /leaves
# - root: /attendance/my, /admin, /ui/my, etc.
# - /leaves: legacy aliases such as /leaves/ui/my and /leaves/apply
app.include_router(dashboard_router)
app.include_router(dashboard_router, prefix="/leaves")

# ==================== PRINT ROUTES ON STARTUP ====================
@app.on_event("startup")
def _print_routes():
    print("\n" + "=" * 60)
    print("REGISTERED ROUTES:")
    print("=" * 60)
    for r in app.routes:
        if hasattr(r, "path"):
            methods = sorted(list(getattr(r, "methods", [])))
            print(f"  {r.path:45} {methods}")
    print("=" * 60 + "\n")
