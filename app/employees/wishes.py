# app/employees/wishes.py
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class BirthdayWish(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: Optional[int] = None
    recipient_id: Optional[int] = None
    message: Optional[str] = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
