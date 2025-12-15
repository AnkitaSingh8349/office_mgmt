# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------------------------
# Database Configuration
# ---------------------------
# Use env var for Render/Production, fallback to local hardcoded for Dev
# NOTE: For Render, you must set DATABASE_URL env var or use their internal DB URL
DEFAULT_LOCAL_DB = "mysql+mysqlconnector://root:root@localhost/office_mgmt"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_LOCAL_DB)

# Handle SQLite fallback if configured (optional)
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(
    DATABASE_URL,
    echo=True,  # optional: shows SQL in console
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

