# app/tasks/models.py

from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

# IMPORTANT: Must import Employee so SQLAlchemy knows the table
from app.employees.models import Employee


class Task(Base):
    __tablename__ = "tasks"   # MySQL table name

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey("employee1.id"), nullable=True)
    deadline = Column(Date, nullable=True)
    status = Column(String(20), nullable=True)     # To-Do / In Progress / Completed
    priority = Column(String(20), nullable=True)   # Low / Medium / High

    # 🔥 This line was missing — REQUIRED for admin to see employee info
    employee = relationship("Employee", backref="tasks")

    def __repr__(self):
        return f"<Task id={self.id} title={self.title}>"
