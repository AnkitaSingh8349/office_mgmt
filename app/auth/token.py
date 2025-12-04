# app/auth/token.py
"""
Development-only token endpoint.
Accepts any username/email/password and returns a JWT access token.
WARNING: This bypasses authentication checks and is insecure. Use only locally.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel
import jwt

# Keep DB import if your project expects it (not used by this dev flow)
from sqlalchemy.orm import Session
try:
    from app.database import get_db
except Exception:
    # If get_db is not available for any reason, provide a dummy dependency.
    def get_db():
        yield None

# JWT settings (pick a secret for dev; change for production)
SECRET_KEY = "dev-secret-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7   # 7 days (or any duration you want)



router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class TokenResponse(BaseModel):
    access: str
    token_type: str = "bearer"
    expires_in: int


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token with an expiry time.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # PyJWT returns str in recent versions; ensure str
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def authenticate_allow_any(identifier: str, password: str):
    """
    Development helper: accept any identifier (email/username) and return a fake user dict.
    This does not check the database and should be removed for real authentication.
    """
    # Use id 0 for dev user; you may change this to something else if needed.
    return {"id": 0, "username": identifier, "email": identifier}


@router.post("/token", response_model=TokenResponse)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)  # kept only to match function signature elsewhere
):
    """
    Development login endpoint.
    Accepts form data (x-www-form-urlencoded): username and password.
    Returns a JWT token for any username/email provided.
    """
    # Build a fake user object using the identifier the client provided
    user = authenticate_allow_any(form_data.username, form_data.password)

    access_token = create_access_token(
        data={
            "sub": str(user["id"]),
            "username": user["username"],
            "email": user["email"],
        }
    )

    return {
        "access": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
def read_current_user(token: str = Depends(oauth2_scheme)):
    """
    Decode the token and return its payload. This is a convenience endpoint to verify token contents.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user": payload}
    except Exception:
        return {"detail": "Invalid or expired token"}
