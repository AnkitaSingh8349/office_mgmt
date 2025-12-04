# app/leaves/router.py
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.leaves.models import Leave

# Optional employee model
try:
    from app.employee.models import Employee
except:
    Employee = None

router = APIRouter(prefix="/api/leaves", tags=["leaves"])
templates = Jinja2Templates(directory="app/templates")


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


# -----------------------
# Safe Serializer (Fixes 500 error)
# -----------------------
def _safe_iso(value):
    """Fix for 500 error when DB stores dates as strings."""
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    except:
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
        "employee_name": None
    }

    if Employee:
        emp = db.query(Employee).filter(Employee.id == l.employee_id).one_or_none()
        if emp:
            data["employee_name"] = getattr(emp, "name", None) or getattr(emp, "full_name", None)

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
    return serialize_leave(leave, db)


@router.post("/{leave_id}/reject", response_model=LeaveOut)
def reject_leave(leave_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):

    _require_admin(user)
    leave = _get_leave(db, leave_id)
    leave.status = "Rejected"
    db.commit()
    db.refresh(leave)
    return serialize_leave(leave, db)


@router.post("/{leave_id}/cancel", response_model=LeaveOut)
def cancel_leave(leave_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):

    leave = _get_leave(db, leave_id)

    if user.role != "admin" and user.id != leave.employee_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    leave.status = "Cancelled"
    db.commit()
    db.refresh(leave)
    return serialize_leave(leave, db)


# -----------------------
# TEMPLATE ROUTE (/leaves)
# -----------------------
from fastapi import FastAPI

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
