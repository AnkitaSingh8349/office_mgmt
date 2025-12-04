from sqlalchemy import Column, Integer, String, Date, DECIMAL
from app.database import Base

class Employee(Base):
    __tablename__ = "employee1"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), nullable=False)
    department_id = Column(Integer, nullable=True)
    salary = Column(DECIMAL(10, 2), nullable=True)
    joining_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=True)

    # 🔥 Missing column — add this
    password_hash = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<Employee id={self.id} name={self.name} email={self.email}>"
