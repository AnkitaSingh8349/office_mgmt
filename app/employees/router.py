from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.employees.models import Employee
from app.auth.dependencies import get_current_user, require_role

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
