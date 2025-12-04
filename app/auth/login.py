# app/auth/login.py

import os
from fastapi import APIRouter, Form, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from app.database import get_db
# import token helper to create JWT cookie
from app.auth.jwt_handler import create_access_token

router = APIRouter()

# Robust templates path relative to this file (avoids cwd issues)
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
TEMPLATES_DIR = os.path.normpath(TEMPLATES_DIR)
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# GET login page
@router.get("/login", response_class=HTMLResponse)
@router.get("/auth/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# POST login (accept both /login and /auth/login)
@router.post("/login")
@router.post("/auth/login")
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    email = (email or "").strip().lower()

    # lazy import model
    try:
        from app.employees.models import Employee as EmployeeModel
    except Exception:
        raise HTTPException(status_code=500, detail="Employee model not available")

    user = db.query(EmployeeModel).filter(EmployeeModel.email == email).first()

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if not user:
        if is_ajax:
            return JSONResponse({"error": "Invalid email or password."}, status_code=401)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password."})

    pw_hash = getattr(user, "password_hash", None)
    plain_pw = getattr(user, "password", None)

    valid = False
    if pw_hash:
        valid = check_password_hash(pw_hash, password)
    elif plain_pw is not None:
        valid = (str(plain_pw) == password)

    if not valid:
        if is_ajax:
            return JSONResponse({"error": "Invalid email or password."}, status_code=401)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password."})

    # Extract user data
    role = getattr(user, "role", "employee")
    name = getattr(user, "name", "")
    user_id = getattr(user, "id", None)

    # Save server-side session
    try:
        request.session["user_id"] = int(user_id) if user_id is not None else None
        request.session["role"] = role
        request.session["name"] = name
        print("SESSION SET:", dict(request.session))
    except Exception as e:
        print("SESSION ERROR:", e)

    # Create JWT token
    token_payload = {
        "sub": str(user_id) if user_id is not None else None,
        "user_id": int(user_id) if user_id is not None else None,
        "role": role,
        "name": name
    }
    jwt_token = create_access_token(token_payload)

    # AJAX login
    if is_ajax:
        redirect_target = "/go_employee"
        if role == "admin":
            redirect_target = "/go_admin"
        elif role == "hr":
            redirect_target = "/go_hr"
        return JSONResponse({"redirect": redirect_target, "role": role, "name": name, "token": jwt_token})

    # NORMAL LOGIN
    redirect_url = "/go_employee"
    if role == "admin":
        redirect_url = "/go_admin"
    elif role == "hr":
        redirect_url = "/go_hr"

    resp = RedirectResponse(url=redirect_url, status_code=303)

    # 🔥 FIXED COOKIE (ONLY CHANGE YOU REQUIRED)
    resp.set_cookie(
        key="session",
        value=jwt_token,
        httponly=True,
        secure=False,      # True only if HTTPS
        samesite="lax",    # "none" if cross-site
        path="/"           # <-- CRITICAL FIX
    )

    return resp


# Dashboard pages (render existing templates)
@router.get("/go_admin", response_class=HTMLResponse)
def go_admin(request: Request):
    name = request.session.get("name", "")
    return templates.TemplateResponse("go_admin.html", {"request": request, "name": name})


@router.get("/go_employee", response_class=HTMLResponse)
def go_employee(request: Request):
    name = request.session.get("name", "")
    return templates.TemplateResponse("go_employee.html", {"request": request, "name": name})


@router.get("/go_hr", response_class=HTMLResponse)
def go_hr(request: Request):
    name = request.session.get("name", "")
    return templates.TemplateResponse("go_hr.html", {"request": request, "name": name})
