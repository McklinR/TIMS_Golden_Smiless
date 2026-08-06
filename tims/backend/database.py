"""
Database configuration for TIMS (Transport Management System).
Golden Smiles Freight and Distribution.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool


def _get_database_url() -> str:
    db_url = os.getenv("TIMS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        return "sqlite:///./tims.db"

    db_url = db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("sqlite://"):
        return db_url

    return db_url


SQLALCHEMY_DATABASE_URL = _get_database_url()
engine_kwargs = {"pool_pre_ping": True}
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite:///:memory:"):
        engine_kwargs["poolclass"] = StaticPool
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["connect_args"] = connect_args
else:
    engine_kwargs["connect_args"] = connect_args

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite:///:memory:"):
        sqlite_path = None
    else:
        sqlite_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///./", "")
        sqlite_path = sqlite_path.replace("sqlite:///", "")
        if sqlite_path.startswith("/"):
            sqlite_path = sqlite_path[1:]
        if sqlite_path:
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
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
    """Ensure the baseline demo accounts exist without wiping user records added later."""
    db: Session = SessionLocal()
    try:
        inspector = inspect(engine)
        if "users" not in inspector.get_table_names():
            Base.metadata.create_all(bind=engine)
            inspector = inspect(engine)
            if "users" not in inspector.get_table_names():
                return

        print("--- Seeding baseline demo accounts ---")

        from backend.auth import get_password_hash
        from backend.models import User, UserRole

        account_credentials = {
            "director": ("director123", "Company Director", "ADMIN"),
            "erick": ("erick123", "Erick Logistics", "ADMIN"),
            "lyn": ("lyn123", "Lyn Operations", "TRACKING"),
            "precious": ("password123", "Precious Smiles", "BOOKING"),
            "edina": ("edina123", "Edina Finance", "ACCOUNTS"),
        }

        for username, data in account_credentials.items():
            password, full_name, role_string = data
            user = db.query(User).filter(User.username == username).first()
            if user is None:
                user = User(username=username)
                db.add(user)
            user.full_name = full_name
            user.hashed_password = get_password_hash(password)
            user.role = UserRole(role_string)
            user.is_active = True

        db.commit()
        print("--- Baseline demo accounts seeded successfully ---")
    except Exception as error:
        db.rollback()
        print(f"[Warning] Demo account seeding skipped: {error}")
    finally:
        db.close()
