# app/auth/jwt_handler.py
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os


# IMPORTANT: change this secret in production and don't hardcode in code
SECRET_KEY = os.environ.get("JWT_SECRET", "devsecret123")

ALGORITHM = "HS256"

def create_access_token(payload: Dict[str, Any], expires_minutes: int = 120) -> str:
    """
    Create a JWT token with an 'exp' claim.
    payload should be a dict (e.g. {"sub": user_id, "role": "admin"})
    """
    to_encode = payload.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # PyJWT returns str in v2+, bytes in older versions — ensure str
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token

# backward-compatible alias
create_token = create_access_token


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT token. Returns the payload dict on success, otherwise None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        # token expired
        return None
    except jwt.InvalidTokenError:
        # invalid token
        return None

# backward-compatible alias
verify_token = decode_jwt