from pydantic import BaseModel
from datetime import date, time
from typing import Optional

class AttendanceOut(BaseModel):
    id: int
    employee_id: int
    date: date
    check_in: Optional[time]
    check_out: Optional[time]
    status: Optional[str]

    class Config:
        orm_mode = True
