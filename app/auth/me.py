# app/auth/me.py
from fastapi import APIRouter, Depends
from typing import Dict, Any

from app.auth.dependencies import get_current_user_payload_or_session

router = APIRouter()

@router.get("/me", response_model=Dict[str, Any])
def read_me(payload: Dict[str, Any] = Depends(get_current_user_payload_or_session)):
    """
    Return a small user payload. Accepts either a Bearer JWT or session cookie.
    """
    return {
        "id": int(payload.get("id") or payload.get("user_id") or payload.get("sub")),
        "name": payload.get("name", ""),
        "role": payload.get("role", "employee")
    }
