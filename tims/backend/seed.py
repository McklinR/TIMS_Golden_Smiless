

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


def _upsert_client(db, **kwargs):
    client = db.query(models.Client).filter(models.Client.name == kwargs["name"]).first()
    if client is None:
        client = models.Client(**kwargs)
        db.add(client)
        return client

    for field, value in kwargs.items():
        setattr(client, field, value)
    return client


def _upsert_transporter(db, **kwargs):
    transporter = db.query(models.Transporter).filter(models.Transporter.name == kwargs["name"]).first()
    if transporter is None:
        transporter = models.Transporter(**kwargs)
        db.add(transporter)
        return transporter

    for field, value in kwargs.items():
        setattr(transporter, field, value)
    return transporter


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
        "loaded_date",
        "loaded_tonnage",
        "location_status",
        "tracking_status",
        "tracking_timestamp",
        "payment_status",
        "deposit_amount",
        "deposit_paid_at",
        "balance_amount",
        "balance_invoiced_at",
    ):
        setattr(existing, field, getattr(booking, field))
    existing.status = booking.status
    return existing


def _upsert_loading_slip(db, slip: models.LoadingSlip):
    existing = db.query(models.LoadingSlip).filter(models.LoadingSlip.booking_id == slip.booking_id).first()
    if existing is None:
        db.add(slip)
        return slip

    for field in (
        "ticket_no",
        "slip_date",
        "time_in",
        "time_out",
        "driver_name",
        "passport",
        "horse",
        "trailer",
        "tare_mass",
        "gross_mass",
        "net_mass",
        "operator_signature",
        "driver_signature",
        "location",
    ):
        setattr(existing, field, getattr(slip, field))
    return existing


def _upsert_offloading(db, offload: models.Offloading):
    existing = db.query(models.Offloading).filter(models.Offloading.booking_id == offload.booking_id).first()
    if existing is None:
        db.add(offload)
        return offload

    for field in (
        "transaction_no",
        "process_type",
        "transaction_status",
        "pre_advice_no",
        "client_reference_no",
        "product",
        "transporter_name",
        "driver_name",
        "horse_registration",
        "trailer1",
        "trailer2",
        "first_weight",
        "second_weight",
        "tare_weight",
        "nett_weight_received",
        "destination",
        "shrinkage_tonnes",
        "client_penalty_charge",
        "transporter_penalty_charge",
        "penalty_margin_recovery",
        "captured_at",
    ):
        setattr(existing, field, getattr(offload, field))
    return existing


def _upsert_tracking_log(db, booking_id: int, raw_note: str, logged_by: int, status_flag: str | None = None, location_guess: str | None = None):
    existing = (
        db.query(models.TrackingLog)
        .filter(models.TrackingLog.booking_id == booking_id, models.TrackingLog.raw_note == raw_note)
        .first()
    )
    if existing is not None:
        return existing

    log = models.TrackingLog(
        booking_id=booking_id,
        logged_by=logged_by,
        raw_note=raw_note,
        status_flag=status_flag,
        location_guess=location_guess,
    )
    db.add(log)
    return log


def _upsert_client_rate_history(db, client_id: int, client_rate: float, penalty_rate: float, effective_from, notes: str | None = None):
    existing = (
        db.query(models.ClientRateHistory)
        .filter(
            models.ClientRateHistory.client_id == client_id,
            models.ClientRateHistory.effective_from == effective_from,
        )
        .first()
    )
    if existing is None:
        db.add(
            models.ClientRateHistory(
                client_id=client_id,
                client_rate=client_rate,
                penalty_rate=penalty_rate,
                effective_from=effective_from,
                notes=notes,
            )
        )
        return

    existing.client_rate = client_rate
    existing.penalty_rate = penalty_rate
    existing.notes = notes


def seed():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        erick = _upsert_user(db, "erick", "Erick Logistics", "erick123", models.UserRole.ADMIN)
        _upsert_user(db, "director", "Company Director", "director123", models.UserRole.ADMIN)
        _upsert_user(db, "lyn", "Lyn Operations", "lyn123", models.UserRole.TRACKING)
        _upsert_user(db, "precious", "Precious Smiles", "password123", models.UserRole.BOOKING)
        _upsert_user(db, "edina", "Edina Finance", "edina123", models.UserRole.ACCOUNTS)
        db.commit()

        icebay = _upsert_client(
            db,
            name="Icebay",
            contact_name="J. Moyo",
            contact_phone="+263 77 000 0001",
            default_client_rate=45.0,
            default_penalty_rate=200.0,
            notes="Chrome ore offtake, Costco terminal.",
        )
        eastlook = _upsert_client(
            db,
            name="Eastlook",
            contact_name="T. Ncube",
            contact_phone="+263 77 000 0002",
            default_client_rate=48.0,
            default_penalty_rate=200.0,
            notes="Chrome ore offtake, Grindrod terminal.",
        )
        northbridge = _upsert_client(
            db,
            name="Northbridge Minerals",
            contact_name="M. Hove",
            contact_phone="+263 77 000 0003",
            default_client_rate=46.5,
            default_penalty_rate=210.0,
            notes="Demo client for active load and offload records.",
        )
        db.commit()

        mogale = _upsert_transporter(
            db,
            name="Mogale Transport",
            contact_name="S. Dube",
            contact_phone="+263 77 000 1001",
            default_transporter_rate=35.0,
            default_penalty_rate=250.0,
        )
        swiftline = _upsert_transporter(
            db,
            name="Swiftline Haulage",
            contact_name="P. Ndlovu",
            contact_phone="+263 77 000 1002",
            default_transporter_rate=36.5,
            default_penalty_rate=250.0,
        )
        horizon = _upsert_transporter(
            db,
            name="Horizon Logistics",
            contact_name="A. Moyo",
            contact_phone="+263 77 000 1003",
            default_transporter_rate=34.0,
            default_penalty_rate=240.0,
        )
        delta = _upsert_transporter(
            db,
            name="Delta Freight",
            contact_name="R. Sithole",
            contact_phone="+263 77 000 1004",
            default_transporter_rate=37.0,
            default_penalty_rate=255.0,
        )
        kappa = _upsert_transporter(
            db,
            name="Kappa Haulers",
            contact_name="T. Ncube",
            contact_phone="+263 77 000 1005",
            default_transporter_rate=33.5,
            default_penalty_rate=245.0,
        )
        atlas = _upsert_transporter(
            db,
            name="Atlas Logistics",
            contact_name="M. Dube",
            contact_phone="+263 77 000 1006",
            default_transporter_rate=38.25,
            default_penalty_rate=260.0,
        )
        db.commit()

        _upsert_client_rate_history(db, icebay.id, 44.0, 195.0, now - timedelta(days=60), "Old contract rate")
        _upsert_client_rate_history(db, icebay.id, 45.0, 200.0, now - timedelta(days=20), "Current rate")
        _upsert_client_rate_history(db, eastlook.id, 47.0, 200.0, now - timedelta(days=45), "Earlier rate")
        _upsert_client_rate_history(db, eastlook.id, 48.0, 200.0, now - timedelta(days=10), "Updated terminal rate")
        _upsert_client_rate_history(db, northbridge.id, 46.5, 210.0, now - timedelta(days=15), "Seed demo rate")

        _upsert_booking(
            db,
            models.Booking(
                booking_date=now - timedelta(hours=10),
                horse_registration="AFH1234",
                trailer1_registration="AFH1234T1",
                trailer2_registration="AFH1234T2",
                driver_name="Tendai Moyo",
                passport_number="ZW1234567",
                eta=now + timedelta(hours=14),
                origin="Shurugwi",
                status=models.BookingStatus.BOOKED,
                client_id=icebay.id,
                transporter_id=mogale.id,
                client_rate=45.0,
                transporter_rate=mogale.default_transporter_rate,
                client_penalty_rate=200.0,
                transporter_penalty_rate=mogale.default_penalty_rate,
                created_by=erick.id,
            ),
        )
        _upsert_booking(
            db,
            models.Booking(
                booking_date=now - timedelta(hours=12),
                horse_registration="ADZ5678",
                trailer1_registration="ADZ5678T1",
                trailer2_registration="ADZ5678T2",
                driver_name="Farai Chikafu",
                passport_number="ZW7654321",
                eta=now + timedelta(hours=6),
                origin="Zvishavane",
                status=models.BookingStatus.IN_TRANSIT,
                client_id=eastlook.id,
                transporter_id=mogale.id,
                client_rate=48.0,
                transporter_rate=mogale.default_transporter_rate,
                client_penalty_rate=200.0,
                transporter_penalty_rate=mogale.default_penalty_rate,
                created_by=erick.id,
                loaded_date=now - timedelta(hours=3),
                loaded_tonnage=21.85,
                location_status="Rutenga",
                tracking_status="ON_ROUTE",
                tracking_timestamp=now - timedelta(minutes=35),
            ),
        )
        _upsert_booking(
            db,
            models.Booking(
                booking_date=now - timedelta(hours=18),
                horse_registration="AHT9012",
                trailer1_registration="AHT9012T1",
                trailer2_registration="AHT9012T2",
                driver_name="Nyasha Chikandiwa",
                passport_number="ZW1122334",
                eta=now - timedelta(hours=1),
                origin="Mberengwa",
                status=models.BookingStatus.OFFLOADED,
                client_id=northbridge.id,
                transporter_id=delta.id,
                client_rate=northbridge.default_client_rate,
                transporter_rate=delta.default_transporter_rate,
                client_penalty_rate=northbridge.default_penalty_rate,
                transporter_penalty_rate=delta.default_penalty_rate,
                created_by=erick.id,
                loaded_date=now - timedelta(hours=8),
                loaded_tonnage=23.4,
                location_status="Grindrod Terminal",
                tracking_status="OFFLOADED",
                tracking_timestamp=now - timedelta(minutes=18),
                payment_status=models.PaymentStatus.BALANCE_INVOICED,
                deposit_amount=319.02,
                deposit_paid_at=now - timedelta(hours=5),
                balance_amount=79.76,
                balance_invoiced_at=now - timedelta(minutes=12),
            ),
        )
        _upsert_booking(
            db,
            models.Booking(
                booking_date=now - timedelta(hours=70),
                horse_registration="ALP4411",
                trailer1_registration="ALP4411T1",
                driver_name="Blessing Muroyiwa",
                passport_number="ZW9988776",
                eta=now - timedelta(hours=30),
                origin="Shurugwi",
                status=models.BookingStatus.BOOKED,
                client_id=icebay.id,
                transporter_id=atlas.id,
                client_rate=44.0,
                transporter_rate=horizon.default_transporter_rate,
                client_penalty_rate=195.0,
                transporter_penalty_rate=atlas.default_penalty_rate,
                created_by=erick.id,
            ),
        )
        db.commit()

        booked = db.query(models.Booking).filter(models.Booking.horse_registration == "AFH1234").first()
        loaded = db.query(models.Booking).filter(models.Booking.horse_registration == "ADZ5678").first()
        offloaded = db.query(models.Booking).filter(models.Booking.horse_registration == "AHT9012").first()

        if booked is not None:
            booked.status = models.BookingStatus.BOOKED
            booked.payment_status = models.PaymentStatus.NONE

        if loaded is not None:
            loaded.status = models.BookingStatus.IN_TRANSIT
            loaded.loaded_date = now - timedelta(hours=3)
            loaded.loaded_tonnage = 21.85
            loaded.deposit_amount = round(0.80 * loaded.transporter_rate * loaded.loaded_tonnage, 2)
            loaded.balance_amount = round(0.20 * loaded.transporter_rate * loaded.loaded_tonnage, 2)
            loaded.payment_status = models.PaymentStatus.NONE
            loaded.location_status = "Rutenga"
            loaded.tracking_status = "ON_ROUTE"
            loaded.tracking_timestamp = now - timedelta(minutes=35)

        if offloaded is not None:
            offloaded.status = models.BookingStatus.OFFLOADED
            offloaded.loaded_date = now - timedelta(hours=8)
            offloaded.loaded_tonnage = 23.4
            offloaded.deposit_amount = round(0.80 * offloaded.transporter_rate * offloaded.loaded_tonnage, 2)
            offloaded.balance_amount = round(0.20 * offloaded.transporter_rate * offloaded.loaded_tonnage, 2)
            offloaded.payment_status = models.PaymentStatus.BALANCE_INVOICED
            offloaded.deposit_paid_at = now - timedelta(hours=5)
            offloaded.balance_invoiced_at = now - timedelta(minutes=12)
            offloaded.location_status = "Grindrod Terminal"
            offloaded.tracking_status = "OFFLOADED"
            offloaded.tracking_timestamp = now - timedelta(minutes=18)

        db.commit()

        _upsert_loading_slip(
            db,
            models.LoadingSlip(
                booking_id=loaded.id,
                ticket_no="WB-1001",
                slip_date=now - timedelta(hours=3),
                time_in="06:55",
                time_out="07:48",
                driver_name=loaded.driver_name,
                passport=loaded.passport_number,
                horse=loaded.horse_registration,
                trailer=loaded.trailer1_registration,
                tare_mass=14.55,
                gross_mass=36.40,
                net_mass=21.85,
                operator_signature="Weighbridge Clerk",
                driver_signature=loaded.driver_name,
                location=loaded.origin,
            ),
        )
        _upsert_loading_slip(
            db,
            models.LoadingSlip(
                booking_id=offloaded.id,
                ticket_no="WB-1002",
                slip_date=now - timedelta(hours=8),
                time_in="03:30",
                time_out="04:10",
                driver_name=offloaded.driver_name,
                passport=offloaded.passport_number,
                horse=offloaded.horse_registration,
                trailer=offloaded.trailer1_registration,
                tare_mass=15.05,
                gross_mass=38.45,
                net_mass=23.40,
                operator_signature="Weighbridge Clerk",
                driver_signature=offloaded.driver_name,
                location=offloaded.origin,
            ),
        )
        _upsert_offloading(
            db,
            models.Offloading(
                booking_id=offloaded.id,
                transaction_no="GRD-9001",
                process_type="Receipt",
                transaction_status="Captured",
                pre_advice_no="PA-7788",
                client_reference_no="NBM-TRIP-01",
                product="Chrome Ore",
                transporter_name=swiftline.name,
                driver_name=offloaded.driver_name,
                horse_registration=offloaded.horse_registration,
                trailer1=offloaded.trailer1_registration,
                trailer2=offloaded.trailer2_registration,
                first_weight=38.45,
                second_weight=36.30,
                tare_weight=15.05,
                nett_weight_received=21.25,
                destination="Grindrod",
                shrinkage_tonnes=2.15,
                client_penalty_charge=451.50,
                transporter_penalty_charge=537.50,
                penalty_margin_recovery=86.00,
                captured_at=now - timedelta(minutes=12),
            ),
        )
        _upsert_tracking_log(
            db,
            booking_id=loaded.id,
            raw_note="Driver says on route from Rutenga, ETA still on schedule.",
            logged_by=erick.id,
            status_flag="ON_ROUTE",
            location_guess="Rutenga",
        )
        _upsert_tracking_log(
            db,
            booking_id=offloaded.id,
            raw_note="Truck arrived at Grindrod terminal and offloading completed.",
            logged_by=erick.id,
            status_flag="OFFLOADED",
            location_guess="Grindrod Terminal",
        )
        _upsert_tracking_log(
            db,
            booking_id=offloaded.id,
            raw_note="Previously delayed at Beitbridge border, now cleared.",
            logged_by=erick.id,
            status_flag="DELAYED",
            location_guess="Beitbridge Border",
        )
        db.commit()

        print("Seed complete.")
        print("Login users:")
        print("  director / director123   (ADMIN)")
        print("  erick    / erick123      (ADMIN)")
        print("  lyn      / lyn123        (TRACKING)")
        print("  precious / password123   (BOOKING)")
        print("  edina    / edina123      (ACCOUNTS)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
