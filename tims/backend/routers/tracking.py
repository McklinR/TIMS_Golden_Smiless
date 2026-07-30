"""Route tracking call-log endpoints (Lyn & Precious)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole
from backend.nlp import parse_tracking_note, parse_whatsapp_tracking_text, normalize_registration

router = APIRouter(tags=["tracking"])


@router.post("/tracking-logs", response_model=schemas.TrackingLogOut)
def create_tracking_log(payload: schemas.TrackingLogCreate, db: Session = Depends(get_db),
                         current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.TRACKING))):
    booking = db.get(models.Booking, payload.booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")

    status_flag, location_guess = parse_tracking_note(payload.raw_note)

    log = models.TrackingLog(
        booking_id=payload.booking_id,
        logged_by=current_user.id,
        raw_note=payload.raw_note,
        status_flag=status_flag,
        location_guess=location_guess,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/tracking-logs/{booking_id}", response_model=list[schemas.TrackingLogOut])
def list_tracking_logs(booking_id: int, db: Session = Depends(get_db), _=Depends(auth.get_current_user)):
    logs = db.query(models.TrackingLog).filter(models.TrackingLog.booking_id == booking_id) \
        .order_by(models.TrackingLog.logged_at.desc()).all()
    return logs


@router.get("/tracking-logs", response_model=list[schemas.TrackingLogOut])
def list_all_recent_logs(limit: int = 50, db: Session = Depends(get_db), _=Depends(auth.get_current_user)):
    return db.query(models.TrackingLog).order_by(models.TrackingLog.logged_at.desc()).limit(limit).all()


@router.post("/api/tracking/parse-note", response_model=schemas.TrackingParseResponse)
def parse_note(
    payload: schemas.TrackingParseRequest,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_roles(UserRole.ADMIN, UserRole.TRACKING)),
):
    extraction = parse_whatsapp_tracking_text(payload.raw_whatsapp_text)
    if not extraction.horse_registration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract horse_registration from WhatsApp text",
        )

    normalized_registration = normalize_registration(extraction.horse_registration)
    booking = (
        db.query(models.Booking)
        .filter(
            func.replace(func.replace(func.upper(models.Booking.horse_registration), " ", ""), "-", "") == normalized_registration,
            models.Booking.status.in_(
                [models.BookingStatus.BOOKED, models.BookingStatus.LOADED, models.BookingStatus.IN_TRANSIT]
            ),
        )
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active booking found for horse_registration '{extraction.horse_registration}'",
        )

    now = datetime.now(timezone.utc)
    booking.location_status = extraction.current_location
    booking.tracking_status = extraction.trip_status
    booking.tracking_timestamp = now
    if extraction.trip_status == "OFFLOADED":
        booking.status = models.BookingStatus.OFFLOADED
    elif booking.status == models.BookingStatus.BOOKED:
        booking.status = models.BookingStatus.IN_TRANSIT

    log = models.TrackingLog(
        booking_id=booking.id,
        logged_by=current_user.id,
        raw_note=payload.raw_whatsapp_text,
        status_flag=extraction.trip_status,
        location_guess=extraction.current_location,
    )
    db.add(log)
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {
        "horse_registration": booking.horse_registration,
        "current_location": booking.location_status or "UNKNOWN",
        "trip_status": booking.tracking_status or "EN ROUTE",
        "parsed_notes": extraction.parsed_notes,
        "booking_id": booking.id,
        "tracking_timestamp": booking.tracking_timestamp,
    }
