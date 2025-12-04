# app/auth/logout.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

def _make_logout_response():
    # redirect target after logout
    resp = RedirectResponse(url="/auth/login", status_code=303)
    # delete the cookie your login sets (your login uses key="session")
    resp.delete_cookie("session", path="/")
    return resp

@router.get("/logout")
@router.get("/logout/")
@router.get("/auth/logout")
@router.get("/auth/logout/")
async def logout_get(request: Request):
    # clear server-side session if present
    try:
        request.session.clear()
    except Exception:
        pass
    return _make_logout_response()

@router.post("/logout")
@router.post("/logout/")
@router.post("/auth/logout")
@router.post("/auth/logout/")
async def logout_post(request: Request):
    try:
        request.session.clear()
    except Exception:
        pass
    return _make_logout_response()
