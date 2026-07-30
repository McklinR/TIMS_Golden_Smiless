"""Dashboard KPI summary - role-filtered (financial margins are admin-only)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole, BookingStatus

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", response_model=schemas.DashboardSummary)
def summary(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    bookings = db.query(models.Booking).all()
    changed = False
    for b in bookings:
        if b.refresh_expiry():
            changed = True
    if changed:
        db.commit()

    week_ago = datetime.utcnow() - timedelta(days=7)

    active = [b for b in bookings if b.status in (
        BookingStatus.BOOKED, BookingStatus.LOADED, BookingStatus.IN_TRANSIT)]
    booked_awaiting = [b for b in bookings if b.status == BookingStatus.BOOKED]
    in_transit = [b for b in bookings if b.status == BookingStatus.IN_TRANSIT]
    expired_recent = [b for b in bookings if b.status == BookingStatus.EXPIRED and b.booking_date >= week_ago]

    total_loaded = sum(b.loaded_tonnage or 0 for b in bookings)
    total_offloaded = sum(o.nett_weight_received for o in db.query(models.Offloading).all())
    outstanding_balance = sum(b.balance_amount or 0 for b in bookings
                               if b.status in (BookingStatus.OFFLOADED, BookingStatus.LOADED, BookingStatus.IN_TRANSIT)
                               and b.payment_status.value != "FULLY_PAID")

    result = schemas.DashboardSummary(
        active_bookings=len(active),
        booked_awaiting_loading=len(booked_awaiting),
        in_transit=len(in_transit),
        expired_this_week=len(expired_recent),
        total_loaded_tonnage=round(total_loaded, 2),
        total_offloaded_tonnage=round(total_offloaded, 2),
        outstanding_balance_liability=round(outstanding_balance, 2),
    )

    if current_user.role == UserRole.ADMIN:
        result.total_gross_margin = round(sum(b.gross_broker_margin for b in bookings), 2)
        result.total_penalty_recovery = round(
            sum(o.penalty_margin_recovery for o in db.query(models.Offloading).all()), 2)

    return result
