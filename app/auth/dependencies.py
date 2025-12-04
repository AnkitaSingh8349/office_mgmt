# app/auth/dependencies.py
from typing import Dict, Any, Optional, List, Callable, Iterable
from fastapi import Header, HTTPException, Depends, Request
from jose import jwt, JWTError
import logging
from types import SimpleNamespace

# DB imports
from sqlalchemy.orm import Session
from app.database import get_db
from app.employees.models import Employee as EmployeeModel

logger = logging.getLogger(__name__)
# you can configure logging level in your app entrypoint; for debug use logger.setLevel(logging.DEBUG)

# Use env in production; this is for demo / dev
SECRET_KEY = "my_ultra_secret_key_123"
ALGORITHM = "HS256"


# -------------------------------------------
# Helper: Extract Bearer token safely
# -------------------------------------------
def _extract_bearer(auth_header: Optional[str]) -> Optional[str]:
    """
    Extract bearer token from Authorization header.
    Returns None if header missing or malformed.
    """
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


# -------------------------------------------
# Strict JWT-only dependency (API use)
# -------------------------------------------
def get_current_user_payload(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# -------------------------------------------
# JWT OR Session fallback login
# -------------------------------------------
def get_current_user_payload_or_session(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Tries, in order:
      1) Authorization: Bearer <token>
      2) Cookie named 'session' (if you store JWT there)
      3) Server-side request.session (SessionMiddleware)
    Returns payload dict or raises 401 if none valid.
    """
    # 1) Try Authorization header (Bearer)
    token = _extract_bearer(authorization)
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            logger.debug("Authenticated via JWT header: user_id=%s payload=%s", payload.get("user_id") or payload.get("id"), {k: payload.get(k) for k in ("user_id", "id", "role", "name")})
            return payload
        except JWTError:
            logger.warning("Invalid/expired header token, falling back to cookie/session...")

    # 2) Try cookie named 'session' (client-side cookie set by login)
    try:
        cookie_token = request.cookies.get("session")
    except Exception:
        cookie_token = None

    if cookie_token:
        try:
            payload = jwt.decode(cookie_token, SECRET_KEY, algorithms=[ALGORITHM])
            logger.debug("Authenticated via JWT cookie: user_id=%s payload=%s", payload.get("user_id") or payload.get("id"), {k: payload.get(k) for k in ("user_id", "id", "role", "name")})
            return payload
        except JWTError:
            logger.warning("Invalid/expired cookie token, falling back to server session...")

    # 3) Try server-side session object (if you use SessionMiddleware)
    session_data = getattr(request, "session", None)
    if session_data:
        user_id = session_data.get("user_id")
        if user_id:
            payload = {
                "user_id": int(user_id),
                "id": int(user_id),
                "name": session_data.get("name", ""),
                "role": session_data.get("role", "employee")
            }
            logger.debug("Authenticated via SERVER SESSION: user_id=%s role=%s", payload["user_id"], payload["role"])
            return payload

    # nothing valid found
    raise HTTPException(status_code=401, detail="Not authenticated. Please login.")


# -------------------------------------------
# Resolve payload -> real DB user (single source of truth)
# -------------------------------------------
def get_current_user(
    payload: Dict[str, Any] = Depends(get_current_user_payload_or_session),
    db: Session = Depends(get_db)
):
    """
    Resolve the payload -> database user.
    Returns the ORM user object (EmployeeModel) or raises 401 if not found.
    This is safer than trusting the payload.role/id values.
    """
    # payload may contain id or user_id or sub
    user_id = payload.get("id") or payload.get("user_id") or payload.get("sub") or payload.get("uid")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid auth payload: missing user id")

    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user id in payload")

    # fetch user from DB (single source of truth)
    user = db.query(EmployeeModel).filter(EmployeeModel.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # debug log to help you confirm which user is returned
    try:
        logger.info("get_current_user -> id=%s role=%s name=%s", getattr(user, "id", None), getattr(user, "role", None), getattr(user, "name", None))
    except Exception:
        pass

    # return the ORM user object; routes can access .id .role .name
    return user


# -------------------------------------------
# Role check that returns the user object (not raw payload)
# Usage: Depends(require_role(["admin"])) or Depends(require_role(["employee"]))
# -------------------------------------------
def require_role(allowed_roles: Iterable[str]) -> Callable:
    def dependency(user = Depends(get_current_user)):
        role = getattr(user, "role", None)
        if not role or str(role).lower() not in [str(r).lower() for r in allowed_roles]:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return dependency


# -------------------------------------------
# Alias kept for compatibility
# -------------------------------------------
def require_role_or_session(allowed_roles: List[str]) -> Callable:
    return require_role(allowed_roles)
