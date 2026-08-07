"""
Booking lifecycle endpoints.

Handles:
  - Creating bookings (Erick sources a truck)
  - Listing/reading bookings, with the 48h expiry rule applied lazily on
    every read (any BOOKED record past its SLA flips to EXPIRED before
    being returned)
  - Financial field scrubbing: only ADMIN sees client_rate / transporter_rate
    / margin figures. Other roles get those fields nulled out.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole, BookingStatus


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_client_rate(client: models.Client, booking_date: datetime | None = None) -> tuple[float, float]:
    history = list(client.rate_history or [])
    if not history:
        return client.default_client_rate or 0.0, client.default_penalty_rate or 0.0

    booking_date = _to_utc(booking_date or datetime.now(timezone.utc))

    applicable = [item for item in history if _to_utc(item.effective_from) <= booking_date]
    selected = applicable[-1] if applicable else history[0]
    return selected.client_rate or 0.0, selected.penalty_rate or 0.0

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _apply_expiry_and_commit(db: Session, bookings: list[models.Booking]) -> None:
    changed = False
    for b in bookings:
        if b.refresh_expiry():
            changed = True
    if changed:
        db.commit()


def _to_out(booking: models.Booking, role: UserRole) -> schemas.BookingOut:
    out = schemas.BookingOut.model_validate(booking)
    if role != UserRole.ADMIN:
        out.client_rate = None
        out.transporter_rate = None
        out.broker_margin_per_tonne = None
        out.gross_broker_margin = None
    else:
        out.broker_margin_per_tonne = booking.broker_margin_per_tonne
        out.gross_broker_margin = booking.gross_broker_margin
    return out


@router.post("", response_model=schemas.BookingOut)
def create_booking(payload: schemas.BookingCreate, db: Session = Depends(get_db),
                    current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.BOOKING))):
    client = db.get(models.Client, payload.client_id)
    transporter = db.get(models.Transporter, payload.transporter_id)
    if not client or not transporter:
        raise HTTPException(404, "Client or transporter not found")

    booking = models.Booking(
        horse_registration=payload.horse_registration,
        trailer1_registration=payload.trailer1_registration,
        trailer2_registration=payload.trailer2_registration,
        driver_name=payload.driver_name,
        passport_number=payload.passport_number,
        eta=payload.eta,
        origin=payload.origin,
        client_id=payload.client_id,
        transporter_id=payload.transporter_id,
        client_rate=payload.client_rate if payload.client_rate is not None else _get_client_rate(client, payload.eta or datetime.now(timezone.utc))[0],
        transporter_rate=payload.transporter_rate if payload.transporter_rate is not None else transporter.default_transporter_rate,
        client_penalty_rate=payload.client_penalty_rate if payload.client_penalty_rate is not None else _get_client_rate(client, payload.eta or datetime.now(timezone.utc))[1],
        transporter_penalty_rate=payload.transporter_penalty_rate if payload.transporter_penalty_rate is not None else transporter.default_penalty_rate,
        status=BookingStatus.BOOKED,
        booking_date=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_out(booking, current_user.role)


@router.get("", response_model=list[schemas.BookingOut])
def list_bookings(status_filter: BookingStatus | None = None, db: Session = Depends(get_db),
                   current_user=Depends(auth.get_current_user)):
    query = db.query(models.Booking)
    bookings = query.all()
    _apply_expiry_and_commit(db, bookings)
    if status_filter:
        bookings = [b for b in bookings if b.status == status_filter]
    bookings.sort(key=lambda b: b.booking_date, reverse=True)
    return [_to_out(b, current_user.role) for b in bookings]


@router.get("/{booking_id}", response_model=schemas.BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db),
                 current_user=Depends(auth.get_current_user)):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    _apply_expiry_and_commit(db, [booking])
    return _to_out(booking, current_user.role)


@router.post("/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db),
                    current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.BOOKING))):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status not in (BookingStatus.BOOKED, BookingStatus.EXPIRED):
        raise HTTPException(400, "Only BOOKED or EXPIRED bookings can be cancelled")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return _to_out(booking, current_user.role)
