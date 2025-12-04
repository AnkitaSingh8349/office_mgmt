# app/auth/auth_router.py
from fastapi import APIRouter
from app.auth.login import router as login_router
from app.auth.signup import router as signup_router
from app.auth.logout import router as logout_router
from app.auth.me import router as me_router   # <- add this

auth_router = APIRouter()

# All auth routes under /auth prefix
auth_router.include_router(login_router, prefix="/auth")
auth_router.include_router(signup_router, prefix="/auth")
auth_router.include_router(logout_router, prefix="/auth")
auth_router.include_router(me_router, prefix="/auth")   # <- include /auth/me

app.include_router(dashboard_router, prefix="/leaves")
