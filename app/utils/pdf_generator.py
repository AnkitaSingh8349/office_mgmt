# app/utils/pdf_generator.py
import io
import re
from pathlib import Path
from datetime import datetime
from typing import Union, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# PDF directory (project-relative)
BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"
SALARY_DIR = MEDIA_DIR / "salary_slips"
SALARY_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename_part(s: str) -> str:
    """
    Allow letters, numbers, dot, underscore and dash.
    Replace anything else with underscore.
    """
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))


def generate_and_save_pdf(employee_or_id: Union[Any, int], salary_or_month: Union[Any, str]) -> Path:
    """
    Generate a simple salary slip PDF and save it in SALARY_DIR.
    This function is flexible:
      - If called as generate_and_save_pdf(employee, salary) it will try to read
        employee.id and salary.month from the objects.
      - If called as generate_and_save_pdf(employee_id, month_str) it will work too.

    Returns Path to the saved PDF (or raises on error).
    """
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

    # sanitize month and build filename
    month_safe = _sanitize_filename_part(month_raw) if month_raw else ""
    if month_safe:
        filename = f"salary_emp{emp_id}_{month_safe}.pdf"
    else:
        filename = f"salary_emp{emp_id}.pdf"

    filename = _sanitize_filename_part(filename)  # final safety
    out_path = SALARY_DIR / filename

    # Build PDF in memory (avoid ReportLab writing directly to disk with potentially bad path)
    buffer = io.BytesIO()
    try:
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, height - 50, "COMPANY NAME")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, "Address Line 1, City, Country")
        c.drawString(50, height - 85, "Phone: +1 123 456 7890 | Email: hr@company.com")

        c.setStrokeColor(colors.black)
        c.line(40, height - 95, width - 40, height - 95)

        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(200, height - 130, "SALARY SLIP")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 160, f"Employee ID: {emp_id}")
        c.drawString(50, height - 175, f"Month: {month_raw}")
        c.drawString(50, height - 190, f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d')}")

        # Earnings & deductions (static example values — replace with real data if desired)
        table_top = height - 230
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
        # raise with context so caller (router) can show debug info
        raise RuntimeError(f"ReportLab error while generating PDF: {e}")

    # write bytes to disk
    buffer.seek(0)
    try:
        with open(out_path, "wb") as f:
            f.write(buffer.read())
    except Exception as e:
        raise RuntimeError(f"Failed to write PDF to disk ({out_path}): {e}")

    return out_path
