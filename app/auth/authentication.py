# app/auth/authentication.py

from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.database import get_db
from app.employees.models import Employee

# -----------------------------
# YOUR JWT CONFIG (local secret)
# -----------------------------
import os

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SESSION_SECRET", "devsecret123"))
ALGORITHM = "HS256"


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Works with BOTH:
      - JWT cookie named 'session'
      - request.session fallback (your login.py uses this)
    """

    # 1) Try JWT cookie
    token = request.cookies.get("session")

    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
            user_id = payload.get("user_id") or payload.get("sub")

            if user_id:
                user = db.query(Employee).filter(Employee.id == int(user_id)).first()
                if user:
                    return user

        except JWTError:
            pass  # go to session fallback

    # 2) Try server-side session (login.py sets this)
    try:
        user_id = request.session.get("user_id")
        if user_id:
            user = db.query(Employee).filter(Employee.id == int(user_id)).first()
            if user:
                return user
    except Exception:
        pass

    return None


def admin_required(current_user = Depends(get_current_user)):
    """
    Only allow admin users.
    """
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def login_required(current_user = Depends(get_current_user)):
    """
    Normal authenticated users.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Please login")
    return current_user
