# app/salary/router.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from datetime import datetime
from functools import wraps
import traceback
import os
import re

from pathlib import Path
import shutil
from calendar import monthrange

# For robust text matching in attendance helpers
from sqlalchemy import func, String
from sqlalchemy.sql import cast

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.employees.models import Employee as User
from app.salary.models import Salary
from app.utils.pdf_generator import generate_and_save_pdf, SALARY_DIR

router = APIRouter()

# Templates directory (app/templates)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ---------- Optional Attendance model imports ----------
POTENTIAL_ATTENDANCE_MODULES = [
    "app.attendance.models",
    "app.attendance1.models",
    "attendance.models",
    "attendance1.models",
]
ATTENDANCE_MODELS = []

for mod in POTENTIAL_ATTENDANCE_MODULES:
    try:
        imported = __import__(mod, fromlist=["Attendance"])
        model = getattr(imported, "Attendance", None)
        if model is None:
            model = getattr(imported, "Attendance1", None)
        if model is not None:
            ATTENDANCE_MODELS.append(model)
            print(f"DEBUG: Imported attendance model from {mod}")
    except Exception as e:
        print(f"DEBUG: Could not import attendance module {mod}: {e}")

print("DEBUG: ATTENDANCE_MODELS found:", [m.__module__ + "." + m.__name__ for m in ATTENDANCE_MODELS])


# Debug wrapper (returns stacktrace in response for dev)
def show_exceptions_for_dev(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            tb = traceback.format_exc()
            print("=== ERROR IN SALARY ROUTE ===\n", tb)
            return PlainTextResponse(tb, status_code=500)
    return wrapper


# Ensure SALARY_DIR is Path and exists
if not isinstance(SALARY_DIR, Path):
    SALARY_DIR = Path(SALARY_DIR)
SALARY_DIR.mkdir(parents=True, exist_ok=True)


# -------------------- helpers --------------------
def month_range_from_ym(ym: str):
    if not ym:
        return None, None
    try:
        norm = str(ym).strip().replace("_", "-")
        parts = norm.split("-")
        if len(parts) >= 2 and len(parts[0]) == 4 and parts[1].isdigit():
            year = parts[0]
            month = parts[1]
        else:
            if len(norm) == 6 and norm.isdigit():
                year = norm[:4]
                month = norm[4:]
            else:
                return None, None
        y = int(year)
        m = int(month)
        start = datetime(y, m, 1).date()
        last_day = monthrange(y, m)[1]
        end = datetime(y, m, last_day).date()
        return start, end
    except Exception:
        return None, None


def get_or_create_salary_slip(db: Session, employee_id: int, month: str):
    salary = db.query(Salary).filter(
        Salary.employee_id == employee_id,
        Salary.month == month
    ).first()

    was_created = False
    if not salary:
        salary = Salary(
            employee_id=employee_id,
            month=month,
            created_at=datetime.utcnow()
        )
        db.add(salary)
        db.commit()
        db.refresh(salary)
        was_created = True

    employee = db.query(User).filter(User.id == employee_id).first()
    if not employee:
        raise ValueError("Employee not found")

    pdf_path = generate_and_save_pdf(employee, salary)
    if isinstance(pdf_path, str):
        pdf_path = Path(pdf_path)
    return pdf_path, was_created


# (Attendance helpers unchanged — kept for compatibility)
def _accumulate_counts_from_model(db: Session, model, s, start_date, end_date):
    present_cnt = None
    explicit_absent_cnt = None
    total_rows_cnt = None
    try:
        if hasattr(model, "date") and hasattr(model, "status"):
            lowered = func.lower(cast(model.status, String))
            present_filter = (lowered.like("%pres%")) | (lowered.in_(["p", "1", "present", "yes", "true"]))
            absent_filter = (lowered.like("%abs%")) | (lowered.in_(["a", "0", "absent", "no", "false"]))

            present_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date,
                present_filter
            )
            absent_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date,
                absent_filter
            )
            total_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date
            )
            present_cnt = present_q.count()
            explicit_absent_cnt = absent_q.count()
            total_rows_cnt = total_q.count()

            if explicit_absent_cnt == 0 and total_rows_cnt and present_cnt is not None:
                inferred = max(0, total_rows_cnt - present_cnt)
                if inferred:
                    explicit_absent_cnt = inferred

            return present_cnt, explicit_absent_cnt, total_rows_cnt

        if hasattr(model, "date") and hasattr(model, "present"):
            present_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date,
                model.present == True
            )
            absent_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date,
                model.present == False
            )
            total_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date
            )
            present_cnt = present_q.count()
            explicit_absent_cnt = absent_q.count()
            total_rows_cnt = total_q.count()

            if explicit_absent_cnt == 0 and total_rows_cnt and present_cnt is not None:
                explicit_absent_cnt = max(0, total_rows_cnt - present_cnt)

            return present_cnt, explicit_absent_cnt, total_rows_cnt

        if hasattr(model, "month") and hasattr(model, "status"):
            lowered = func.lower(cast(model.status, String))
            present_filter = (lowered.like("%pres%")) | (lowered.in_(["p", "1", "present", "yes", "true"]))
            absent_filter = (lowered.like("%abs%")) | (lowered.in_(["a", "0", "absent", "no", "false"]))

            present_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.month == getattr(s, "month", ""),
                present_filter
            )
            absent_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.month == getattr(s, "month", ""),
                absent_filter
            )
            total_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.month == getattr(s, "month", "")
            )
            present_cnt = present_q.count()
            explicit_absent_cnt = absent_q.count()
            total_rows_cnt = total_q.count()

            if explicit_absent_cnt == 0 and total_rows_cnt and present_cnt is not None:
                explicit_absent_cnt = max(0, total_rows_cnt - present_cnt)

            return present_cnt, explicit_absent_cnt, total_rows_cnt

        if hasattr(model, "date"):
            total_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.date >= start_date,
                model.date <= end_date
            )
            total_rows_cnt = total_q.count()
            if hasattr(model, "present"):
                present_q = db.query(model).filter(
                    model.employee_id == s.employee_id,
                    model.date >= start_date,
                    model.date <= end_date,
                    model.present == True
                )
                present_cnt = present_q.count()
                explicit_absent_cnt = max(0, total_rows_cnt - present_cnt)
            else:
                present_cnt = total_rows_cnt
                explicit_absent_cnt = 0
            return present_cnt, explicit_absent_cnt, total_rows_cnt
    except Exception as e:
        print(f"DEBUG(_accumulate_counts): error querying model {model}: {e}")

    return present_cnt, explicit_absent_cnt, total_rows_cnt


def _accumulate_counts_from_model_monthfield(db: Session, model, s):
    present_cnt = None
    explicit_absent_cnt = None
    total_rows_cnt = None
    try:
        if hasattr(model, "month"):
            total_q = db.query(model).filter(
                model.employee_id == s.employee_id,
                model.month == getattr(s, "month", "")
            )
            total_rows_cnt = total_q.count()
            if hasattr(model, "status"):
                lowered = func.lower(cast(model.status, String))
                present_filter = (lowered.like("%pres%")) | (lowered.in_(["p", "1", "present", "yes", "true"]))
                absent_filter = (lowered.like("%abs%")) | (lowered.in_(["a", "0", "absent", "no", "false"]))

                present_q = db.query(model).filter(
                    model.employee_id == s.employee_id,
                    model.month == getattr(s, "month", ""),
                    present_filter
                )
                absent_q = db.query(model).filter(
                    model.employee_id == s.employee_id,
                    model.month == getattr(s, "month", ""),
                    absent_filter
                )
                present_cnt = present_q.count()
                explicit_absent_cnt = absent_q.count()
            elif hasattr(model, "present"):
                present_q = db.query(model).filter(
                    model.employee_id == s.employee_id,
                    model.month == getattr(s, "month", ""),
                    model.present == True
                )
                absent_q = db.query(model).filter(
                    model.employee_id == s.employee_id,
                    model.month == getattr(s, "month", ""),
                    model.present == False
                )
                present_cnt = present_q.count()
                explicit_absent_cnt = absent_q.count()
            else:
                present_cnt = total_rows_cnt
                explicit_absent_cnt = 0

            if explicit_absent_cnt == 0 and total_rows_cnt and present_cnt is not None:
                explicit_absent_cnt = max(0, total_rows_cnt - present_cnt)
    except Exception as e:
        print(f"DEBUG(_accumulate_counts_monthfield): error querying model {model}: {e}")

    return present_cnt, explicit_absent_cnt, total_rows_cnt


def build_rows(db: Session, salaries):
    rows = []
    total_attendance = 0
    total_absent = 0

    print("DEBUG(build_rows): Attendance models present?", [m.__name__ for m in ATTENDANCE_MODELS])

    for s in salaries:
        emp = getattr(s, "employee", None)
        if emp is None:
            try:
                emp = db.query(User).filter(User.id == s.employee_id).first()
            except Exception:
                emp = None

        # prefer stored counts
        attend_count = None
        absent_count = None
        for name in ("attend", "attendance", "attend_count", "attendance_count"):
            if hasattr(s, name):
                try:
                    attend_count = int(getattr(s, name) or 0)
                except Exception:
                    attend_count = 0
                break
        for name in ("absent", "absent_count"):
            if hasattr(s, name):
                try:
                    absent_count = int(getattr(s, name) or 0)
                except Exception:
                    absent_count = 0
                break

        # compute from attendance models if needed (unchanged)
        if (attend_count is None or absent_count is None) and ATTENDANCE_MODELS:
            start_date, end_date = month_range_from_ym(getattr(s, "month", "") or "")
            present_sum = 0
            explicit_absent_sum = 0
            total_rows_sum = 0
            any_data = False

            if start_date and end_date:
                for model in ATTENDANCE_MODELS:
                    pres, abs_explicit, total_rows = _accumulate_counts_from_model(db, model, s, start_date, end_date)
                    if pres is not None:
                        any_data = True
                        present_sum += int(pres)
                    if abs_explicit is not None:
                        any_data = True
                        explicit_absent_sum += int(abs_explicit)
                    if total_rows is not None:
                        any_data = True
                        total_rows_sum += int(total_rows)
            else:
                for model in ATTENDANCE_MODELS:
                    pres, abs_explicit, total_rows = _accumulate_counts_from_model_monthfield(db, model, s)
                    if pres is not None:
                        any_data = True
                        present_sum += int(pres)
                    if abs_explicit is not None:
                        any_data = True
                        explicit_absent_sum += int(abs_explicit)
                    if total_rows is not None:
                        any_data = True
                        total_rows_sum += int(total_rows)

            if any_data:
                if present_sum is not None and explicit_absent_sum is not None:
                    attend_count = int(present_sum)
                    absent_count = int(explicit_absent_sum)
                elif present_sum is not None and total_rows_sum:
                    attend_count = int(present_sum)
                    absent_count = max(0, int(total_rows_sum) - int(present_sum))
                elif present_sum is not None:
                    attend_count = int(present_sum)
                    absent_count = 0
                elif explicit_absent_sum is not None:
                    absent_count = int(explicit_absent_sum)
                    if total_rows_sum:
                        attend_count = max(0, int(total_rows_sum) - int(explicit_absent_sum))
                    else:
                        attend_count = 0

        if attend_count is None:
            attend_count = 0
        if absent_count is None:
            absent_count = 0

        try:
            a = int(attend_count)
        except Exception:
            a = 0
        try:
            b = int(absent_count)
        except Exception:
            b = 0

        total_attendance += a
        total_absent += b

        rows.append({
            "salary": s,
            "employee": emp,
            "attendance_count": a,
            "absent_count": b
        })

    print(f"DEBUG(build_rows): total_attendance={total_attendance}, total_absent={total_absent}, rows={len(rows)}")
    return rows, total_attendance, total_absent


# ------------------------- SALARY LIST VIEW -------------------------
@router.get("/salary")
@show_exceptions_for_dev
def salary_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Employee => show only their own salaries.
    Admin => show all salaries.
    """
    # Normalize current_user attributes (works for ORM or SimpleNamespace)
    try:
        user_id = int(getattr(current_user, "id", None))
    except Exception:
        user_id = None

    # ----------------- CHANGED: robust admin detection -----------------
    is_admin = False
    try:
        # prefer boolean flags if present, fall back to 'role' string
        if getattr(current_user, "is_admin", False) or getattr(current_user, "is_staff", False):
            is_admin = True
        else:
            role_val = getattr(current_user, "role", "") or ""
            role_str = str(role_val).strip().lower()
            if "admin" in role_str:
                is_admin = True
    except Exception:
        is_admin = False
    # -------------------------------------------------------------------

    print(f"DEBUG[salary_list]: current_user.id={user_id} is_admin={is_admin}")

    if is_admin:
        salaries = db.query(Salary).order_by(Salary.id.desc()).all()
        employees = db.query(User).order_by(User.id.desc()).all()
        template_name = "salary_admin.html"
    else:
        if not user_id:
            print("DEBUG[salary_list]: missing user id for non-admin -> redirect to login")
            return RedirectResponse("/login")
        # query only salaries for the logged-in employee
        salaries = db.query(Salary).filter(Salary.employee_id == user_id).order_by(Salary.id.desc()).all()
        # defensive filter in case something odd happens upstream
        salaries = [s for s in salaries if int(getattr(s, "employee_id", -1)) == user_id]
        employees = []
        template_name = "salary_employee.html"

    rows, total_attendance, total_absent = build_rows(db, salaries)

    try:
        total_employees = db.query(User).count()
    except Exception as e:
        print("DEBUG: error counting employees:", e)
        total_employees = len(employees) if employees else 0

    # ----------------- CHANGED: pass current_user (avoid collision with other 'user' vars) -----------------
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "current_user": current_user,
            "salaries": salaries,
            "employees": employees,
             "user": current_user,
            "rows": rows,
            "total_attendance": total_attendance,
            "total_absent": total_absent,
            "total_employees": total_employees
        }
    )
    # -------------------------------------------------------------------------------------------------------


# Optional alias for /salary/admin
@router.get("/salary/admin")
def salary_admin_alias(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return salary_list(request=request, db=db, current_user=current_user)


# ------------------------- UPLOAD SALARY (ADMIN) -------------------------
@router.post("/salary/admin/upload/{salary_id}")
@show_exceptions_for_dev
def upload_salary(
    salary_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Admin only
    role = getattr(current_user, "role", None)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")
    if not role or str(role).lower() != "admin":
        return PlainTextResponse("Access denied", status_code=403)

    salary = db.query(Salary).filter(Salary.id == salary_id).first()
    if not salary:
        return PlainTextResponse("Salary record not found", status_code=404)

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        return PlainTextResponse("Only PDF files are allowed", status_code=400)

    SALARY_DIR.mkdir(parents=True, exist_ok=True)
    month_str = (getattr(salary, "month", "") or "").replace("-", "_") or "unknown"
    orig = Path(file.filename).name
    safe_name = f"salary_emp{salary.employee_id}_{month_str}_{orig}"
    dest = SALARY_DIR / safe_name

    try:
        with dest.open("wb") as out_f:
            shutil.copyfileobj(file.file, out_f)
    except Exception as e:
        print("Error saving uploaded file:", e)
        return PlainTextResponse("Failed to save file", status_code=500)
    finally:
        try:
            file.file.close()
        except:
            pass

    try:
        if hasattr(salary, "slip_file"):
            setattr(salary, "slip_file", safe_name)
        elif hasattr(salary, "slip_filename"):
            setattr(salary, "slip_filename", safe_name)
        elif hasattr(salary, "file_name"):
            setattr(salary, "file_name", safe_name)
        db.add(salary)
        db.commit()
    except Exception as e:
        print("Warning: could not persist slip filename to DB:", e)

    return RedirectResponse("/salary", status_code=303)


# ------------------------- GENERATE SALARY -------------------------
@router.post("/salary/generate")
@show_exceptions_for_dev
def generate_salary(
    employee_id: int = Form(...),
    month: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    role = getattr(current_user, "role", None)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")

    if not role or str(role).lower() != "admin":
        return RedirectResponse("/salary", status_code=303)

    try:
        pdf_path, was_created = get_or_create_salary_slip(db, employee_id, month)
        print("Salary slip generated:", pdf_path)
        return RedirectResponse("/salary", status_code=303)
    except ValueError as e:
        return PlainTextResponse(str(e), status_code=404)
    except Exception as e:
        print("Error generating salary:", e)
        return PlainTextResponse(str(e), status_code=500)


# ------------------------- DOWNLOAD SALARY -------------------------
@router.get("/salary/download/{salary_id}", name="download_salary")
@show_exceptions_for_dev
def download_salary(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    from pathlib import Path

    def _safe(name: str) -> str:
        # Keep letters, numbers, dot, underscore and dash. Replace other chars with underscore.
        return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name))

    # --- normalize role and id ---
    try:
        user_id = int(getattr(current_user, "id", None))
    except Exception:
        user_id = None
    role_val = getattr(current_user, "role", "")
    try:
        role_str = str(role_val).strip().lower()
    except Exception:
        role_str = ""
    is_admin = bool(role_str and "admin" in role_str)

    print(f"DEBUG[download_salary]: current_user.id={user_id} role={role_str} is_admin={is_admin}")

    # --- fetch salary record ---
    # ----------------- CHANGED: For non-admins, fetch by both id and ownership to avoid leaking records. -----------------
    if not is_admin and user_id:
        salary = db.query(Salary).filter(Salary.id == salary_id, Salary.employee_id == int(user_id)).first()
    else:
        salary = db.query(Salary).filter(Salary.id == salary_id).first()
    # ---------------------------------------------------------------------------------------------------------------------

    if not salary:
        print("DEBUG[download_salary]: salary record not found")
        return PlainTextResponse("Salary record not found", status_code=404)

    # --- permission check ---
    if not is_admin:
        if not user_id:
            print("DEBUG[download_salary]: access denied (no user id)")
            return PlainTextResponse("Access denied", status_code=403)
        try:
            if salary.employee_id != int(user_id):
                print(f"DEBUG[download_salary]: access denied (salary.employee_id={salary.employee_id} != user_id={user_id})")
                return PlainTextResponse("Access denied", status_code=403)
        except Exception:
            return PlainTextResponse("Access denied", status_code=403)

    # --- prefer uploaded slip if present (try several variants) ---
    uploaded_name = None
    for attr in ("slip_file", "slip_filename", "file_name", "uploaded_filename"):
        if hasattr(salary, attr):
            val = getattr(salary, attr)
            if val:
                uploaded_name = val
                break

    tried_paths = []

    if uploaded_name:
        print(f"DEBUG[download_salary]: uploaded_name raw={uploaded_name}")
        # candidate 1: as stored (may be basename or full path)
        cand = Path(str(uploaded_name))
        # if uploaded_name is relative or basename, join SALARY_DIR
        if not cand.is_absolute():
            p1 = SALARY_DIR / cand.name
            tried_paths.append(p1)
            if p1.exists():
                print("DEBUG[download_salary]: returning uploaded file:", p1)
                return FileResponse(path=str(p1), media_type="application/pdf", filename=p1.name)
        else:
            tried_paths.append(cand)
            if cand.exists():
                print("DEBUG[download_salary]: returning uploaded absolute file:", cand)
                return FileResponse(path=str(cand), media_type="application/pdf", filename=cand.name)

        # candidate 2: sanitized basename
        safe_name = _safe(Path(uploaded_name).name)
        p2 = SALARY_DIR / safe_name
        tried_paths.append(p2)
        if p2.exists():
            print("DEBUG[download_salary]: returning uploaded file (sanitized):", p2)
            return FileResponse(path=str(p2), media_type="application/pdf", filename=p2.name)

        # candidate 3: try stripping added prefixes/suffixes (common patterns)
        basename = Path(uploaded_name).name
        if basename != uploaded_name:
            p3 = SALARY_DIR / basename
            tried_paths.append(p3)
            if p3.exists():
                print("DEBUG[download_salary]: returning uploaded file (basename):", p3)
                return FileResponse(path=str(p3), media_type="application/pdf", filename=p3.name)

    # --- fallback: generated file patterns ---
    # Try both formats for month part: with '-' and '_', because files may be saved either way.
    month_raw = (getattr(salary, "month", "") or "")
    month_candidates = []
    if month_raw:
        month_candidates.append(month_raw)                       # as stored (e.g. "2025-12")
        month_candidates.append(month_raw.replace("-", "_"))    # underscore form
    else:
        month_candidates.append("")  # empty fallback

    gen_candidates = []
    for m in month_candidates:
        name = f"salary_emp{salary.employee_id}_{m}.pdf" if m else f"salary_emp{salary.employee_id}.pdf"
        gen_candidates.append(Path(SALARY_DIR) / name)

    # check generated candidates
    for p in gen_candidates:
        tried_paths.append(p)
        if p.exists():
            print("DEBUG[download_salary]: returning existing generated file:", p)
            return FileResponse(path=str(p), media_type="application/pdf", filename=p.name)

    # not found on disk: attempt to generate
    employee = db.query(User).filter(User.id == salary.employee_id).first()
    if not employee:
        print("DEBUG[download_salary]: employee not found for salary")
        return PlainTextResponse("Employee not found", status_code=404)

    try:
        print("DEBUG[download_salary]: attempting to generate PDF now...")
        generated_path = generate_and_save_pdf(employee, salary)
        print("DEBUG[download_salary]: generate_and_save_pdf returned:", generated_path)
    except Exception as e:
        print("ERROR[download_salary]: exception generating PDF:", e)
        traceback.print_exc()
        return PlainTextResponse("Error generating PDF", status_code=500)

    # normalize returned path
    if isinstance(generated_path, str):
        generated_path = Path(generated_path)
    if not isinstance(generated_path, Path):
        print("DEBUG[download_salary]: generate_and_save_pdf returned unexpected type")
        return PlainTextResponse("Invalid generated path", status_code=500)

    tried_paths.append(generated_path)
    if generated_path.exists():
        print("DEBUG[download_salary]: returning newly generated file:", generated_path)
        return FileResponse(path=str(generated_path), media_type="application/pdf", filename=generated_path.name)

    # nothing worked - show debug info
    print("DEBUG[download_salary]: Tried paths:")
    for t in tried_paths:
        print(" -", t, "(exists)" if Path(t).exists() else "(missing)")
    return PlainTextResponse("Salary file not found", status_code=404)


# ------------------------- DELETE SALARY -------------------------
@router.post("/salary/delete/{salary_id}")
@show_exceptions_for_dev
def delete_salary(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    role = getattr(current_user, "role", None)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")

    if not role or str(role).lower() != "admin":
        return RedirectResponse("/salary", status_code=303)

    salary = db.query(Salary).filter(Salary.id == salary_id).first()
    if not salary:
        return PlainTextResponse("Salary record not found", status_code=404)

    # delete uploaded slip if present
    uploaded_name = None
    for attr in ("slip_file", "slip_filename", "file_name"):
        if hasattr(salary, attr) and getattr(salary, attr):
            uploaded_name = getattr(salary, attr)
            break

    if uploaded_name:
        p = SALARY_DIR / uploaded_name
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            print("Warning: could not delete uploaded slip:", e)

    # delete generated slip if present
    month_str = (getattr(salary, "month", "") or "").replace("-", "_")
    gen_name = f"salary_emp{salary.employee_id}_{month_str}.pdf"
    gen_path = SALARY_DIR / gen_name
    try:
        if gen_path.exists():
            gen_path.unlink()
    except Exception as e:
        print("Warning: could not delete generated slip:", e)

    db.delete(salary)
    db.commit()

    return RedirectResponse("/salary", status_code=303)


# Alias so /salary/slips and /salary/slips/ work (calls existing salary_list)
@router.get("/salary/slips")
@router.get("/salary/slips/")
def salary_slips_alias(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return salary_list(request=request, db=db, current_user=current_user)
