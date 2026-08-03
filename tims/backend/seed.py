

"""Seed script for TIMS demo data."""

from datetime import datetime, timedelta, timezone

from backend import models
from backend.auth import get_password_hash
from backend.database import Base, SessionLocal, engine, ensure_booking_tracking_columns

Base.metadata.create_all(bind=engine)
ensure_booking_tracking_columns()


def _upsert_user(db, username: str, full_name: str, password: str, role: models.UserRole):
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        user = models.User(username=username)
        db.add(user)
    user.full_name = full_name
    user.hashed_password = get_password_hash(password)
    user.role = role
    user.is_active = True
    return user


def _upsert_booking(db, booking: models.Booking):
    existing = db.query(models.Booking).filter(models.Booking.horse_registration == booking.horse_registration).first()
    if existing is None:
        db.add(booking)
        return booking

    for field in (
        "booking_date",
        "trailer1_registration",
        "trailer2_registration",
        "driver_name",
        "passport_number",
        "eta",
        "origin",
        "client_id",
        "transporter_id",
        "client_rate",
        "transporter_rate",
        "client_penalty_rate",
        "transporter_penalty_rate",
        "created_by",
    ):
        setattr(existing, field, getattr(booking, field))
    existing.status = booking.status
    return existing


def seed():
    db = SessionLocal()
    try:
        erick = _upsert_user(db, "erick", "Erick Logistics", "erick123", models.UserRole.ADMIN)
        _upsert_user(db, "director", "Company Director", "director123", models.UserRole.ADMIN)
        _upsert_user(db, "lyn", "Lyn Operations", "lyn123", models.UserRole.TRACKING)
        _upsert_user(db, "precious", "Precious Smiles", "password123", models.UserRole.BOOKING)
        _upsert_user(db, "connie", "Connie Finance", "connie123", models.UserRole.ACCOUNTS)
        db.commit()

        icebay = db.query(models.Client).filter(models.Client.name == "Icebay").first()
        if icebay is None:
            icebay = models.Client(
                name="Icebay",
                contact_name="J. Moyo",
                contact_phone="+263 77 000 0001",
                default_client_rate=45.0,
                default_penalty_rate=200.0,
                notes="Chrome ore offtake, Costco terminal.",
            )
            db.add(icebay)

        eastlook = db.query(models.Client).filter(models.Client.name == "Eastlook").first()
        if eastlook is None:
            eastlook = models.Client(
                name="Eastlook",
                contact_name="T. Ncube",
                contact_phone="+263 77 000 0002",
                default_client_rate=48.0,
                default_penalty_rate=200.0,
                notes="Chrome ore offtake, Grindrod terminal.",
            )
            db.add(eastlook)
        db.commit()

        mogale = db.query(models.Transporter).filter(models.Transporter.name == "Mogale Transport").first()
        if mogale is None:
            mogale = models.Transporter(
                name="Mogale Transport",
                contact_name="S. Dube",
                contact_phone="+263 77 000 1001",
                default_transporter_rate=35.0,
                default_penalty_rate=250.0,
            )
            db.add(mogale)
            db.commit()

        _upsert_booking(
            db,
            models.Booking(
                booking_date=datetime.now(timezone.utc) - timedelta(hours=10),
                horse_registration="AFH1234",
                trailer1_registration="AFH1234T1",
                trailer2_registration="AFH1234T2",
                driver_name="Tendai Moyo",
                passport_number="ZW1234567",
                eta=datetime.now(timezone.utc) + timedelta(hours=14),
                origin="Shurugwi",
                status=models.BookingStatus.BOOKED,
                client_id=icebay.id,
                transporter_id=mogale.id,
                client_rate=icebay.default_client_rate,
                transporter_rate=mogale.default_transporter_rate,
                client_penalty_rate=icebay.default_penalty_rate,
                transporter_penalty_rate=mogale.default_penalty_rate,
                created_by=erick.id,
            ),
        )
        _upsert_booking(
            db,
            models.Booking(
                booking_date=datetime.now(timezone.utc) - timedelta(hours=60),
                horse_registration="ADZ5678",
                trailer1_registration="ADZ5678T1",
                driver_name="Farai Chikafu",
                passport_number="ZW7654321",
                eta=datetime.now(timezone.utc) - timedelta(hours=36),
                origin="Zvishavane",
                status=models.BookingStatus.BOOKED,
                client_id=eastlook.id,
                transporter_id=mogale.id,
                client_rate=eastlook.default_client_rate,
                transporter_rate=mogale.default_transporter_rate,
                client_penalty_rate=eastlook.default_penalty_rate,
                transporter_penalty_rate=mogale.default_penalty_rate,
                created_by=erick.id,
            ),
        )
        db.commit()

        print("Seed complete.")
        print("Login users:")
        print("  director / director123   (ADMIN)")
        print("  erick    / erick123      (ADMIN)")
        print("  lyn      / lyn123        (TRACKING)")
        print("  precious / password123   (BOOKING)")
        print("  connie   / connie123     (ACCOUNTS)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
