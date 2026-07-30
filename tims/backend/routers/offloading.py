"""
Offloading capture (terminal / Grindrod slip) and shrinkage penalty logic.

Shrinkage = loaded_tonnage (mine weighbridge) - nett_weight_received (terminal)
If shrinkage > 0:
  client_penalty_charge        = shrinkage * client_penalty_rate       (client bills broker)
  transporter_penalty_charge   = shrinkage * transporter_penalty_rate  (broker bills transporter)
  penalty_margin_recovery      = transporter_penalty_charge - client_penalty_charge
    (the protective margin the broker keeps, per the spec's $250 vs $200 example -> $50/tonne)

The transporter's outstanding 20% balance is reduced by the
transporter_penalty_charge before Connie invoices it.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole, BookingStatus, PaymentStatus

router = APIRouter(tags=["offloading"])


@router.post("/offloading", response_model=schemas.OffloadingOut)
def create_offloading(payload: schemas.OffloadingCreate, db: Session = Depends(get_db),
                       _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.TRACKING, UserRole.BOOKING))):
    booking = db.get(models.Booking, payload.booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.offloading is not None:
        raise HTTPException(400, "Offloading already captured for this booking")
    if not booking.loaded_tonnage:
        raise HTTPException(400, "Cannot capture offloading before a loading slip has been recorded")

    shrinkage = max(0.0, round(booking.loaded_tonnage - payload.nett_weight_received, 3))
    client_penalty_charge = round(shrinkage * (booking.client_penalty_rate or 0.0), 2)
    transporter_penalty_charge = round(shrinkage * (booking.transporter_penalty_rate or 0.0), 2)
    penalty_margin_recovery = round(transporter_penalty_charge - client_penalty_charge, 2)

    offload = models.Offloading(
        booking_id=payload.booking_id,
        transaction_no=payload.transaction_no,
        process_type=payload.process_type,
        transaction_status=payload.transaction_status,
        pre_advice_no=payload.pre_advice_no,
        client_reference_no=payload.client_reference_no,
        product=payload.product,
        transporter_name=payload.transporter_name,
        driver_name=payload.driver_name,
        horse_registration=payload.horse_registration,
        trailer1=payload.trailer1,
        trailer2=payload.trailer2,
        first_weight=payload.first_weight,
        second_weight=payload.second_weight,
        tare_weight=payload.tare_weight,
        nett_weight_received=payload.nett_weight_received,
        destination=payload.destination,
        shrinkage_tonnes=shrinkage,
        client_penalty_charge=client_penalty_charge,
        transporter_penalty_charge=transporter_penalty_charge,
        penalty_margin_recovery=penalty_margin_recovery,
        captured_at=datetime.utcnow(),
    )
    db.add(offload)

    # reduce the transporter's outstanding balance by their penalty share
    booking.balance_amount = round(max(0.0, booking.balance_amount - transporter_penalty_charge), 2)
    booking.status = BookingStatus.OFFLOADED

    db.commit()
    db.refresh(offload)
    return offload


@router.get("/offloading/{booking_id}", response_model=schemas.OffloadingOut)
def get_offloading(booking_id: int, db: Session = Depends(get_db), _=Depends(auth.get_current_user)):
    offload = db.query(models.Offloading).filter(models.Offloading.booking_id == booking_id).first()
    if not offload:
        raise HTTPException(404, "No offloading captured for this booking")
    return offload


@router.post("/bookings/{booking_id}/invoice-balance", response_model=schemas.BookingOut)
def invoice_balance(booking_id: int, db: Session = Depends(get_db),
                     current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS))):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status != BookingStatus.OFFLOADED:
        raise HTTPException(400, "Balance can only be invoiced after clean offloading verification")
    if booking.payment_status != PaymentStatus.DEPOSIT_PAID:
        raise HTTPException(400, "Deposit must be paid before the balance can be invoiced")

    booking.payment_status = PaymentStatus.BALANCE_INVOICED
    booking.balance_invoiced_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    from backend.routers.bookings import _to_out
    return _to_out(booking, current_user.role)


@router.post("/bookings/{booking_id}/mark-fully-paid", response_model=schemas.BookingOut)
def mark_fully_paid(booking_id: int, db: Session = Depends(get_db),
                     current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS))):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.payment_status != PaymentStatus.BALANCE_INVOICED:
        raise HTTPException(400, "Balance must be invoiced before it can be marked fully paid")
    booking.payment_status = PaymentStatus.FULLY_PAID
    db.commit()
    db.refresh(booking)

    from backend.routers.bookings import _to_out
    return _to_out(booking, current_user.role)
