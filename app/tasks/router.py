# app/tasks/rount.py

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from datetime import datetime
from functools import wraps
import traceback
from jinja2 import TemplateNotFound
from sqlalchemy.exc import SQLAlchemyError
import os

from app.database import get_db
from app.tasks.models import Task
from app.auth.dependencies import get_current_user 

# Try to import a sensible "employee" model. First try app.employees.models.Employee,
# then app.auth.models.User. If neither import exists, EmployeeModel will be None
# and queries for employees will be skipped safely.
try:
    from app.employees.models import Employee as EmployeeModel
except Exception:
    try:
        from app.auth.models import User as EmployeeModel
    except Exception:
        EmployeeModel = None


router = APIRouter()

# Use absolute path for templates to avoid cwd issues
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ----------------------------
# Debug wrapper (dev only)
# Remove or disable this in production
# ----------------------------
def show_exceptions_for_dev(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            tb = traceback.format_exc()
            print("=== ERROR IN ROUTE ===\n", tb)  # server console
            return PlainTextResponse(tb, status_code=500)  # visible in browser (dev only)
    return wrapper


# ---------------------------------------
# GET: List tasks (admin = all, employee = own)
# ---------------------------------------
@router.get("/tasks")
@show_exceptions_for_dev   # remove this decorator in production
def task_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # tolerate current_user being either an object or a dict
    role = getattr(current_user, "role", None)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")
    user_id = getattr(current_user, "id", None)
    if user_id is None and isinstance(current_user, dict):
        user_id = current_user.get("id")

    try:
        if role and str(role).lower() == "admin":
            tasks = db.query(Task).all()
        else:
            # ensure user_id is numeric, otherwise return empty list
            try:
                uid = int(user_id)
                tasks = db.query(Task).filter(Task.assigned_to == uid).all()
            except Exception:
                tasks = []
    except TemplateNotFound:
        return PlainTextResponse("Template not found: tasks.html (expected in templates/)", status_code=500)

    # --- NEW: load employees for dropdown in the template (if model available) ---
    try:
        if EmployeeModel is not None:
            employees = db.query(EmployeeModel).all()
        else:
            employees = []
    except Exception:
        employees = []

    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "user": current_user, "tasks": tasks, "employees": employees}
    )


# ---------------------------------------
# POST: Create task (admin only)
# ---------------------------------------
@router.post("/tasks/create")
def task_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(None),
    assigned_to_raw: str = Form(None),   # accept raw and coerce for safety
    deadline: str = Form(None),
    priority: str = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # role check tolerant for object/dict
    role = getattr(current_user, "role", None) or (current_user.get("role") if isinstance(current_user, dict) else None)
    if not role or str(role).lower() != "admin":
        return RedirectResponse("/tasks", status_code=303)

    # safe assigned_to conversion
    assigned_to = None
    if assigned_to_raw not in (None, "", "None"):
        try:
            assigned_to = int(assigned_to_raw)
        except Exception:
            assigned_to = None

    deadline_date = None
    if deadline:
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        except Exception:
            deadline_date = None

    new_task = Task(
        title=title,
        description=description,
        assigned_to=assigned_to,
        deadline=deadline_date,
        status="To-Do",
        priority=priority
    )

    try:
        db.add(new_task)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        tb = traceback.format_exc()
        print("DB error in create:", tb)
        return PlainTextResponse(f"Database error creating task:\n\n{tb}", status_code=500)

    return RedirectResponse("/tasks", status_code=303)


# ---------------------------------------
# GET: View detail page
# ---------------------------------------
@router.get("/tasks/{task_id}")
@show_exceptions_for_dev
def task_view(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        return RedirectResponse("/tasks", status_code=303)

    # employee can view only own tasks
    role = getattr(current_user, "role", None)
    user_id = getattr(current_user, "id", None)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")
    if user_id is None and isinstance(current_user, dict):
        user_id = current_user.get("id")

    # if user is not admin and not owner, redirect
    try:
        if not (role and str(role).lower() == "admin") and task.assigned_to != int(user_id):
            return RedirectResponse("/tasks", status_code=303)
    except Exception:
        # in case user_id is not numeric
        return RedirectResponse("/tasks", status_code=303)

    # Provide employees to task_detail template as well (so edit form can use dropdown)
    try:
        if EmployeeModel is not None:
            employees = db.query(EmployeeModel).all()
        else:
            employees = []
    except Exception:
        employees = []

    return templates.TemplateResponse(
        "task_detail.html",
        {"request": request, "user": current_user, "task": task, "employees": employees}
    )


# ---------------------------------------
# POST: Handle accept, complete, delete, update
# ---------------------------------------
@router.post("/tasks/{task_id}/action")
def task_action(
    task_id: int,
    action: str = Form(...),
    title: str = Form(None),
    description: str = Form(None),
    assigned_to_raw: str = Form(None),   # accept raw and coerce
    deadline: str = Form(None),
    priority: str = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        task = db.query(Task).filter(Task.id == task_id).first()

        if not task:
            return RedirectResponse("/tasks", status_code=303)

        # safe convert assigned_to
        assigned_to = None
        if assigned_to_raw not in (None, "", "None"):
            try:
                assigned_to = int(assigned_to_raw)
            except Exception:
                assigned_to = None

        # determine role safely
        role = getattr(current_user, "role", None)
        user_id = getattr(current_user, "id", None)
        if role is None and isinstance(current_user, dict):
            role = current_user.get("role")
        if user_id is None and isinstance(current_user, dict):
            user_id = current_user.get("id")

        # employee actions
        if role and str(role).lower() == "employee":
            try:
                int_user_id = int(user_id)
            except Exception:
                int_user_id = None

            if action == "accept":
                # assign to himself if unassigned
                if task.assigned_to is None and int_user_id is not None:
                    task.assigned_to = int_user_id
                task.status = "In Progress"

            elif action == "complete":
                if int_user_id is not None and task.assigned_to == int_user_id:
                    task.status = "Completed"

            elif action == "reopen":
                if int_user_id is not None and task.assigned_to == int_user_id:
                    task.status = "In Progress"

            db.add(task)
            db.commit()
            return RedirectResponse("/tasks", status_code=303)

        # admin actions
        if role and str(role).lower() == "admin":
            if action == "delete":
                db.delete(task)
                db.commit()
                return RedirectResponse("/tasks", status_code=303)

            if action == "update":
                if title is not None and title != "":
                    task.title = title

                # allow description empty string
                if description is not None:
                    task.description = description

                # update assigned_to only if valid int
                if assigned_to is not None:
                    task.assigned_to = assigned_to
                else:
                    # if form cleared assignment (empty), set None
                    if assigned_to_raw in ("", "None"):
                        task.assigned_to = None

                # parse deadline safely
                if deadline:
                    try:
                        task.deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
                    except Exception:
                        pass

                if priority is not None:
                    task.priority = priority

                db.add(task)
                db.commit()
                return RedirectResponse(f"/tasks/{task_id}", status_code=303)

        return RedirectResponse("/tasks", status_code=303)

    except SQLAlchemyError as db_exc:
        db.rollback()
        tb = traceback.format_exc()
        print("SQLAlchemy error in task_action:", tb)
        return PlainTextResponse(f"Database error:\n\n{tb}", status_code=500)
    except Exception as exc:
        tb = traceback.format_exc()
        print("Unexpected error in task_action:", tb)
        return PlainTextResponse(f"Unexpected error:\n\n{tb}", status_code=500)


@router.get("/admin/summary")
def tasks_summary(db: Session = Depends(get_db)):
    try:
        total = db.execute("SELECT COUNT(*) FROM tasks").scalar() or 0
    except:
        total = 0
    return {"total": total}
