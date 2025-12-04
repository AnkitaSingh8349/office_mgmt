# app/salary/engine.py
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple
from sqlalchemy.orm import Session
import os, time

from app.attendance.models import Attendance
from app.leaves.models import Leave
from app.employees.models import Employee
from app.salary.models import Salary

def _decimal(v):
    try:
        return Decimal(v)
    except Exception:
        return Decimal("0.00")

def first_last_day(year: int, month: int) -> Tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last

def count_working_days(start: date, end: date) -> int:
    days = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days

def calculate_for_employee(db: Session, employee: Employee, year: int, month: int):
    first, last = first_last_day(year, month)
    total_working_days = count_working_days(first, last)

    # Attendance present count (status == 'PRESENT')
    att_count = db.query(Attendance).filter(
        Attendance.employee_id == employee.id,
        Attendance.date >= first,
        Attendance.date <= last,
        Attendance.status == "PRESENT"
    ).count()

    # Approved leave days overlapping month
    leaves = db.query(Leave).filter(
        Leave.employee_id == employee.id,
        Leave.status == "Approved",
        Leave.from_date <= last,
        Leave.to_date >= first
    ).all()

    leave_days = 0
    unpaid_leave_days = 0
    for lv in leaves:
        s = lv.from_date
        e = lv.to_date or s
        cur = s
        while cur <= e:
            if first <= cur <= last and cur.weekday() < 5:
                leave_days += 1
                if (lv.leave_type or "").lower() in ("unpaid", "lop", "without pay"):
                    unpaid_leave_days += 1
            cur += timedelta(days=1)

    paid_days = att_count + max(0, leave_days - unpaid_leave_days)
    paid_days = min(paid_days, total_working_days)

    base_salary = _decimal(getattr(employee, "salary", 0) or 0)

    if total_working_days > 0:
        deduction = (base_salary * _decimal(unpaid_leave_days) / _decimal(total_working_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        earned = (base_salary * _decimal(paid_days) / _decimal(total_working_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        deduction = Decimal("0.00")
        earned = base_salary

    net_salary = (earned - deduction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if net_salary < 0:
        net_salary = Decimal("0.00")

    month_str = f"{year}-{str(month).zfill(2)}"
    existing = db.query(Salary).filter_by(employee_id=employee.id, month=month_str).first()

    if existing:
        existing.base_salary = float(base_salary)
        existing.deductions = float(deduction)
        existing.net_salary = float(net_salary)
        row = existing
    else:
        row = Salary(employee_id=employee.id, month=month_str,
                     base_salary=float(base_salary),
                     deductions=float(deduction),
                     net_salary=float(net_salary),
                     slip_file=None)
        db.add(row)

    db.commit()
    db.refresh(row)
    return row

def run_engine_for_month(db: Session, year: int, month: int, generate_pdf: bool = False, pdf_generator=None, email_sender=None):
    """
    generate_pdf: bool -> if True and pdf_generator provided, will generate PDF file and save to salary.slip_file
    pdf_generator: callable(salary_row, employee) -> (filename, path) OR bytes
    email_sender: callable(to_email, subject, body, attachment_path) -> send email (optional)
    """
    employees = db.query(Employee).all()
    results = []
    for emp in employees:
        s = calculate_for_employee(db, emp, year, month)
        # optionally generate pdf
        if generate_pdf and callable(pdf_generator):
            try:
                # pdf_generator may return bytes or a (filename, path) tuple
                res = pdf_generator(s, emp)
                if isinstance(res, tuple) and len(res) == 2:
                    fname, path = res
                elif isinstance(res, bytes):
                    # save bytes to file
                    fname = f"salary_{s.id}_{int(time.time())}.pdf"
                    path = os.path.join(os.path.dirname(__file__), "..", "static", "uploads", "salary_slips", fname)
                    with open(path, "wb") as fh:
                        fh.write(res)
                else:
                    # If generator returned filename string
                    fname = str(res)
                    path = os.path.join(os.path.dirname(__file__), "..", "static", "uploads", "salary_slips", fname)
                s.slip_file = fname
                db.add(s)
                db.commit()
                db.refresh(s)
                # optionally email
                if callable(email_sender) and getattr(emp, "email", None):
                    try:
                        email_sender(emp.email, f"Salary Slip for {s.month}", "Please find your salary slip attached.", path)
                    except Exception:
                        pass
            except Exception:
                pass
        results.append(s)
    return results
