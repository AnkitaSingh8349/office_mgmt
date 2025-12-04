# app/utils/config.py
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALARY_SLIP_DIR = os.path.join(BASE_DIR, "static", "uploads", "salary_slips")

os.makedirs(SALARY_SLIP_DIR, exist_ok=True)
