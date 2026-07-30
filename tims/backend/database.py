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
from sqlalchemy.orm import sessionmaker, declarative_base, Session

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


def seed_demo_accounts() -> None:
    """Automatically seeds the 5 default demo accounts into a fresh production database."""
    # Delayed internal structural imports to protect against application circular dependency locks
    try:
        from backend.models import User
        from backend.routers.auth_router import get_password_hash
    except ImportError:
        # Fallback to absolute paths if running directly inside the nested tims/ directory sub-context
        from tims.backend.models import User
        from tims.backend.routers.auth_router import get_password_hash

    db: Session = SessionLocal()
    try:
        # Check if the users data table exists and is currently completely empty
        inspector = inspect(engine)
        if "users" in inspector.get_table_names() and db.query(User).count() == 0:
            print("--- Seeding Demo Accounts for Golden Smiles Freight ---")
            demo_users = ["director", "erick", "lyn", "precious", "connie"]
            
            # Encrypts a standardized password your auth_router middleware engine can safely decode
            hashed_fallback_password = get_password_hash("password123")
            
            for username in demo_users:
                new_profile = User(
                    username=username,
                    email=f"{username}@goldensmiles.com",
                    hashed_password=hashed_fallback_password,
                    is_active=True
                )
                db.add(new_profile)
            
            db.commit()
            print("--- System Seeding Event Concluded Successfully! ---")
    except Exception as error:
        db.rollback()
        print(f"[Warning] Initialization seeding routine skipped or halted: {error}")
    finally:
        db.close()
