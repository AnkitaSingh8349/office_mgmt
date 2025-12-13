"""
FastAPI router for /api/profile that reads/writes from the `employee1` table.

Notes:
- This file expects an SQLAlchemy/SQLModel `Employee` model in app.employees.models.
- It uses your real dependencies from app.auth.dependencies: get_db and get_current_user.
- The router prefix is set to "/profile" so when mounted with prefix="/api" in main.py
  the final endpoints become /api/profile/me (GET, PUT).
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime

# ---------- Real dependencies (no placeholders) ----------
from app.auth.dependencies import get_db, get_current_user

# ---------- Import your ORM model ----------
from app.employees.models import Employee as Employee1

# Router prefix intentionally set to "/profile".
# main.py should include this router with prefix="/api" so final path is /api/profile/me
router = APIRouter(prefix="/profile", tags=["profile"])
logger = logging.getLogger(__name__)


class ProfileUpdate(BaseModel):
    basic: Optional[Dict[str, Optional[str]]] = None
    personal: Optional[Dict[str, Optional[str]]] = None
    identity: Optional[Dict[str, Optional[str]]] = None
    contact: Optional[Dict[str, Optional[str]]] = None
    payment: Optional[Dict[str, Optional[str]]] = None


def _coerce_to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


def _extract_flat_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept nested (basic/personal/...) or flat payload and return a flat dict of non-empty strings.
    """
    out: Dict[str, Any] = {}
    for sec in ("basic", "personal", "identity", "contact", "payment"):
        section = payload.get(sec) or {}
        if isinstance(section, dict):
            for k, v in section.items():
                s = _coerce_to_str(v)
                if s is not None:
                    out[k] = s

    # accept top-level flat keys too
    for k, v in payload.items():
        if k in ("basic", "personal", "identity", "contact", "payment"):
            continue
        s = _coerce_to_str(v)
        if s is not None:
            out[k] = s

    return out


def _profile_to_grouped(emp) -> Dict[str, Dict[str, Optional[str]]]:
    """Convert Employee1 ORM instance to grouped dict for frontend consumption."""
    def _get(a):
        return getattr(emp, a, None) if emp is not None else None

    return {
        "basic": {
            "first_name": _get("first_name"),
            "last_name": _get("last_name"),
            "personal_phone": _get("personal_phone"),
            "birthday": _get("birthday"),
            "present_address": _get("present_address"),
            "permanent_address": _get("permanent_address"),
        },
        "personal": {
            "gender": _get("gender"),
            "marital_status": _get("marital_status"),
            "father_name": _get("father_name"),
            "linkedin_url": _get("linkedin_url"),
        },
        "identity": {
            "uan": _get("uan"),
            "pan": _get("pan"),
            "aadhar": _get("aadhar"),
        },
        "contact": {
            "personal_email": _get("personal_email"),
            "personal_mobile": _get("personal_mobile"),
            "seating_location": _get("seating_location"),
        },
        "payment": {
            "bank_account_no": _get("bank_account_no"),
            "bank_name": _get("bank_name"),
            "ifsc_code": _get("ifsc_code"),
            "account_type": _get("account_type"),
            "payment_mode": _get("payment_mode"),
        }
    }


def _parse_date_like(val: str) -> Optional[str]:
    """Normalize incoming date strings to YYYY-MM-DD (string). Returns original if unparseable."""
    if not val:
        return None
    v = str(val).strip()
    # If already in YYYY-MM-DD
    try:
        if len(v) >= 10 and v[4] == '-' and v[7] == '-':
            # Quick validation
            _ = datetime.strptime(v[:10], "%Y-%m-%d")
            return v[:10]
    except Exception:
        pass

    # Try common formats
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(v, fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue

    # last-resort: return original trimmed string
    return v


@router.get("/me")
def get_my_profile(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    emp = db.query(Employee1).filter(Employee1.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")

    return _profile_to_grouped(emp)


@router.put("/me")
def update_my_profile(payload: ProfileUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    emp = db.query(Employee1).filter(Employee1.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")

    raw_payload = payload.dict(exclude_none=True)
    flat = _extract_flat_from_payload(raw_payload)

    if not flat:
        # Nothing to update — return current grouped profile
        return _profile_to_grouped(emp)

    # map incoming keys to model attribute names if your DB columns differ
    key_map: Dict[str, str] = {
        # example: "mobile": "personal_mobile",
        # add mappings here if your DB columns have different names
    }

    changed = False
    try:
        for k, v in flat.items():
            if k == "birthday":
                v = _parse_date_like(v)
            attr = key_map.get(k, k)
            # only update attributes that exist on the model
            if hasattr(emp, attr):
                old = getattr(emp, attr)
                # SQLAlchemy may store dates as date/datetime objects — convert to string for comparison
                if isinstance(old, (datetime,)):
                    old_cmp = old.strftime("%Y-%m-%d")
                else:
                    old_cmp = old
                if old_cmp != v:
                    setattr(emp, attr, v)
                    changed = True
            else:
                # ignore unknown keys silently (could log)
                logger.debug("Ignoring unknown profile key: %s", k)

        if changed:
            db.add(emp)
            db.commit()
            db.refresh(emp)

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error while updating profile")
        raise HTTPException(status_code=500, detail="Database error")

    return _profile_to_grouped(emp)
