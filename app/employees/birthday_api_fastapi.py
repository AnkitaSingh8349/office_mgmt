# app/employees/birthday_api_fastapi.py

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback
import logging

from sqlmodel import Session, select
from app.database import engine
from app.employees.models import Employee
from app.employees.wishes import BirthdayWish
from app.utils.email_service import send_email

logger = logging.getLogger("birthday_router")

router = APIRouter(prefix="/employees", tags=["Employees - Birthdays"])

@router.get("/birth_email.html")
def serve_birth_email():
    path = os.path.join(os.getcwd(), "static", "birth_email.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Not Found")

# create wishes table
try:
    BirthdayWish.metadata.create_all(bind=engine)
except Exception:
    pass


def is_leap_year(y: int) -> bool:
    return (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))


def _get_current_user_id(request: Request):
    try:
        sess = dict(request.session)
        if "user_id" in sess:
            return int(sess["user_id"])
    except:
        pass
    if "uid" in request.query_params:
        return int(request.query_params["uid"])
    return None


@router.get("/birthdays/today_pandas")
def todays_birthdays_pandas(request: Request):
    try:
        user_id = _get_current_user_id(request)

        tz = ZoneInfo("Asia/Kolkata")
        today = datetime.now(tz).date()
        tm = today.month
        td = today.day

        with Session(engine) as session:
            stmt = select(Employee.id, Employee.name, Employee.birthday, Employee.email)
            rows = session.exec(stmt).all()

            stmt_wish = select(BirthdayWish)
            all_wishes = session.exec(stmt_wish).all()

        wishes_by_recipient = {}

        for w in all_wishes:
            if not w.created_at:
                continue

            created = w.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=ZoneInfo("UTC"))
            created_local = created.astimezone(tz)

            if created_local.date() != today:
                continue

            wishes_by_recipient.setdefault(w.recipient_id, []).append({
                "wish_id": w.id,
                "sender_id": w.sender_id,
                "created_at": w.created_at.isoformat(),
            })

        birthdays = []
        you = None

        for row in rows:
            eid, name, bday, email = row

            if not bday:
                continue

            b_month = bday.month
            b_day = bday.day

            is_today = (b_month == tm and b_day == td)

            if tm == 2 and td == 28 and not is_leap_year(today.year):
                if b_month == 2 and b_day == 29:
                    is_today = True

            if is_today:
                birthdays.append({
                    "id": eid,
                    "name": name,
                    "email": email,
                    "wishes_today": wishes_by_recipient.get(eid, [])
                })

                if user_id == eid:
                    you = {"id": eid, "name": name}

        return {
            "date": today.isoformat(),
            "birthdays": birthdays,
            "is_your_birthday": bool(you is not None),
            "you": you
        }

    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/birthdays/send/{emp_id}")
def send_birthday_email(emp_id: int, request: Request, background: BackgroundTasks):
    """
    Employee clicks WISH button → This API sends email + stores wish.
    """
    try:
        sender_id = _get_current_user_id(request)

        with Session(engine) as session:
            emp = session.get(Employee, emp_id)
            if not emp:
                raise HTTPException(status_code=404, detail="Employee not found")
            if not emp.email:
                raise HTTPException(status_code=400, detail="Employee has no email")

        subject = f"🎉 Happy Birthday, {emp.name}!"
        body = (
            f"Dear {emp.name},\n\n"
            f"Wishing you a very Happy Birthday! 🎉\n\n"
            "Best Regards,\nAJX Technologies"
        )

        def bg_send():
            try:
                send_email(emp.email, subject, body)
            except Exception:
                logger.exception("Email send failed")

            try:
                with Session(engine) as session:
                    wish = BirthdayWish(
                        sender_id=sender_id,
                        recipient_id=emp_id,
                        message="Sent via employee portal"
                    )
                    session.add(wish)
                    session.commit()
            except Exception:
                logger.exception("Wish save failed")

        background.add_task(bg_send)

        return {"status": "queued", "to": emp.email}

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/birthdays/wishes/today")
def todays_wishes(request: Request):
    """
    Admin view: All wishes sent today.
    """
    try:
        tz = ZoneInfo("Asia/Kolkata")
        today = datetime.now(tz).date()

        with Session(engine) as session:
            stmt = select(BirthdayWish)
            all_wishes = session.exec(stmt).all()

            emp_ids = set()
            todays = []

            for w in all_wishes:
                if not w.created_at:
                    continue
                created = w.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=ZoneInfo("UTC"))
                if created.astimezone(tz).date() != today:
                    continue

                todays.append(w)
                emp_ids.add(w.sender_id)
                emp_ids.add(w.recipient_id)

            emp_map = {}
            if emp_ids:
                stmt2 = select(Employee.id, Employee.name).where(Employee.id.in_(emp_ids))
                for eid, name in session.exec(stmt2).all():
                    emp_map[eid] = name

        out = []
        for w in todays:
            out.append({
                "wish_id": w.id,
                "sender_id": w.sender_id,
                "sender_name": emp_map.get(w.sender_id),
                "recipient_id": w.recipient_id,
                "recipient_name": emp_map.get(w.recipient_id),
                "created_at": w.created_at.isoformat()
            })

        return {"date": today.isoformat(), "wishes": out}

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))
