from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.employees.models import Employee

router = APIRouter(
    prefix="/admin/employees",
    tags=["Admin Employees"]
)

templates = Jinja2Templates(directory="app/templates")


# ---------------- PAGE ROUTE ----------------
@router.get("/profile")
def admin_employee_profile_page(request: Request):
    return templates.TemplateResponse(
        "admin_employee_profile.html",
        {"request": request}
    )

# ---------------- ADMIN DEPENDENCY ----------------
def admin_required():
    # replace later with real admin auth
    return True

# ---------------- API: LIST EMPLOYEES ----------------
@router.get("/all")
def get_all_employees(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    employees = db.query(Employee).order_by(Employee.name).all()

    return [
        {
            "id": e.id,
            "name": e.name,
            "email": e.email
        }
        for e in employees
    ]

# ---------------- API: EMPLOYEE DETAIL ----------------
@router.get("/{employee_id}")
def get_employee_detail(
    employee_id: int,
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    return {
        "id": emp.id,
        "name": emp.name,
        "email": emp.email,
        "phone": emp.phone,
        "role": emp.role,
        "department_id": emp.department_id,
        "salary": emp.salary,
        "joining_date": emp.joining_date,
        "status": emp.status,

        "birthday": emp.birthday,
        "gender": emp.gender,
        "marital_status": emp.marital_status,
        "father_name": emp.father_name,
        "linkedin_url": emp.linkedin_url,
        "uan": emp.uan,
        "pan": emp.pan,
        "aadhar": emp.aadhar,
        "personal_email": emp.personal_email,
        "personal_mobile": emp.personal_mobile,
        "seating_location": emp.seating_location,
        "bank_account_no": emp.bank_account_no,
        "bank_name": emp.bank_name,
        "ifsc_code": emp.ifsc_code,
        "account_type": emp.account_type,
        "payment_mode": emp.payment_mode,
    }
