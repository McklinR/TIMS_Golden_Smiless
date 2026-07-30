"""
Database configuration for TIMS (Transport Management System).
Golden Smiles Freight and Distribution.

Uses SQLite by default for zero-config local development. Swap the
SQLALCHEMY_DATABASE_URL for a Postgres/MySQL DSN in production by setting
the TIMS_DATABASE_URL environment variable.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.getenv("TIMS_DATABASE_URL", "sqlite:///./tims.db")

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_booking_tracking_columns() -> None:
    """Add tracking columns to bookings when upgrading an existing SQLite DB."""
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "bookings" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("bookings")}
    alters = []
    if "location_status" not in existing:
        alters.append("ALTER TABLE bookings ADD COLUMN location_status VARCHAR(128)")
    if "tracking_status" not in existing:
        alters.append("ALTER TABLE bookings ADD COLUMN tracking_status VARCHAR(32)")
    if "tracking_timestamp" not in existing:
        alters.append("ALTER TABLE bookings ADD COLUMN tracking_timestamp DATETIME")

    if not alters:
        return

    with engine.begin() as connection:
        for statement in alters:
            connection.execute(text(statement))
