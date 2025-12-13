# app/auth/jwt_handler.py
# Uses python-jose to create/verify JWTs (compatible with dependencies.py)
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from jose import jwt, JWTError

# Read secret from env (keep in sync with SessionMiddleware secret for dev/migration)
JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("SESSION_SECRET", "devsecret123"))
ALGORITHM = "HS256"

def create_access_token(payload: Dict[str, Any], expires_minutes: int = 120) -> str:
    """
    Create a JWT token with an 'exp' claim.
    payload: a dict, e.g. {"sub": "4", "user_id": 4, "role": "employee"}
    Returns a JWT string.
    """
    to_encode = payload.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    # python-jose returns str
    return token

def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT token. Returns payload dict on success, otherwise None.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
