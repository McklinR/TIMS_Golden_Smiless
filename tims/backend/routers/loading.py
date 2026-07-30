"""
Loading slip capture (Erick, at the mine weighbridge).

Uploading a loading slip:
  1. Computes net_mass = gross_mass - tare_mass
  2. Transitions the booking BOOKED -> LOADED, stamps loaded_date/loaded_tonnage
  3. Pre-computes the 80% deposit / 20% balance split against the
     transporter_rate, ready for Connie to release via /bookings/{id}/pay-deposit
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole, BookingStatus, PaymentStatus

router = APIRouter(tags=["loading"])

DEPOSIT_SPLIT = 0.80
BALANCE_SPLIT = 0.20


@router.post("/loading-slips", response_model=schemas.LoadingSlipOut)
def create_loading_slip(payload: schemas.LoadingSlipCreate, db: Session = Depends(get_db),
                         _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.BOOKING))):
    booking = db.get(models.Booking, payload.booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.loading_slip is not None:
        raise HTTPException(400, "This booking already has a loading slip captured")
    if booking.status == BookingStatus.EXPIRED:
        raise HTTPException(400, "Booking has EXPIRED - reallocate the volume to a replacement truck instead")

    net_mass = round(payload.gross_mass - payload.tare_mass, 3)
    if net_mass <= 0:
        raise HTTPException(400, "Net mass must be positive (gross_mass must exceed tare_mass)")

    slip = models.LoadingSlip(
        booking_id=payload.booking_id,
        ticket_no=payload.ticket_no,
        slip_date=payload.slip_date or datetime.utcnow(),
        time_in=payload.time_in,
        time_out=payload.time_out,
        driver_name=payload.driver_name or booking.driver_name,
        passport=payload.passport or booking.passport_number,
        horse=payload.horse or booking.horse_registration,
        trailer=payload.trailer or booking.trailer1_registration,
        tare_mass=payload.tare_mass,
        gross_mass=payload.gross_mass,
        net_mass=net_mass,
        operator_signature=payload.operator_signature,
        driver_signature=payload.driver_signature,
        location=payload.location or booking.origin,
    )
    db.add(slip)

    booking.status = BookingStatus.LOADED
    booking.loaded_date = slip.slip_date
    booking.loaded_tonnage = net_mass
    booking.deposit_amount = round(DEPOSIT_SPLIT * booking.transporter_rate * net_mass, 2)
    booking.balance_amount = round(BALANCE_SPLIT * booking.transporter_rate * net_mass, 2)

    db.commit()
    db.refresh(slip)
    return slip


@router.get("/loading-slips/{booking_id}", response_model=schemas.LoadingSlipOut)
def get_loading_slip(booking_id: int, db: Session = Depends(get_db), _=Depends(auth.get_current_user)):
    slip = db.query(models.LoadingSlip).filter(models.LoadingSlip.booking_id == booking_id).first()
    if not slip:
        raise HTTPException(404, "No loading slip captured for this booking")
    return slip


@router.post("/bookings/{booking_id}/pay-deposit", response_model=schemas.BookingOut)
def pay_deposit(booking_id: int, db: Session = Depends(get_db),
                 current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS))):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status != BookingStatus.LOADED and booking.status not in (BookingStatus.IN_TRANSIT, BookingStatus.OFFLOADED):
        raise HTTPException(400, "Deposit can only be released once a loading slip has been captured")
    if booking.payment_status != PaymentStatus.NONE:
        raise HTTPException(400, f"Deposit already processed (current status: {booking.payment_status.value})")

    booking.payment_status = PaymentStatus.DEPOSIT_PAID
    booking.deposit_paid_at = datetime.utcnow()
    if booking.status == BookingStatus.LOADED:
        booking.status = BookingStatus.IN_TRANSIT
    db.commit()
    db.refresh(booking)

    from backend.routers.bookings import _to_out
    return _to_out(booking, current_user.role)
