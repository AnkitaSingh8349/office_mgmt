# app/main.py
# Full file — corrected router includes so employee API works at /api/employees/*

# ------------------ VERY FIRST: load .env from project root ------------------
import pathlib
from dotenv import load_dotenv, find_dotenv

# FIRST define ROOT
ROOT = pathlib.Path(__file__).resolve().parent.parent

# THEN load .env correctly
env_path = ROOT / ".env"
if not env_path.exists():
    env_path = find_dotenv()

load_dotenv(env_path)
print("Loaded .env from:", env_path)

import os
import pathlib as _pathlib  # avoid shadowing above variable names
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

# Create app immediately (safer for circular imports)
app = FastAPI(title="Office Management System")

# ---------------------------------------------------------------------
# Import routers AFTER app creation (avoids early eval / circular import)
# ---------------------------------------------------------------------
# Auth
from .auth.login import router as auth_router
from .auth.signup import router as signup_router
from .auth.logout import router as logout_router
from .auth.token import router as token_router
from .employees.profile_router import router as admin_profile_router

# Dashboard / pages
from .dashboard_router import router as dashboard_router

# Employees: NOTE - ensure these modules exist
# The employee API router (app/employees/router.py) should define `router` and
# expose endpoints like GET / (list) and GET /admin/{eid} (detail)
from .employees.router import router as employee_router

# If you have a profile router for employees (optional), import it.
# This file is optional — if it doesn't exist adjust accordingly.
try:
    from .employees.profile import router as employees_profile_router
except Exception:
    employees_profile_router = None

# Other app routers
from .leaves.router import router as leaves_router
from .salary.router import router as salary_router
from .tasks.router import router as task_router
from .attendance.router import router as attendance_router

# Birthday API (optional)
try:
    from app.employees.birthday_api_fastapi import router as birthday_router
except Exception:
    birthday_router = None

# Templates
templates = Jinja2Templates(directory="app/templates")

# -------------------- Middleware & static files --------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent

SESSION_SECRET = os.getenv("SESSION_SECRET", "replace_with_a_strong_secret_here")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=False,
    same_site="lax"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    fallback = pathlib.Path("app") / "static"
    if fallback.is_dir():
        app.mount("/static", StaticFiles(directory=str(fallback)), name="static")

UPLOAD_ROOT = BASE_DIR / "static" / "uploads" / "salary_slips"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/salary_slips", StaticFiles(directory=str(UPLOAD_ROOT)), name="salary_slips")

# -------------------- Debug endpoints --------------------
@app.get("/debug/session")
def debug_session(request: Request):
    try:
        return {"session": dict(request.session), "cookies": list(request.cookies.keys())}
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/routes")
def debug_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append({
                "path": route.path,
                "name": getattr(route, "name", "N/A"),
                "methods": sorted(list(getattr(route, "methods", [])))
            })
    return {"routes": routes}

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

# ------------------- INCLUDE YOUR ROUTERS (fixed) -------------------

# Auth & basic
app.include_router(auth_router)
app.include_router(signup_router)
app.include_router(logout_router)
app.include_router(token_router)

# UI / page routers
app.include_router(dashboard_router)
app.include_router(leaves_router)
app.include_router(attendance_router)
app.include_router(salary_router)
app.include_router(task_router)
app.include_router(admin_profile_router)


# Employee API: ensure employee_router is mounted under /api so frontend can call /api/employees/...
# The employee_router file (app/employees/router.py) should define endpoints with path prefix "/employees"
# Example: router = APIRouter(prefix="/employees")
# Mounting it with prefix="/api" gives final path: /api/employees/...
app.include_router(employee_router, prefix="/api")

# Also include the employee router without prefix so server-rendered pages (if any) at /employees/* remain available.
# If employee_router already contains views that should not be exposed twice, you can skip the next line.
try:
    app.include_router(employee_router)  # exposes /employees/...
except Exception:
    # ignore if already included or invalid
    pass

# If you have a separate employees profile router (like /api/profile/employees/*), include it.
if employees_profile_router is not None:
    # If that router already has an internal prefix, you might not need to add another prefix.
    # Many setups expect /api/profile/employees/* so we mount under /api/profile
    app.include_router(employees_profile_router, prefix="/api/profile")

# birthday router under /api (optional)
if birthday_router is not None:
    app.include_router(birthday_router, prefix="/api")

# ------------------- Redirect helper -------------------
@app.get("/leaves/ui/{page}")
def leaves_ui_redirect(page: str, request: Request):
    qs = request.query_params
    url = f"/ui/{page}"
    if qs:
        qstr = "&".join(f"{k}={v}" for k, v in qs.items())
        url = f"{url}?{qstr}"
    return RedirectResponse(url)

# ------------------- STARTUP DEBUG -------------------
@app.on_event("startup")
def _print_routes_and_env():
    print("\n" + "=" * 60)
    print("REGISTERED ROUTES:")
    print("=" * 60)
    for r in app.routes:
        if hasattr(r, "path"):
            methods = sorted(list(getattr(r, "methods", [])))
            print(f"  {r.path:45} {methods}")
    print("=" * 60 + "\n")

    print("ENV CHECK:")
    print("  SMTP_HOST =", os.getenv("SMTP_HOST"))
    print("  SMTP_USER =", os.getenv("SMTP_USER"))
    print("  ADMIN_EMAIL =", os.getenv("ADMIN_EMAIL"))
    print("=" * 60 + "\n")

@app.get("/debug/env")
def debug_env():
    return {
        "SMTP_HOST": os.getenv("SMTP_HOST"),
        "SMTP_USER": os.getenv("SMTP_USER"),
        "FROM_EMAIL": os.getenv("FROM_EMAIL"),
        "ADMIN_EMAIL": os.getenv("ADMIN_EMAIL"),
    }

# simple test email endpoint (uses your existing send_email util)
try:
    from .utils.email_service import send_email
    @app.get("/test-email")
    def test_email():
        to = os.getenv("ADMIN_EMAIL", ".com")
        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        if not smtp_host or not smtp_user:
            return {"error": "SMTP settings not configured. Check .env file."}
        try:
            send_email(to, "Test Email", "Email system working!")
            return {"status": "sent", "to": to}
        except Exception as e:
            return {"error": str(e)}
except Exception:
    # no email util available; skip test-email route
    pass

# Serve the birth_email template for BOTH /birth_email and /birth_email.html (server-rendered)
@app.get("/birth_email", response_class=HTMLResponse)
@app.get("/birth_email.html", response_class=HTMLResponse)
def birth_email_page(request: Request, id: int | None = None, name: str = "", email: str = ""):
    return templates.TemplateResponse(
        "birth_email.html",
        {
            "request": request,
            "id": id,
            "name": name,
            "email": email
        }
    )
