# app/dashboard_router.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Dict, Any
from typing import Optional
from fastapi import Path
from typing import Optional

from app.auth.dependencies import (
    get_current_user_payload_or_session,
    require_role_or_session
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# -----------------------------
# Employee dashboard
# -----------------------------
@router.get("/attendance/dashboard")
def employee_dashboard(
    request: Request,
    payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "go_employee.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# Admin dashboard
# -----------------------------
@router.get("/admin")
def admin_dashboard(
    request: Request,
    payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)
):
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    return templates.TemplateResponse(
        "go_admin.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# HR dashboard
# -----------------------------
@router.get("/hr")
def hr_dashboard(
    request: Request,
    payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)
):
    if payload.get("role") not in ("hr", "admin"):
        raise HTTPException(status_code=403, detail="HR only")

    return templates.TemplateResponse(
        "go_hr.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# Employee attendance page
# -----------------------------
@router.get("/attendance/my")
def page_employee_attendance(
    request: Request,
    payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "employee_attendance.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# Employee leaves page
# -----------------------------
@router.get("/leaves/my", dependencies=[Depends(require_role_or_session(["employee", "admin", "hr"]))])
def page_employee_leaves(
    request: Request,
    payload = Depends(get_current_user_payload_or_session)
):
    return templates.TemplateResponse(
        "employee_leaves.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# ALIAS ROUTES (correct position)
# -----------------------------

# /leaves/ui/my  → open leaves.html
@router.get("/ui/my", dependencies=[Depends(require_role_or_session(["employee", "admin", "hr"]))])
def leaves_ui_my(request: Request, payload = Depends(get_current_user_payload_or_session)):
    return templates.TemplateResponse(
        "leaves.html",
        {
            "request": request,
            "role": payload.get("role", "employee"),
            "user_name": payload.get("name", ""),
            "user_id": payload.get("id", "")
        }
    )

# /leaves/apply → also open leaves.html
@router.get("/apply", dependencies=[Depends(require_role_or_session(["employee", "admin", "hr"]))])
def leaves_apply_alias(request: Request, payload = Depends(get_current_user_payload_or_session)):
    return templates.TemplateResponse(
        "leaves.html",
        {
            "request": request,
            "role": payload.get("role", "employee"),
            "user_name": payload.get("name", ""),
            "user_id": payload.get("id", "")
        }
    )


# -----------------------------
# Admin attendance
# -----------------------------
@router.get("/admin/attendance", dependencies=[Depends(require_role_or_session(["admin"]))])
def page_admin_attendance(
    request: Request,
    payload = Depends(get_current_user_payload_or_session)
):
    return templates.TemplateResponse(
        "admin_attendance.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )


# -----------------------------
# Admin / HR leave management
# -----------------------------
@router.get("/admin/leaves", dependencies=[Depends(require_role_or_session(["admin", "hr"]))])
def page_admin_leaves(
    request: Request,
    payload = Depends(get_current_user_payload_or_session)
):
    return templates.TemplateResponse(
        "admin_leaves.html",
        {
            "request": request,
            "name": payload.get("name", ""),
            "role": payload.get("role", "")
        }
    )

    # add this to app/dashboard_router.py (near other /ui routes)

@router.get("/ui", dependencies=[Depends(require_role_or_session(["employee","admin","hr"]))])
@router.get("/ui/{page}", dependencies=[Depends(require_role_or_session(["employee","admin","hr"]))])
def leaves_ui_catchall(
    request: Request,
    page: Optional[str] = None,
    payload = Depends(get_current_user_payload_or_session)
):
    # protect against payload being None or not a dict
    ctx = payload or {}
    return templates.TemplateResponse(
        "leaves.html",   # <- ensure this file exists in app/templates/
        {
            "request": request,
            "role": ctx.get("role", "employee"),
            "user_name": ctx.get("name", ""),
            "user_id": ctx.get("id") or ctx.get("user_id") or ""
        }
    )