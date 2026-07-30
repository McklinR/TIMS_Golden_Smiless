"""
Database configuration for TIMS (Transport Management System).
Golden Smiles Freight and Distribution.
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
    """Automatically seeds default accounts using the exact valid uppercase Enum values."""
    db: Session = SessionLocal()
    try:
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            user_count = db.execute(text("SELECT count(*) FROM users")).scalar()
            
            if user_count == 0:
                print("--- Seeding Custom Demo Accounts for Golden Smiles Freight ---")
                
                from backend.models import User
                from backend.auth import get_password_hash
                
                # Roles updated to match your exact enum constraint properties
                account_credentials = {
                    "director": ("director123", "Company Director", "ADMIN"),
                    "erick": ("erick123", "Erick Logistics", "ADMIN"),
                    "lyn": ("lyn123", "Lyn Operations", "TRACKING"),
                    "precious": ("password123", "Precious Smiles", "BOOKING"),
                    "connie": ("connie123", "Connie Finance", "ACCOUNTS")
                }
                
                for username, data in account_credentials.items():
                    password, full_name, role_string = data
                    
                    new_profile = User(
                        username=username,
                        full_name=full_name,       
                        hashed_password=get_password_hash(password), 
                        role=role_string, 
                        is_active=True
                    )
                    db.add(new_profile)
                
                db.add(new_profile)
            db.commit()
            print("--- System Seeding Event Concluded Successfully! ---")
    except Exception as error:
        db.rollback()
        print(f"[Warning] Initialization seeding routine skipped: {error}")
    finally:
        db.close()
