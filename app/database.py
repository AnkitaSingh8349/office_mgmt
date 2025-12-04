# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------------------------
# Use MySQL Connector (no PyMySQL)
# ---------------------------
DATABASE_URL = "mysql+mysqlconnector://root:root@localhost/office_mgmt"

engine = create_engine(
    DATABASE_URL,
    echo=True,  # optional: shows SQL in console
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
