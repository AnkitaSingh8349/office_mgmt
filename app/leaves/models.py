# app/leaves/models.py

from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey
from app.database import Base

class Leave(Base):
    __tablename__ = "leaves"   # EXACT MySQL table name

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employee1.id"), nullable=False)
    leave_type = Column(String(20), nullable=False)   # Casual / Sick / Earned
    from_date = Column(Date, nullable=True)
    to_date = Column(Date, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="Pending")  
    # Pending / Approved / Rejected

    def __repr__(self):
        return f"<Leave id={self.id} employee_id={self.employee_id}>"
