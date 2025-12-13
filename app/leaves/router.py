# app/leaves/router.py
from app.utils.email_service import send_email

from dotenv import load_dotenv
load_dotenv()  # ensure env vars are available when this module is imported

from fastapi import APIRouter, Depends, HTTPException, Request, FastAPI
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import os
import json
from pathlib import Path
from threading import Lock
import logging
import inspect

from app.database import SessionLocal
from app.leaves.models import Leave

# -----------------------------------------------------------
# Ensure Employee variable exists before logging
# -----------------------------------------------------------
Employee = None
try:
    from app.employee.models import Employee     # older folder
except Exception:
    try:
        from app.employees.models import Employee  # alternate folder name
    except Exception:
        Employee = None

# -----------------------------------------------------------
# Robust compatibility wrapper for send_email
# -----------------------------------------------------------
def send_email_with_attachment(to, subject, body, attachment_path=None):
    """
    Compatibility wrapper for send_email so existing callers don't crash.
    - Attempts keyword call if send_email accepts keywords.
    - Falls back to common positional argument orders.
    - Raises RuntimeError with helpful message if none work.
    """
    def _raise(msg, exc=None):
        if exc:
            raise RuntimeError(f"send_email_with_attachment failed: {msg}: {exc}")
        raise RuntimeError(f"send_email_with_attachment failed: {msg}")

    try:
        sig = inspect.signature(send_email)
    except Exception as e:
        _raise("could not inspect send_email signature", e)

    params = sig.parameters

    # try reasonable keyword mapping first
    kw = {}
    if 'to' in params: kw['to'] = to
    if 'subject' in params: kw['subject'] = subject
    if 'body' in params: kw['body'] = body
    if not kw:
        if 'recipient' in params:
            kw['recipient'] = to
        elif 'recipient_email' in params:
            kw['recipient_email'] = to
        elif 'addr' in params:
            kw['addr'] = to

    if kw:
        try:
            return send_email(**kw)
        except TypeError:
            # not supported, fall through to positional tries
            pass
        except Exception as e:
            _raise("send_email raised an exception when called with keyword args", e)

    # try common positional signatures
    attempts = [
        (to, subject, body),
        (subject, body, to),
        (subject, body),
        (to, subject),
    ]
    last_exc = None
    for args in attempts:
        try:
            return send_email(*args)
        except TypeError as e:
            last_exc = e
            continue
        except Exception as e:
            _raise("send_email raised an exception when called positionally", e)

    _raise(f"unable to call send_email; target signature: {sig}", last_exc)

# -----------------------------------------------------------
# Logging and router init
# -----------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
log.info("Employee model loaded: %s", "Yes" if Employee else "No")

router = APIRouter(prefix="/api/leaves", tags=["leaves"])
templates = Jinja2Templates(directory="app/templates")

# -----------------------
# File-based notifications (no DB changes)
# -----------------------
NOTIFS_DIR = Path("data")
NOTIFS_FILE = NOTIFS_DIR / "notifications.json"
_NOTIFS_LOCK = Lock()

NOTIFS_DIR.mkdir(parents=True, exist_ok=True)
if not NOTIFS_FILE.exists():
    NOTIFS_FILE.write_text("[]")

def _load_notifs():
    with _NOTIFS_LOCK:
        try:
            raw = NOTIFS_FILE.read_text()
            return json.loads(raw or "[]")
        except Exception:
            return []

def _save_notifs(items):
    with _NOTIFS_LOCK:
        NOTIFS_FILE.write_text(json.dumps(items, indent=2, default=str))

# -----------------------
# DB Session
# -----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------
# Auth session
# -----------------------
from app.auth.dependencies import get_current_user_payload_or_session

class CurrentUser(BaseModel):
    id: Optional[int]
    role: Optional[str]
    name: Optional[str]

def get_current_user(payload = Depends(get_current_user_payload_or_session)) -> CurrentUser:
    if not payload:
        return CurrentUser(id=None, role=None, name=None)

    return CurrentUser(
        id=payload.get("id") or payload.get("user_id"),
        role=payload.get("role"),
        name=payload.get("name")
    )

# -----------------------
# Pydantic Schemas
# -----------------------
class LeaveCreate(BaseModel):
    leave_type: str
    from_date: date
    to_date: date
    reason: Optional[str] = None

class LeaveOut(BaseModel):
    id: int
    employee_id: int
    leave_type: str
    from_date: Optional[date]
    to_date: Optional[date]
    reason: Optional[str]
    status: str
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None

class NotifyPayload(BaseModel):
    subject: str
    message: str

# -----------------------
# Safe Serializer (returns date-only YYYY-MM-DD)
# -----------------------
def _safe_iso(value):
    """Return YYYY-MM-DD for date/datetime-like values, else string or None."""
    try:
        if value is None:
            return None
        # if it's a date or datetime-like object (has year/month/day)
        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        # fallback
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    except Exception:
        return None

def serialize_leave(l: Leave, db: Session):
    data = {
        "id": l.id,
        "employee_id": l.employee_id,
        "leave_type": l.leave_type,
        "from_date": _safe_iso(getattr(l, "from_date", None)),
        "to_date": _safe_iso(getattr(l, "to_date", None)),
        "reason": l.reason,
        "status": l.status,
        "employee_name": None,
        "employee_email": None,
    }

    if Employee:
        emp = db.query(Employee).filter(Employee.id == l.employee_id).one_or_none()
        if emp:
            data["employee_name"] = getattr(emp, "name", None) or getattr(emp, "full_name", None)
            data["employee_email"] = getattr(emp, "email", None)

    return data

# -----------------------
# API ROUTES
# -----------------------

@router.get("", response_model=List[LeaveOut])
def list_leaves(mine: bool = False, db: Session = Depends(get_db),
                current_user: CurrentUser = Depends(get_current_user)):

    q = db.query(Leave)

    if mine:
        if not current_user.id:
            return []
        q = q.filter(Leave.employee_id == current_user.id)
    else:
        if current_user.role != "admin":
            if not current_user.id:
                return []
            q = q.filter(Leave.employee_id == current_user.id)

    items = q.order_by(Leave.id.desc()).all()
    return [serialize_leave(l, db) for l in items]

@router.post("", response_model=LeaveOut, status_code=201)
def create_leave(payload: LeaveCreate, db: Session = Depends(get_db),
                 current_user: CurrentUser = Depends(get_current_user)):

    if not current_user.id:
        raise HTTPException(status_code=401, detail="Unauthenticated")

    if payload.to_date < payload.from_date:
        raise HTTPException(status_code=400, detail="to_date must be >= from_date")

    # SERVER-SIDE overlap check (authoritative)
    try:
        # consider only leaves that are not Cancelled/Rejected
        conflicting = db.query(Leave).filter(
            Leave.employee_id == current_user.id,
            ~Leave.status.in_(["Cancelled", "Rejected"]),
            # overlap condition: existing.from_date <= new_to AND existing.to_date >= new_from
            and_(
                Leave.from_date <= payload.to_date,
                Leave.to_date >= payload.from_date
            )
        ).order_by(Leave.id.desc()).first()

        if conflicting:
            # descriptive error for client
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Overlapping leave exists",
                    "conflict_id": conflicting.id,
                    "conflict_from": _safe_iso(conflicting.from_date),
                    "conflict_to": _safe_iso(conflicting.to_date),
                    "conflict_status": conflicting.status
                }
            )
    except HTTPException:
        # re-raise known HTTP errors (conflict)
        raise
    except Exception as ex:
        log.exception("Error checking overlapping leaves for user %s: %s", current_user.id, ex)
        # fallback: return 500 so the problem is visible
        raise HTTPException(status_code=500, detail="Server error checking existing leaves")

    # no conflict -> create leave
    leave = Leave(
        employee_id=current_user.id,
        leave_type=payload.leave_type,
        from_date=payload.from_date,
        to_date=payload.to_date,
        reason=payload.reason,
        status="Pending"
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)

    # --- Notify admin by email (Reply-To = employee email) ---
    try:
        emp_name = current_user.name or f"Employee {current_user.id}"

        # get employee email from DB
        emp_email = None
        if Employee:
            emp = db.query(Employee).filter(Employee.id == current_user.id).one_or_none()
            if emp:
                emp_email = getattr(emp, "email", None)

        subject = f"Leave applied by {emp_name} (ID: {current_user.id})"
        body = (
            f"Employee: {emp_name}\n"
            f"Employee ID: {current_user.id}\n"
            f"Leave Type: {leave.leave_type}\n"
            f"From: {leave.from_date}\n"
            f"To: {leave.to_date}\n"
            f"Reason: {leave.reason or '-'}\n"
            f"Status: {leave.status}\n\n"
            f"To approve/reject visit: /leaves (admin panel) or call the API: POST /api/leaves/{leave.id}/approve"
        )

        admin_email = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_USER") or "admin@example.com"
        log.info("About to send admin notification email to %s for leave id=%s (reply-to=%s)", admin_email, leave.id, emp_email)

        # Use send_email directly so we can set reply_to
        send_email(
            to_email=admin_email,
            subject=subject,
            body=body,
            reply_to=emp_email  # <--- critical: set Reply-To to employee email
        )
        log.info("Admin notify result for leave id=%s: sent", leave.id)

    except Exception as e:
        log.exception("Failed to send admin notification email for leave id=%s", leave.id)

    # --- Notify the employee (confirmation email) ---
    try:
        emp_email = None
        if Employee:
            emp = db.query(Employee).filter(Employee.id == current_user.id).one_or_none()
            if emp:
                emp_email = getattr(emp, "email", None)

        if emp_email:
            subject = f"Leave request submitted (#{leave.id})"
            body = (
                f"Hello {emp_name},\n\n"
                f"Your leave request ({leave.leave_type}) from {leave.from_date} to {leave.to_date} has been submitted and is currently {leave.status}.\n\n"
                f"Regards,\nAdmin"
            )
            log.info("About to send confirmation email to employee: %s (leave id=%s)", emp_email, leave.id)
            ok = send_email_with_attachment(emp_email, subject, body)
            log.info("Employee notify result for leave id=%s: %s", leave.id, ok)
    except Exception as e:
        log.exception("Failed to send confirmation email to employee for leave id=%s", leave.id)

    return serialize_leave(leave, db)

def _get_leave(db, leave_id):
    leave = db.query(Leave).filter(Leave.id == leave_id).one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    return leave

def _require_admin(user: CurrentUser):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

@router.post("/{leave_id}/approve", response_model=LeaveOut)
def approve_leave(leave_id: int, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):

    _require_admin(user)
    leave = _get_leave(db, leave_id)
    leave.status = "Approved"
    db.commit()
    db.refresh(leave)

    # notify employee
    try:
        emp_email = None
        emp_name = None
        if Employee:
            emp = db.query(Employee).filter(Employee.id == leave.employee_id).one_or_none()
            if emp:
                emp_email = getattr(emp, "email", None)
                emp_name = getattr(emp, "name", None) or getattr(emp, "full_name", None)

        if emp_email:
            subject = f"Your leave request #{leave.id} has been Approved"
            body = (
                f"Hello {emp_name or ''},\n\n"
                f"Your leave ({leave.leave_type}) from {leave.from_date} to {leave.to_date} has been approved.\n\n"
                f"Regards,\nAdmin"
            )
            log.info("About to send approval email to %s for leave id=%s", emp_email, leave.id)
            ok = send_email_with_attachment(emp_email, subject, body)
            log.info("Approval notify result for leave id=%s: %s", leave.id, ok)
    except Exception as e:
        log.exception("Failed to send approval email for leave id=%s", leave.id)

    return serialize_leave(leave, db)

@router.post("/{leave_id}/reject", response_model=LeaveOut)
def reject_leave(leave_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):

    _require_admin(user)
    leave = _get_leave(db, leave_id)
    leave.status = "Rejected"
    db.commit()
    db.refresh(leave)

    # notify employee
    try:
        emp_email = None
        emp_name = None
        if Employee:
            emp = db.query(Employee).filter(Employee.id == leave.employee_id).one_or_none()
            if emp:
                emp_email = getattr(emp, "email", None)
                emp_name = getattr(emp, "name", None) or getattr(emp, "full_name", None)

        if emp_email:
            subject = f"Your leave request #{leave.id} has been Rejected"
            body = (
                f"Hello {emp_name or ''},\n\n"
                f"Your leave ({leave.leave_type}) from {leave.from_date} to {leave.to_date} was rejected.\n\n"
                f"If you have questions, contact HR.\n\nRegards,\nAdmin"
            )
            log.info("About to send rejection email to %s for leave id=%s", emp_email, leave.id)
            ok = send_email_with_attachment(emp_email, subject, body)
            log.info("Rejection notify result for leave id=%s: %s", leave.id, ok)
    except Exception as e:
        log.exception("Failed to send rejection email for leave id=%s", leave.id)

    return serialize_leave(leave, db)

@router.post("/{leave_id}/cancel", response_model=LeaveOut)
def cancel_leave(leave_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    """
    Cancel a leave:
      - Admin can cancel any leave.
      - Employee can cancel their own leave (owner).
    This function logs helpful debug info and returns clear HTTP errors.
    """
    try:
        log.info("cancel_leave called: leave_id=%s by user.id=%s role=%s name=%s",
                 leave_id, getattr(user, "id", None), getattr(user, "role", None), getattr(user, "name", None))

        leave = _get_leave(db, leave_id)  # raises 404 if not found
        log.info("Found leave: id=%s employee_id=%s status=%s", leave.id, leave.employee_id, leave.status)

        # Allow admin OR the leave owner to cancel
        if user.role == "admin" or (user.id is not None and user.id == leave.employee_id):
            # Optional: only allow cancelling if status is not already Cancelled
            if leave.status == "Cancelled":
                log.info("Leave %s already cancelled", leave_id)
                return serialize_leave(leave, db)

            leave.status = "Cancelled"
            db.commit()
            db.refresh(leave)
            log.info("Leave %s cancelled by user %s (role=%s)", leave_id, user.id, user.role)
            return serialize_leave(leave, db)

        # Not allowed
        log.warning("Cancel forbidden: user.id=%s role=%s not allowed to cancel leave.employee_id=%s",
                    user.id, user.role, leave.employee_id)
        raise HTTPException(status_code=403, detail="Not allowed to cancel this leave")

    except HTTPException:
        # re-raise known HTTP errors
        raise
    except Exception as ex:
        # log full traceback so you can paste it here if something else fails
        log.exception("Unexpected error in cancel_leave for id=%s: %s", leave_id, ex)
        raise HTTPException(status_code=500, detail=f"Server error cancelling leave: {ex}")

# Optional: admin <-> employee custom notify endpoint (both sides)
@router.post("/{leave_id}/notify")
def notify_endpoint(leave_id: int, payload: NotifyPayload, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    """
    If current user is admin -> notify the employee about a leave.
    If current user is the employee who owns the leave -> notify the admin.
    Otherwise -> 403.

    Also persists a message record to data/notifications.json so admin/employee can view/reply later.
    """
    leave = _get_leave(db, leave_id)

    # load employee info (if available)
    emp_email = None
    emp_name = None
    if Employee:
        emp = db.query(Employee).filter(Employee.id == leave.employee_id).one_or_none()
        if emp:
            emp_email = getattr(emp, "email", None)
            emp_name = getattr(emp, "name", None) or getattr(emp, "full_name", None)

    # admin sending to employee
    if user.role == "admin":
        if not emp_email:
            raise HTTPException(status_code=400, detail="Employee has no email on record")
        recipient = emp_email
        display_to = emp_name or emp_email

    # employee sending to admin
    elif user.id == leave.employee_id:
        recipient = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_USER") or None
        if not recipient:
            raise HTTPException(status_code=400, detail="Admin email not configured")
        display_to = "Admin"

    else:
        raise HTTPException(status_code=403, detail="Not allowed to notify for this leave")

    # Build email body
    body = (
        f"Hello {display_to},\n\n"
        f"{payload.message}\n\n"
        f"Regarding leave: id={leave.id}, type={leave.leave_type}, from={leave.from_date}, to={leave.to_date}\n\n"
        "Regards,\n"
        f"{user.name or 'System'}"
    )

    # Persist to file (so messages are available in UI even if email delivery fails)
    try:
        items = _load_notifs()
        next_id = (max((i.get("id", 0) for i in items), default=0) + 1)
        record = {
            "id": next_id,
            "leave_id": leave.id,
            "sender_id": user.id,
            "sender_role": user.role,
            "subject": payload.subject,
            "body": payload.message,
            "is_read": True if user.role == "admin" else False,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        items.append(record)
        _save_notifs(items)
    except Exception as ex:
        log.exception("WARN: failed to append file notification: %s", ex)

    # send email (set Reply-To appropriately)
    try:
        log.info("About to send custom notify email to %s for leave id=%s (from user=%s)", recipient, leave.id, user.name)

        admin_addr = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_USER") or None

        if user.role == "admin":
            # admin -> employee: reply-to should be admin address so employee replies to admin
            reply_target = admin_addr
        else:
            # employee -> admin: reply-to should be the employee's email so admin replies to employee
            reply_target = emp_email

        # call send_email directly to pass reply_to
        send_email(
            to_email=recipient,
            subject=payload.subject,
            body=body,
            reply_to=reply_target
        )
        log.info("Custom notify result for leave id=%s: sent (reply-to=%s)", leave.id, reply_target)
    except Exception as e:
        log.exception("Failed to send custom notify email for leave id=%s", leave.id)
        # keep persisted message (admin can still read it), but surface the error
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")

    return {"ok": True}

@router.get("/{leave_id}/messages")
def leave_messages(leave_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    """
    Return message history for a leave. Admin or the leave owner can view.

    Dev behavior: if the leave does not exist, return an empty list (so the UI doesn't break).
    If you want strict REST semantics, replace the dev branch to raise 404 via _get_leave().
    """
    log.info("GET /api/leaves/%s/messages called by user=%s", leave_id, getattr(user, "id", None))

    # Try to fetch the leave. Dev: return empty list if not found (avoids 404 in UI).
    leave = db.query(Leave).filter(Leave.id == leave_id).one_or_none()
    if not leave:
        log.warning("leave id=%s not found; returning empty messages list (dev mode)", leave_id)
        return []

    # Authorization: admin or owner only
    if user.role != "admin" and user.id != leave.employee_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Load persisted notifications and filter for this leave
    try:
        items = _load_notifs()
        msgs = [i for i in items if int(i.get("leave_id", -1)) == int(leave_id)]
        msgs.sort(key=lambda x: x.get("created_at", ""))
    except Exception as ex:
        log.exception("Failed to load messages for leave id=%s: %s", leave_id, ex)
        # Fail gracefully: return empty list if something goes wrong reading the file
        msgs = []

    return msgs

# -----------------------
# Notifications endpoints (file-based)
# -----------------------
@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    """Return unread notifications for admin."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    items = _load_notifs()
    unread = [i for i in items if not i.get("is_read", False)]
    unread.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return unread

@router.post("/notifications/{notif_id}/mark_read")
def mark_notification_read(notif_id: int, db: Session = Depends(get_db),
                           user: CurrentUser = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    items = _load_notifs()
    found = False
    for i in items:
        if int(i.get("id")) == int(notif_id):
            i["is_read"] = True
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Not found")
    _save_notifs(items)
    return {"ok": True}

# Template route inclusion helper (used by app.main to mount the UI)
def include_template_route(app: FastAPI):

    @app.get("/leaves")
    async def leaves_page(request: Request,
                          current_user: CurrentUser = Depends(get_current_user)):

        return templates.TemplateResponse(
            "leaves.html",
            {
                "request": request,
                "role": current_user.role or "employee",
                "user_name": current_user.name or "",
                "user_id": current_user.id or ""
            }
        )

@router.get("/admin/summary")
def leaves_summary(db: Session = Depends(get_db)):
    try:
        total = db.execute("SELECT COUNT(*) FROM leaves").scalar() or 0
    except:
        total = 0
    return {"total": total}
