from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.employees.models import Employee
from app.auth.dependencies import get_current_user, require_role

# app/employees/router.py (top portion)
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from sqlmodel import Session, select
from sqlalchemy import func        # <- for debug count
from datetime import date, datetime
import traceback

from app.database import engine
from app.employees.models import Employee

# remove internal prefix here
router = APIRouter(tags=["employees_api"])



# Ensure get_session is defined BEFORE routes that depend on it
def get_session():
    with Session(engine) as s:
        yield s

# ... existing helpers (_iso_safe, _serialize_short, etc.) ...

# Now safe to add debug endpoint that uses get_session
@router.get("/_debug_count", name="employees_debug_count")
def debug_count(session: Session = Depends(get_session)):
    try:
        cnt = session.exec(select(func.count()).select_from(Employee)).one()
        return {"count": cnt}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# your all_employees and other routes follow...


router = APIRouter(prefix="/employees", tags=["employees"])
templates = Jinja2Templates(directory="app/templates")


# --- admin_required helper using get_current_user ---
def admin_required(current_user = Depends(get_current_user)):
    if not current_user or getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ----------------- Employee pages / CRUD -----------------

# List employees (HTML)
@router.get("/", response_class=HTMLResponse)
def list_employees(request: Request, db: Session = Depends(get_db), user = Depends(admin_required)):
    employees = db.query(Employee).order_by(Employee.id).all()
    return templates.TemplateResponse("employees_list.html", {"request": request, "employees": employees, "user": user})


# Create form view (GET)
@router.get("/create-form", response_class=HTMLResponse)
def create_form(request: Request, user = Depends(admin_required)):
    return templates.TemplateResponse("employee_create.html", {"request": request, "user": user})


# Create employee (POST)
@router.post("/create")
def create_employee(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    role: str = Form(...),
    department_id: int = Form(None),
    salary: str = Form(None),
    joining_date: str = Form(None),
    status: str = Form(None),
    db: Session = Depends(get_db),
    user = Depends(admin_required),
):
    salary_val = Decimal(salary) if salary not in (None, "", "None") else None

    new_emp = Employee(
        name=name,
        email=email,
        phone=phone,
        role=role,
        department_id=department_id,
        salary=salary_val,
        joining_date=joining_date or None,
        status=status,
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return RedirectResponse(url="/employees", status_code=303)


# Edit form view (GET)
@router.get("/edit/{emp_id}", response_class=HTMLResponse)
def edit_employee_view(emp_id: int, request: Request, db: Session = Depends(get_db), user = Depends(admin_required)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return templates.TemplateResponse("employee_edit.html", {"request": request, "employee": emp, "user": user})


# Update employee (POST)
@router.post("/update/{emp_id}")
def update_employee(
    emp_id: int,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    role: str = Form(...),
    department_id: int = Form(None),
    salary: str = Form(None),
    joining_date: str = Form(None),   # <-- FIXED: removed broken comment
    status: str = Form(None),
    db: Session = Depends(get_db),
    user = Depends(admin_required),
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp.name = name
    emp.email = email
    emp.phone = phone
    emp.role = role
    emp.department_id = department_id
    emp.salary = Decimal(salary) if salary not in (None, "", "None") else None
    emp.joining_date = joining_date or None
    emp.status = status

    db.commit()
    return RedirectResponse(url="/employees", status_code=303)


# Delete (GET)
@router.get("/delete/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db), user = Depends(admin_required)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()
    return RedirectResponse(url="/employees", status_code=303)


# Admin summary API
@router.get("/admin/summary")
def employee_admin_summary(db: Session = Depends(get_db), _ = Depends(require_role(["admin"]))):
    try:
        total = db.query(Employee).count()
    except Exception:
        total = 0
    return {"total": total}


    
