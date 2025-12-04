# app/attendance/router.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, List
import logging
import importlib

from app.database import get_db
from app.attendance.models import Attendance

# Auth dependencies (your existing auth helpers)
from app.auth.dependencies import (
    get_current_user_payload_or_session,
    require_role_or_session,
    require_role,
)

logger = logging.getLogger(__name__)

# Router must be defined before decorated endpoints
router = APIRouter(prefix="/attendance", tags=["attendance"])


# -----------------------------
# Helper: extract user id
# -----------------------------
def _get_user_id_from_payload(payload: Optional[Dict[str, Any]]) -> int:
    if not payload:
        logger.debug("Auth payload is missing or empty.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth payload")

    for key in ("sub", "user_id", "id"):
        if key in payload:
            v = payload.get(key)
            if v is None:
                continue
            try:
                return int(v)
            except (TypeError, ValueError):
                logger.warning("Invalid user id in token/session for key %s: %r", key, v)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Invalid user id in token/session ({key})")

    logger.warning("Token/session subject missing: payload keys=%s", list(payload.keys()))
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token subject missing")


# -----------------------------
# Helpers to format timestamps robustly
# -----------------------------
def _combine_date_time(date_val, time_val):
    """
    Return an ISO datetime string combining date_val and time_val.
    Accepts:
      - time_val as datetime -> returns .isoformat()
      - time_val as string with 'T' -> returned as-is
      - time-only string like '4:24:12' -> combined with date_val (or today)
      - time-like object (has hour/minute) -> combine with date_val (or today)
    """
    if not time_val:
        return None

    try:
        # if it's already a datetime object
        if isinstance(time_val, datetime):
            return time_val.isoformat()

        # if it's a string that looks like an ISO datetime (has 'T'), assume it's fine
        if isinstance(time_val, str):
            if "T" in time_val:
                return time_val
            # assume time-only string like '4:24:12' or '04:24:12'; use date_val or today
            d = date_val if isinstance(date_val, date) else None
            if d is None:
                # if date_val is string try to keep it
                try:
                    d = date.fromisoformat(str(date_val))
                except Exception:
                    d = date.today()
            # pad / keep the time string as-is
            return f"{d.isoformat()}T{time_val}"

        # if it's a time-like object (has hour/minute attributes)
        if hasattr(time_val, "hour"):
            d = date_val if isinstance(date_val, date) else None
            if d is None:
                try:
                    d = date.fromisoformat(str(date_val))
                except Exception:
                    d = date.today()
            dt = datetime.combine(d, time_val)
            return dt.isoformat()

        # fallback - convert to string
        return str(time_val)
    except Exception:
        # last resort: str()
        try:
            return str(time_val)
        except Exception:
            return None


def _parse_iso_or_combined(date_val, time_val):
    """
    Parse combined ISO returned by _combine_date_time into a datetime object.
    Returns None if parsing fails.
    """
    try:
        iso = _combine_date_time(date_val, time_val)
        if not iso:
            return None
        # fromisoformat should accept 'YYYY-MM-DDTHH:MM:SS' (maybe with microseconds)
        return datetime.fromisoformat(iso)
    except Exception:
        # fallback: try creating datetime from strings
        try:
            if isinstance(date_val, str) and isinstance(time_val, str):
                combined = f"{date_val}T{time_val}"
                return datetime.fromisoformat(combined)
        except Exception:
            return None
    return None


def _fmt_time_ampm(date_val, time_val):
    """Return human-friendly time like '6:51 AM' or None."""
    try:
        dt = None
        if isinstance(time_val, datetime):
            dt = time_val
        else:
            dt = _parse_iso_or_combined(date_val, time_val)
        if not dt:
            return None
        return dt.strftime("%-I:%M %p") if hasattr(dt, "strftime") else None
    except Exception:
        # Windows' strftime doesn't support %-I; try a portable approach:
        try:
            dt2 = _parse_iso_or_combined(date_val, time_val)
            if not dt2:
                return None
            hour = dt2.hour % 12
            hour = hour if hour != 0 else 12
            return f"{hour}:{dt2.strftime('%M')} {'AM' if dt2.hour < 12 else 'PM'}"
        except Exception:
            return None


def _format_duration(seconds: int):
    """Return human friendly duration 'Hh Mm' from seconds"""
    if seconds is None:
        return None
    try:
        s = int(seconds)
        hours = s // 3600
        mins = (s % 3600) // 60
        parts = []
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        return " ".join(parts)
    except Exception:
        return None


def _compute_worked(att_date, check_in_val, check_out_val):
    """Return (seconds, human) or (None, None) if cannot compute."""
    try:
        if not check_in_val or not check_out_val:
            return None, None
        dt_in = _parse_iso_or_combined(att_date, check_in_val)
        dt_out = _parse_iso_or_combined(att_date, check_out_val)
        if not dt_in or not dt_out:
            return None, None
        delta = dt_out - dt_in
        secs = int(delta.total_seconds())
        if secs < 0:
            # Out is earlier than in - ignore
            return None, None
        return secs, _format_duration(secs)
    except Exception:
        return None, None


# -----------------------------
# Admin summary (robust)
# -----------------------------
@router.get("/admin/summary", response_model=dict)
def admin_presence_summary(
    db: Session = Depends(get_db),
    _ = Depends(require_role(["admin"]))
):
    """
    Admin-only summary for today's presence.
    Uses employee1 and attendance1 (raw SQL fallback),
    prefers an ORM Employee model if available.

    Important:
      - Only shows users whose role is 'admin' in the summary.
      - check_in/check_out returned as ISO datetime strings (date+time) and friendly AM/PM strings.
    """
    EMPLOYEE_TABLE = "employee1"
    ATT_TABLE = "attendance1"

    # Attempt to import an Employee1 ORM model if present for a nicer join.
    Employee = None
    try:
        mod = importlib.import_module("app.employee1.models")
        Employee = getattr(mod, "Employee1", None) or getattr(mod, "Employee", None)
    except Exception:
        Employee = None

    today = date.today()
    present_count = 0
    absent_count = 0
    total_admins = 0
    admins_list: List[Dict[str, Any]] = []

    # Preferred: ORM solution if Employee model exists
    if Employee is not None:
        try:
            from sqlalchemy.orm import aliased
            E = aliased(Employee)
            Att = Attendance

            # outerjoin on today's attendance
            rows = (
                db.query(E, Att)
                .outerjoin(Att, (Att.employee_id == E.id) & (Att.date == today))
                .filter(E.role != None)  # ensure role exists
                .order_by(E.name if hasattr(E, "name") else E.id)
                .all()
            )

            for e, att in rows:
                # admin detection
                is_admin = False
                try:
                    if hasattr(e, "role") and e.role is not None:
                        is_admin = str(e.role).lower() == "admin"
                    elif hasattr(e, "is_admin"):
                        is_admin = bool(getattr(e, "is_admin"))
                except Exception:
                    is_admin = False

                if not is_admin:
                    continue

                total_admins += 1
                is_present = bool(att and getattr(att, "check_in", None))
                if is_present:
                    present_count += 1
                else:
                    absent_count += 1

                # compute friendly display values and worked time
                ci = getattr(att, "check_in", None) if att else None
                co = getattr(att, "check_out", None) if att else None
                ci_iso = _combine_date_time(getattr(att, "date", today) if att else today, ci) if ci else None
                co_iso = _combine_date_time(getattr(att, "date", today) if att else today, co) if co else None
                secs, human = _compute_worked(getattr(att, "date", today) if att else today, ci, co)

                admins_list.append({
                    "id": getattr(e, "id", None),
                    "name": getattr(e, "name", None),
                    "check_in": ci_iso,
                    "check_in_display": _fmt_time_ampm(getattr(att, "date", today) if att else today, ci),
                    "check_out": co_iso,
                    "check_out_display": _fmt_time_ampm(getattr(att, "date", today) if att else today, co),
                    "worked_seconds": secs,
                    "worked_human": human,
                    "status": getattr(att, "status", None) if att else None,
                    "present": is_present
                })

            return {
                "date": str(today),
                "present_count": present_count,
                "absent_count": absent_count,
                "total_admins": total_admins,
                "admins": admins_list
            }
        except Exception:
            logger.exception("ORM admin summary failed; falling back to SQL.")

    # Raw SQL fallback: explicit join between employee1 and attendance1
    try:
        # Only select employees who are admins (use lower() to be safe)
        sql = text(f"""
            SELECT e.id as id,
                   e.name as name,
                   e.role as role,
                   a.date as att_date,
                   a.check_in as check_in,
                   a.check_out as check_out,
                   a.status as status
            FROM {EMPLOYEE_TABLE} e
            LEFT JOIN {ATT_TABLE} a
              ON a.employee_id = e.id AND date(a.date) = :today
            WHERE LOWER(COALESCE(e.role, '')) = 'admin'
            ORDER BY e.name
        """)
        rows = db.execute(sql, {"today": str(today)}).fetchall()
    except Exception as exc:
        logger.exception("Failed to query employee/attendance via raw SQL: %s", exc)
        raise HTTPException(status_code=500, detail=f"DB error querying employee/attendance: {exc}")

    for r in rows:
        # support both mapping-row and index access
        try:
            emp_id = r["id"] if "id" in r.keys() else r[0]
            emp_name = r["name"] if "name" in r.keys() else (r[1] if len(r) > 1 else None)
            emp_role = r["role"] if "role" in r.keys() else (r[2] if len(r) > 2 else None)
            att_date = r["att_date"] if "att_date" in r.keys() else (r[3] if len(r) > 3 else None)
            check_in = r["check_in"] if "check_in" in r.keys() else (r[4] if len(r) > 4 else None)
            check_out = r["check_out"] if "check_out" in r.keys() else (r[5] if len(r) > 5 else None)
            status = r["status"] if "status" in r.keys() else (r[6] if len(r) > 6 else None)
        except Exception:
            emp_id = r[0]
            emp_name = r[1] if len(r) > 1 else None
            emp_role = r[2] if len(r) > 2 else None
            att_date = r[3] if len(r) > 3 else None
            check_in = r[4] if len(r) > 4 else None
            check_out = r[5] if len(r) > 5 else None
            status = r[6] if len(r) > 6 else None

        # ensure admin only (defensive)
        is_admin = False
        try:
            if emp_role is not None and str(emp_role).lower() == "admin":
                is_admin = True
        except Exception:
            is_admin = False

        if not is_admin:
            continue

        total_admins += 1
        is_present = bool(check_in)
        if is_present:
            present_count += 1
        else:
            absent_count += 1

        # compute display + worked
        ci_iso = _combine_date_time(att_date or today, check_in) if check_in else None
        co_iso = _combine_date_time(att_date or today, check_out) if check_out else None
        secs, human = _compute_worked(att_date or today, check_in, check_out)

        admins_list.append({
            "id": emp_id,
            "name": emp_name,
            "check_in": ci_iso,
            "check_in_display": _fmt_time_ampm(att_date or today, check_in),
            "check_out": co_iso,
            "check_out_display": _fmt_time_ampm(att_date or today, check_out),
            "worked_seconds": secs,
            "worked_human": human,
            "status": status,
            "present": is_present
        })

    return {
        "date": str(today),
        "present_count": present_count,
        "absent_count": absent_count,
        "total_admins": total_admins,
        "admins": admins_list
    }


# -----------------------------
# Role-aware landing for /attendance
# (supports optional from_date/to_date query params)
# -----------------------------
@router.get("/", include_in_schema=False)
def attendance_index(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    # Use the payload-only dependency here to avoid the dependency returning a Response object
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    # If date filters are present, return JSON rows for the current user
    if from_date or to_date:
        user_id = _get_user_id_from_payload(payload)
        q = db.query(Attendance).filter(Attendance.employee_id == user_id)
        if from_date:
            q = q.filter(Attendance.date >= from_date)
        if to_date:
            q = q.filter(Attendance.date <= to_date)
        rows = q.order_by(Attendance.date.desc()).all()
        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "date": str(r.date),
                "check_in": _combine_date_time(r.date, r.check_in) if r.check_in else None,
                "check_in_display": _fmt_time_ampm(r.date, r.check_in) if r.check_in else None,
                "check_out": _combine_date_time(r.date, r.check_out) if r.check_out else None,
                "check_out_display": _fmt_time_ampm(r.date, r.check_out) if r.check_out else None,
                "status": r.status
            })
        return result

    accept = request.headers.get("accept", "")
    wants_html = "text/html" in accept or "application/xhtml+xml" in accept

    # Defensive: payload may be None or a dict
    role = ""
    if payload and isinstance(payload, dict):
        role = payload.get("role", "") or ""
    role_str = role.lower() if isinstance(role, str) else ""

    # For HTML clients redirect to the proper page (or login if not authenticated)
    if wants_html:
        if not payload:
            return RedirectResponse("/login", status_code=302)
        if role_str == "admin":
            return RedirectResponse("/admin/attendance")
        if role_str == "hr":
            return RedirectResponse("/hr")
        return RedirectResponse("/attendance/my")

    # For non-HTML requests require a valid payload
    user_id = _get_user_id_from_payload(payload)
    return {
        "message": "Attendance system",
        "user_id": user_id,
        "role": payload.get("role") if isinstance(payload, dict) else None,
        "name": payload.get("name", "Unknown") if isinstance(payload, dict) else "Unknown",
        "endpoints": {
            "check_in": "/attendance/checkin",
            "check_out": "/attendance/checkout",
            "my_attendance": "/attendance/me",
            "debug": "/attendance/debug-noauth"
        }
    }


# -----------------------------
# Check in
# -----------------------------
@router.post("/checkin", response_model=dict)
def check_in(
    request: Request,
    db: Session = Depends(get_db),
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = _get_user_id_from_payload(payload)
    today = date.today()
    att = db.query(Attendance).filter(Attendance.employee_id == user_id, Attendance.date == today).first()

    # Use server-local datetime for consistency
    now_dt = datetime.now()

    # Save either datetime object (preferred) or time portion depending on model
    if not att:
        att = Attendance(employee_id=user_id, date=today, check_in=now_dt, status="PRESENT")
        db.add(att)
        db.commit()
        db.refresh(att)
        logger.info("User %s checked in at %s (attendance id=%s)", user_id, now_dt.isoformat(), getattr(att, "id", None))
        return {
            "success": True,
            "message": "Checked in successfully",
            "attendance_id": att.id,
            "date": str(att.date),
            "check_in": _combine_date_time(att.date, att.check_in)
        }

    if not att.check_in:
        att.check_in = now_dt
        db.commit()
        db.refresh(att)
        logger.info("User %s checked in (existing row) at %s (attendance id=%s)", user_id, now_dt.isoformat(), getattr(att, "id", None))
        return {
            "success": True,
            "message": "Checked in successfully",
            "attendance_id": att.id,
            "date": str(att.date),
            "check_in": _combine_date_time(att.date, att.check_in)
        }

    return {
        "success": False,
        "message": "Already checked-in",
        "attendance": {
            "date": str(att.date),
            "check_in": _combine_date_time(att.date, att.check_in)
        }
    }


# -----------------------------
# Debug GET (safe) for checkout (does not change DB)
# -----------------------------
@router.get("/checkout-debug", response_model=dict)
def checkout_get_for_debug(
    request: Request,
    db: Session = Depends(get_db),
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = _get_user_id_from_payload(payload)
    today = date.today()
    att = db.query(Attendance).filter(Attendance.employee_id == user_id, Attendance.date == today).first()
    if not att:
        return {"detail": "No attendance record for today", "date": str(today)}
    secs, human = _compute_worked(att.date, att.check_in, att.check_out)
    return {
        "date": str(att.date),
        "check_in": _combine_date_time(att.date, att.check_in) if att.check_in else None,
        "check_in_display": _fmt_time_ampm(att.date, att.check_in) if att.check_in else None,
        "check_out": _combine_date_time(att.date, att.check_out) if att.check_out else None,
        "check_out_display": _fmt_time_ampm(att.date, att.check_out) if att.check_out else None,
        "can_checkin": not bool(att.check_in),
        "can_checkout": bool(att.check_in) and not bool(att.check_out),
        "worked_seconds": secs,
        "worked_human": human
    }


# -----------------------------
# Check out (POST)
# -----------------------------
@router.post("/checkout", response_model=dict)
def check_out(
    request: Request,
    db: Session = Depends(get_db),
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = _get_user_id_from_payload(payload)
    today = date.today()
    att = db.query(Attendance).filter(Attendance.employee_id == user_id, Attendance.date == today).first()

    if not att:
        raise HTTPException(status_code=404, detail="No attendance record found for today. Please check in first.")

    if not att.check_in:
        raise HTTPException(status_code=400, detail="Cannot check out without checking in first.")

    if att.check_out:
        return {
            "success": False,
            "message": "Already checked out",
            "attendance": {
                "date": str(att.date),
                "check_out": _combine_date_time(att.date, att.check_out)
            }
        }

    # Use server-local time to match check_in and to avoid UTC/local confusion
    now_dt = datetime.now()
    att.check_out = now_dt
    db.commit()
    db.refresh(att)

    # compute worked duration
    secs, human = _compute_worked(att.date, att.check_in, att.check_out)

    logger.info("User %s checked out at %s (attendance id=%s) worked: %s",
                user_id, now_dt.isoformat(), getattr(att, "id", None), human)

    return {
        "success": True,
        "message": "Checked out successfully",
        "attendance_id": att.id,
        "date": str(att.date),
        "check_in": _combine_date_time(att.date, att.check_in) if att.check_in else None,
        "check_in_display": _fmt_time_ampm(att.date, att.check_in) if att.check_in else None,
        "check_out": _combine_date_time(att.date, att.check_out),
        "check_out_display": _fmt_time_ampm(att.date, att.check_out),
        "worked_seconds": secs,
        "worked_human": human
    }


# -----------------------------
# Debug (no auth)
# -----------------------------
@router.get("/debug-noauth", response_model=dict)
def debug_noauth(request: Request):
    session_data = {}
    try:
        session_data = dict(getattr(request, "session", {}))
    except Exception as e:
        session_data = {"error": str(e)}

    return {
        "cookies": dict(request.cookies),
        "session": session_data,
        "has_session": hasattr(request, "session"),
        "headers": {
            "authorization": request.headers.get("authorization", "Not present"),
            "cookie": request.headers.get("cookie", "Not present")
        }
    }


# -----------------------------
# My attendance (current user)
# -----------------------------
@router.get("/me", response_model=dict)
def my_attendance(
    limit: int = 30,
    db: Session = Depends(get_db),
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = _get_user_id_from_payload(payload)
    rows = db.query(Attendance).filter(Attendance.employee_id == user_id).order_by(Attendance.date.desc()).limit(limit).all()

    result = []
    for r in rows:
        secs, human = _compute_worked(r.date, r.check_in, r.check_out)
        result.append({
            "id": r.id,
            "date": str(r.date),
            "check_in": _combine_date_time(r.date, r.check_in) if r.check_in else None,
            "check_in_display": _fmt_time_ampm(r.date, r.check_in) if r.check_in else None,
            "check_out": _combine_date_time(r.date, r.check_out) if r.check_out else None,
            "check_out_display": _fmt_time_ampm(r.date, r.check_out) if r.check_out else None,
            "status": r.status,
            "worked_seconds": secs,
            "worked_human": human
        })

    return {"user_id": user_id, "total_records": len(result), "attendance": result}


# -----------------------------
# Today's status for current user
# -----------------------------
@router.get("/status", response_model=dict)
def attendance_status(
    db: Session = Depends(get_db),
    payload: Optional[Dict[str, Any]] = Depends(get_current_user_payload_or_session)
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = _get_user_id_from_payload(payload)
    today = date.today()
    att = db.query(Attendance).filter(Attendance.employee_id == user_id, Attendance.date == today).first()

    if not att:
        return {"status": "NOT_CHECKED_IN", "message": "You haven't checked in today", "date": str(today), "can_checkin": True, "can_checkout": False}

    secs, human = _compute_worked(att.date, att.check_in, att.check_out)
    return {
        "status": att.status,
        "date": str(att.date),
        "check_in": _combine_date_time(att.date, att.check_in) if att.check_in else None,
        "check_in_display": _fmt_time_ampm(att.date, att.check_in) if att.check_in else None,
        "check_out": _combine_date_time(att.date, att.check_out) if att.check_out else None,
        "check_out_display": _fmt_time_ampm(att.date, att.check_out) if att.check_out else None,
        "can_checkin": not bool(att.check_in),
        "can_checkout": bool(att.check_in) and not bool(att.check_out),
        "worked_seconds": secs,
        "worked_human": human
    }


# -----------------------------
# Admin data endpoint (for admin_attendance.html)
# -----------------------------
@router.get("/admin/data", response_model=List[Dict[str, Any]])
def admin_attendance_data(db: Session = Depends(get_db), _ = Depends(require_role_or_session(["admin"]))):
    """
    Returns recent attendance rows joined with employee1 to include employee_name.
    check_in/check_out are returned as ISO datetime strings (date+time) and friendly fields.
    """
    EMPLOYEE_TABLE = "employee1"
    ATT_TABLE = "attendance1"

    result = []
    # Try ORM join if Employee model exists
    Employee = None
    try:
        mod = importlib.import_module("app.employee1.models")
        Employee = getattr(mod, "Employee1", None) or getattr(mod, "Employee", None)
    except Exception:
        Employee = None

    if Employee is not None:
        try:
            rows = (
                db.query(Attendance, Employee)
                .join(Employee, Employee.id == Attendance.employee_id)
                .order_by(Attendance.date.desc())
                .limit(500)
                .all()
            )
            for att, emp in rows:
                secs, human = _compute_worked(att.date, att.check_in, att.check_out)
                result.append({
                    "id": att.id,
                    "date": str(att.date),
                    "employee_id": att.employee_id,
                    "employee_name": getattr(emp, "name", None),
                    "check_in": _combine_date_time(att.date, att.check_in) if att.check_in else None,
                    "check_in_display": _fmt_time_ampm(att.date, att.check_in) if att.check_in else None,
                    "check_out": _combine_date_time(att.date, att.check_out) if att.check_out else None,
                    "check_out_display": _fmt_time_ampm(att.date, att.check_out) if att.check_out else None,
                    "status": att.status,
                    "worked_seconds": secs,
                    "worked_human": human
                })
            return result
        except Exception:
            logger.exception("ORM admin/data join failed; falling back to raw SQL.")

    # Raw SQL fallback using attendance1 and employee1 (simple select on attendance + employee lookup)
    try:
        sql = text(f"""
            SELECT a.id AS id, a.date AS date, a.employee_id AS employee_id,
                   e.name AS employee_name,
                   a.check_in AS check_in, a.check_out AS check_out, a.status AS status
            FROM {ATT_TABLE} a
            LEFT JOIN {EMPLOYEE_TABLE} e ON e.id = a.employee_id
            ORDER BY a.date DESC
            LIMIT 500
        """)
        rows = db.execute(sql).fetchall()
    except Exception as exc:
        logger.exception("Failed to query attendance/employee via raw SQL: %s", exc)
        raise HTTPException(status_code=500, detail=f"DB error querying attendance/employee: {exc}")

    for r in rows:
        try:
            rec_date = r["date"] if "date" in r.keys() else (r[1] if len(r) > 1 else None)
            check_in = r["check_in"] if "check_in" in r.keys() else (r[4] if len(r) > 4 else None)
            check_out = r["check_out"] if "check_out" in r.keys() else (r[5] if len(r) > 5 else None)

            secs, human = _compute_worked(rec_date, check_in, check_out)

            rec = {
                "id": r["id"] if "id" in r.keys() else r[0],
                "date": str(rec_date) if rec_date is not None else None,
                "employee_id": r["employee_id"] if "employee_id" in r.keys() else r[2],
                "employee_name": r["employee_name"] if "employee_name" in r.keys() else (r[3] if len(r) > 3 else None),
                "check_in": _combine_date_time(rec_date, check_in) if check_in else None,
                "check_in_display": _fmt_time_ampm(rec_date, check_in) if check_in else None,
                "check_out": _combine_date_time(rec_date, check_out) if check_out else None,
                "check_out_display": _fmt_time_ampm(rec_date, check_out) if check_out else None,
                "status": r["status"] if "status" in r.keys() else (r[6] if len(r) > 6 else None),
                "worked_seconds": secs,
                "worked_human": human
            }
        except Exception:
            rec_date = r[1] if len(r) > 1 else None
            secs, human = _compute_worked(rec_date, r[4] if len(r) > 4 else None, r[5] if len(r) > 5 else None)
            rec = {
                "id": r[0],
                "date": str(rec_date) if rec_date is not None else None,
                "employee_id": r[2] if len(r) > 2 else None,
                "employee_name": r[3] if len(r) > 3 else None,
                "check_in": _combine_date_time(rec_date, r[4]) if len(r) > 4 and r[4] else None,
                "check_in_display": _fmt_time_ampm(rec_date, r[4]) if len(r) > 4 and r[4] else None,
                "check_out": _combine_date_time(rec_date, r[5]) if len(r) > 5 and r[5] else None,
                "check_out_display": _fmt_time_ampm(rec_date, r[5]) if len(r) > 5 and r[5] else None,
                "status": r[6] if len(r) > 6 else None,
                "worked_seconds": secs,
                "worked_human": human
            }
        result.append(rec)

    return result


# -----------------------------
# (DEBUG) Useful endpoints for local troubleshooting
# -----------------------------
@router.get("/admin/summary-all", response_model=dict)
def admin_summary_all(db: Session = Depends(get_db), _ = Depends(require_role(["admin"]))):
    """
    Returns full employee list joined with today's attendance.
    Use this to get accurate Present / Absent for all rows in employee1.
    """
    EMP = "employee1"
    ATT = "attendance1"
    today = date.today()
    try:
        sql = text(f"""
            SELECT e.id, e.name AS name, e.role,
                   a.check_in, a.check_out, a.status
            FROM {EMP} e
            LEFT JOIN {ATT} a ON a.employee_id = e.id AND date(a.date) = :today
            ORDER BY e.name
        """)
        rows = db.execute(sql, {"today": str(today)}).fetchall()
    except Exception as exc:
        logger.exception("admin_summary_all DB error: %s", exc)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    employees = []
    for r in rows:
        # handle both mapping and tuple row
        if hasattr(r, "keys"):
            secs, human = _compute_worked(today, r["check_in"], r["check_out"])
            employees.append({
                "id": r["id"],
                "name": r["name"],
                "role": r["role"],
                "check_in": _combine_date_time(today, r["check_in"]) if r["check_in"] is not None else None,
                "check_in_display": _fmt_time_ampm(today, r["check_in"]) if r["check_in"] is not None else None,
                "check_out": _combine_date_time(today, r["check_out"]) if r["check_out"] is not None else None,
                "check_out_display": _fmt_time_ampm(today, r["check_out"]) if r["check_out"] is not None else None,
                "status": r["status"],
                "worked_seconds": secs,
                "worked_human": human
            })
        else:
            secs, human = _compute_worked(today, r[3] if len(r) > 3 else None, r[4] if len(r) > 4 else None)
            employees.append({
                "id": r[0],
                "name": r[1],
                "role": r[2],
                "check_in": _combine_date_time(today, r[3]) if r[3] is not None else None,
                "check_in_display": _fmt_time_ampm(today, r[3]) if r[3] is not None else None,
                "check_out": _combine_date_time(today, r[4]) if r[4] is not None else None,
                "check_out_display": _fmt_time_ampm(today, r[4]) if r[4] is not None else None,
                "status": r[5] if len(r) > 5 else None,
                "worked_seconds": secs,
                "worked_human": human
            })
    return {"date": str(today), "employees": employees}


@router.get("/admin/debug-payload", response_model=dict)
def admin_debug_payload(request: Request, payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)):
    """
    Shows the payload returned by get_current_user_payload_or_session and request.session/cookies.
    Useful to confirm whether the server sees a valid admin session.
    """
    sess = {}
    try:
        sess = dict(getattr(request, "session", {}) or {})
    except Exception:
        sess = {"info": "no session object"}
    return {"payload": payload, "session": sess, "cookies": dict(request.cookies)}


@router.get("/admin/data-debug-noauth", response_model=List[Dict[str, Any]])
def admin_attendance_data_debug(db: Session = Depends(get_db)):
    """
    Debug copy of admin attendance data WITHOUT auth.
    Use to confirm whether the DB query itself succeeds (bypasses require_role).
    """
    try:
        rows = db.query(Attendance).order_by(Attendance.date.desc()).limit(500).all()
    except Exception as exc:
        logger.exception("admin/data-debug DB error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    result = []
    for r in rows:
        secs, human = _compute_worked(r.date, r.check_in, r.check_out)
        result.append({
            "id": r.id,
            "date": str(r.date),
            "employee_id": r.employee_id,
            "employee_name": getattr(r, "employee_name", None),
            "check_in": _combine_date_time(r.date, r.check_in) if r.check_in else None,
            "check_in_display": _fmt_time_ampm(r.date, r.check_in) if r.check_in else None,
            "check_out": _combine_date_time(r.date, r.check_out) if r.check_out else None,
            "check_out_display": _fmt_time_ampm(r.date, r.check_out) if r.check_out else None,
            "status": r.status,
            "worked_seconds": secs,
            "worked_human": human
        })
    return result

@router.get("/admin/summary")
def attendance_summary(db: Session = Depends(get_db)):
    try:
        total = db.execute("SELECT COUNT(*) FROM attendance").scalar() or 0
    except:
        total = 0
    return {"total": total}
