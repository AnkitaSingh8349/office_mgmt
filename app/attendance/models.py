# app/attendance/models.py

from sqlalchemy import Column, Integer, Date, Time, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Attendance(Base):
    __tablename__ = "attendance1"   # EXACT table name in MySQL

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employee1.id"), nullable=False)
    date = Column(Date, nullable=True)
    check_in = Column(Time, nullable=True)
    check_out = Column(Time, nullable=True)
    status = Column(String(20), nullable=True)   # values: 'PRESENT', 'ABSENT', 'WFH'

    # Optional relationship to Employee (safe; only if Employee model exists)
    # from app.employees.models import Employee
    # employee = relationship("Employee", backref="attendances")

    def __repr__(self):
        return f"<Attendance id={self.id} employee_id={self.employee_id} date={self.date}>"
