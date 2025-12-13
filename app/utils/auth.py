# app/utils/auth.py
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict
import jwt
import os

security = HTTPBearer()

# Use environment variable if you have one, otherwise default for dev.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_change_me")
ALGORITHM = "HS256"

def verify_token(token: str) -> Dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Minimal dependency that returns {'id': <user_id>, 'role': '<role>'}
    Expects JWT payload to contain 'sub' (user id) and 'role'.
    If you use session cookies instead, replace this with your session logic.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload.get("sub")
    role = payload.get("role", "employee")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return {"id": user_id, "role": role}
