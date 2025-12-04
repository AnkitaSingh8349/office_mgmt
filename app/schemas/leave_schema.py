# app/schemas/leave_schema.py
from pydantic import BaseModel
from datetime import date
from typing import Optional

class LeaveCreateSchema(BaseModel):
    leave_type: str
    from_date: date
    to_date: date
    reason: str

class LeaveApproveSchema(BaseModel):
    status: str
    decision_note: Optional[str] = None

class LeaveOut(BaseModel):
    id: int
    employee_id: int
    leave_type: str
    from_date: date
    to_date: date
    reason: Optional[str]
    status: str
    applied_on: Optional[date]
    approver_id: Optional[int]

    model_config = {"from_attributes": True}
