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
    password_hash = Column(String(255), nullable=True)

    # --- These fields EXIST in DB ---
    birthday = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    marital_status = Column(String(20), nullable=True)
    father_name = Column(String(100), nullable=True)
    linkedin_url = Column(String(255), nullable=True)
    uan = Column(String(50), nullable=True)
    pan = Column(String(50), nullable=True)
    aadhar = Column(String(50), nullable=True)
    personal_email = Column(String(150), nullable=True)
    personal_mobile = Column(String(20), nullable=True)
    seating_location = Column(String(100), nullable=True)
    bank_account_no = Column(String(64), nullable=True)
    bank_name = Column(String(100), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    account_type = Column(String(20), nullable=True)
    payment_mode = Column(String(20), nullable=True)

    def __repr__(self):
        return f"<Employee id={self.id} name={self.name} email={self.email}>"
