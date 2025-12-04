# app/auth/signup.py

import os
import json
from fastapi import APIRouter, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app.database import get_db

# ----------------------------------------------------
# Config
# ----------------------------------------------------
DEBUG_SIGNUP = os.getenv("DEBUG_SIGNUP", "1") in ("1", "true", "True")

# ----------------------------------------------------
# Router & templates
# ----------------------------------------------------
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------- SHOW SIGNUP FORM -----------------------
@router.get("/signup", response_class=HTMLResponse)
@router.get("/auth/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


# ---------------------- SIGNUP POST -----------------------
@router.post("/signup")
@router.post("/auth/signup")
def signup_post(
    request: Request,
    # Form params (populated for normal form posts)
    name: str = Form(None),
    email: str = Form(None),
    phone: str = Form(""),
    password: str = Form(None),
    role: str = Form("employee"),  # <-- accept role from frontend (default employee)
    db: Session = Depends(get_db)
):
    """
    Accepts both form-encoded POST (Form params above) and
    AJAX JSON POSTs. For JSON, we parse request body manually
    and prefer JSON values if provided.
    """

    # Detect JSON content and try to parse it (AJAX path)
    content_type = (request.headers.get("content-type") or "").lower()
    is_json = content_type.startswith("application/json")

    if is_json:
        # Try FastAPI Request.json() if available; fall back to reading body bytes
        parsed = {}
        try:
            if hasattr(request, "json"):
                # In many sync handlers request.json() is not awaitable - try anyway
                parsed = request.json() or {}
            else:
                parsed = {}
        except Exception:
            # fallback: read raw body from scope if available
            try:
                body_bytes = request.scope.get("body")
                if body_bytes:
                    parsed = json.loads(body_bytes)
                else:
                    parsed = {}
            except Exception:
                parsed = {}

        if isinstance(parsed, dict):
            # prefer JSON values where provided
            name = name or parsed.get("name")
            email = email or parsed.get("email")
            password = password or parsed.get("password")
            phone = phone or parsed.get("phone", phone)
            role = role or parsed.get("role", role)

    # normalize and validate
    name = (name or "").strip()
    email = (email or "").strip().lower()
    password = (password or "")

    # Simple validation
    if not name or not email or not password:
        msg = "Name, email and password are required"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
            return JSONResponse({"error": msg}, status_code=400)
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": msg, "name": name, "email": email},
        )

    # Lazy-load Employee model (support Employee or Employee1)
    try:
        import app.employees.models as models
        Employee = getattr(models, "Employee", None) or getattr(models, "Employee1", None)
        if Employee is None:
            raise ImportError("No Employee or Employee1 class found in app.employees.models")
    except Exception as imp_exc:
        detail = str(imp_exc)
        if DEBUG_SIGNUP:
            print("DEBUG: Employee model load failed:", detail)
        raise HTTPException(status_code=500, detail="Employee model not available")

    # Try to determine engine/URL bound to session for debug purposes
    engine_url = "<unknown>"
    try:
        engine = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
        if engine is not None and hasattr(engine, "url"):
            engine_url = str(engine.url)
        else:
            engine_url = repr(engine)
    except Exception:
        engine_url = "<unable to determine engine>"

    # check if email exists
    try:
        existing = db.query(Employee).filter(Employee.email == email).first()
    except Exception as exc:
        detail = str(exc)
        if DEBUG_SIGNUP:
            print("DEBUG: DB query error:", detail)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
            return JSONResponse({"error": "Database query error", "detail": detail, "engine": engine_url}, status_code=500)
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Database query error: " + detail})

    if existing:
        msg = "Email already exists!"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
            return JSONResponse({"error": msg}, status_code=400)
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg, "name": name, "email": email})

    # detect which password column to use
    has_hash_col = hasattr(Employee, "password_hash")
    has_plain_col = hasattr(Employee, "password")

    # Create new user instance
    try:
        if has_hash_col:
            new_user = Employee(
                name=name,
                email=email,
                phone=phone,
                role=role,  # ensure role is provided to satisfy NOT NULL DB constraints
                password_hash=generate_password_hash(password),
            )
        elif has_plain_col:
            new_user = Employee(
                name=name,
                email=email,
                phone=phone,
                role=role,
                password=password,
            )
        else:
            msg = "No password column on Employee model. Contact admin."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
                return JSONResponse({"error": msg}, status_code=500)
            return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        if DEBUG_SIGNUP:
            print("DEBUG: Created new user id:", getattr(new_user, "id", None))
            print("DEBUG: Model:", Employee.__name__, "tablename:", getattr(Employee, "__tablename__", "<none>"))
            print("DEBUG: Engine/DB URL bound to session:", engine_url)

    except Exception as exc:
        # rollback and report the real DB error in debug mode so you can see what's missing
        db.rollback()
        detail = str(exc)
        if DEBUG_SIGNUP:
            print("DEBUG: DB commit/create failed:", detail)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
            # include engine info and error detail during debugging so you can inspect quickly
            payload = {"error": "Database error creating user", "detail": detail}
            if DEBUG_SIGNUP:
                payload["engine"] = engine_url
            return JSONResponse(payload, status_code=500)
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Database error creating user: " + detail})

    # Auto-login: store session (best-effort)
    try:
        request.session["user_id"] = int(getattr(new_user, "id", None))
        request.session["role"] = getattr(new_user, "role", "employee")
        request.session["name"] = getattr(new_user, "name", "")
    except Exception:
        # if session store misconfigured, continue gracefully
        pass

    # decide redirect based on role
    redirect_url = "/go_employee"
    new_role = getattr(new_user, "role", "")
    if new_role == "admin":
        redirect_url = "/go_admin"
    elif new_role == "hr":
        redirect_url = "/go_hr"

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or is_json:
        return JSONResponse({"redirect": redirect_url})
    return RedirectResponse(url=redirect_url, status_code=303)
