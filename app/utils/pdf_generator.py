# app/utils/pdf_generator.py
import io
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Union, Any, Optional
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import sys
import traceback

BASE_DIR = Path(__file__).resolve().parent.parent
SALARY_DIR = BASE_DIR / "static" / "uploads" / "salary_slips"

def _ensure_salary_dir():
    try:
        SALARY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Could not create salary directory {SALARY_DIR!s}: {e}")

def _sanitize_filename_part(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))

def _truncate(s: str, max_len: int = 40) -> str:
    s = str(s or "")
    return s if len(s) <= max_len else s[:max_len]

def _email_token(email: str, hide_email: bool = True, keep_chars: int = 8) -> str:
    if not email:
        return "noemail"
    email = str(email)
    if not hide_email:
        return _sanitize_filename_part(email)
    h = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return h[:keep_chars]

def _extract_present_days(candidate: Any) -> Optional[int]:
    """
    Try common attribute names to find attendance/present count on a salary object
    (e.g. attendance_count, attend_count, present_days, present).
    Returns int or None.
    """
    if candidate is None:
        return None
    for attr in ("attendance_count", "attend_count", "present_days", "present", "present_count", "present_cnt"):
        try:
            if hasattr(candidate, attr):
                val = getattr(candidate, attr)
                if val is None:
                    continue
                return int(val)
            if isinstance(candidate, dict) and attr in candidate:
                v = candidate.get(attr)
                if v is None:
                    continue
                return int(v)
        except Exception:
            continue
    return None

def generate_and_save_pdf(
    employee_or_id: Union[Any, int],
    salary_or_month: Union[Any, str],
    present_days: Optional[int] = None,
    hide_email_in_filename: bool = True
) -> Path:
    """
    Generate a salary slip PDF and save it into SALARY_DIR.

    - employee_or_id may be an object with .id, .name, .email or just an int.
    - salary_or_month may be an object with .month or a month string.
    - present_days: optional int specifying days present (if available).
    - hide_email_in_filename: if True the email is replaced by a short hash to avoid leaking PII.

    Returns Path to the saved file.
    """
    try:
        print(f"[pdf_generator] generate_and_save_pdf called: emp={employee_or_id!r}, month={salary_or_month!r}, present_days={present_days}", file=sys.stderr)
    except Exception:
        pass

    # Resolve employee id
    try:
        if hasattr(employee_or_id, "id"):
            emp_id = int(getattr(employee_or_id, "id"))
        else:
            emp_id = int(employee_or_id)
    except Exception:
        raise ValueError("Invalid employee / employee id passed to generate_and_save_pdf")

    # Resolve month string
    month_raw = ""
    try:
        if hasattr(salary_or_month, "month"):
            month_raw = getattr(salary_or_month, "month") or ""
        else:
            month_raw = str(salary_or_month or "")
    except Exception:
        month_raw = str(salary_or_month or "")

    # Try to extract present_days from salary_or_month if present_days arg not provided
    if present_days is None:
        present_days = _extract_present_days(salary_or_month)

    # Extract employee name & email if available
    emp_name_raw = ""
    emp_email_raw = ""
    try:
        if hasattr(employee_or_id, "name"):
            emp_name_raw = getattr(employee_or_id, "name") or ""
        elif isinstance(employee_or_id, dict):
            emp_name_raw = employee_or_id.get("name", "") or ""
    except Exception:
        emp_name_raw = ""

    try:
        if hasattr(employee_or_id, "email"):
            emp_email_raw = getattr(employee_or_id, "email") or ""
        elif isinstance(employee_or_id, dict):
            emp_email_raw = employee_or_id.get("email", "") or ""
    except Exception:
        emp_email_raw = ""

    # sanitize & build filename parts
    name_part = _truncate(_sanitize_filename_part(emp_name_raw).replace(" ", "_"), 40) or f"emp{emp_id}"
    email_part = _email_token(emp_email_raw, hide_email=hide_email_in_filename, keep_chars=8)
    live_part = "live"
    present_part = f"present{int(present_days)}" if present_days is not None else "present?"

    month_safe = _sanitize_filename_part(month_raw) if month_raw else ""
    if month_safe:
        filename = f"salary_emp{emp_id}_{month_safe}_{name_part}_{email_part}_{live_part}_{present_part}.pdf"
    else:
        filename = f"salary_emp{emp_id}_{name_part}_{email_part}_{live_part}_{present_part}.pdf"

    filename = _sanitize_filename_part(filename)[:180]  # cap length
    out_path = SALARY_DIR / filename

    # ensure dir exists before writing
    _ensure_salary_dir()

    # Build PDF in memory
    buffer = io.BytesIO()
    try:
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, height - 50, "AJXtechnologies private limited")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, "Skye Privilon, 117, Tulsi Nagar, Nipania, Indore, Madhya Pradesh 452010")

        # show email if available (you can hide in PDF if privacy required)
        if emp_email_raw:
            email_display = emp_email_raw
        else:
            email_display = ""

        c.drawString(50, height - 85, f"Phone: +1 123 456 7890 | Email: {email_display}")

        c.setStrokeColor(colors.black)
        c.line(40, height - 95, width - 40, height - 95)

        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(200, height - 130, "SALARY SLIP")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 160, f"Employee ID: {emp_id}")
        if emp_name_raw:
            c.drawString(50, height - 175, f"Name: {emp_name_raw}")
        c.drawString(50, height - 190, f"Month: {month_raw}")
        c.drawString(50, height - 205, f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d')}")
        if present_days is not None:
            c.drawString(50, height - 220, f"Days Present: {int(present_days)}")

        # Earnings & deductions (static example values — replace with real data if desired)
        table_top = height - 260
        left_x = 50
        right_x = 300

        c.setFont("Helvetica-Bold", 14)
        c.drawString(left_x, table_top, "EARNINGS")
        c.setFont("Helvetica", 12)
        c.drawString(left_x, table_top - 20, "Basic Salary: 25000")
        c.drawString(left_x, table_top - 40, "HRA: 5000")
        c.drawString(left_x, table_top - 60, "Allowances: 3000")
        total_earnings = 25000 + 5000 + 3000

        c.setFont("Helvetica-Bold", 14)
        c.drawString(right_x, table_top, "DEDUCTIONS")
        c.setFont("Helvetica", 12)
        c.drawString(right_x, table_top - 20, "PF: 2000")
        c.drawString(right_x, table_top - 40, "Tax: 1500")
        total_deductions = 2000 + 1500

        net_salary = total_earnings - total_deductions

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, table_top - 110, f"NET SALARY: {net_salary} INR")

        # Footer
        c.setStrokeColor(colors.black)
        c.line(40, 120, width - 40, 120)

        c.setFont("Helvetica", 12)
        c.drawString(50, 100, "This is a system generated payslip and does not require a signature.")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(400, 80, "HR Department")

        c.showPage()
        c.save()
    except Exception as e:
        tb = traceback.format_exc()
        print("[pdf_generator] Error while building PDF:", tb, file=sys.stderr)
        raise RuntimeError(f"ReportLab error while generating PDF: {e}")

    # write bytes to disk
    buffer.seek(0)
    try:
        with open(out_path, "wb") as f:
            f.write(buffer.read())
    except Exception as e:
        tb = traceback.format_exc()
        print("[pdf_generator] Error writing PDF to disk:", tb, file=sys.stderr)
        raise RuntimeError(f"Failed to write PDF to disk ({out_path}): {e}")

    try:
        print(f"[pdf_generator] Saved PDF -> {out_path}", file=sys.stderr)
    except Exception:
        pass

    return out_path
