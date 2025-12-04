# app/salary/models.py

from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey
from app.database import Base

class Salary(Base):
    __tablename__ = "salary"   # match your MySQL table name

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employee1.id"), nullable=False)
    month = Column(String(20), nullable=True)
    base_salary = Column(DECIMAL(10, 2), nullable=True)
    deductions = Column(DECIMAL(10, 2), nullable=True)
    net_salary = Column(DECIMAL(10, 2), nullable=True)
    slip_file = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<Salary id={self.id} employee_id={self.employee_id} month={self.month}>"
