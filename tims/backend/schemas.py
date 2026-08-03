"""Pydantic schemas - request/response contracts for the TIMS API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from backend.models import UserRole, BookingStatus, PaymentStatus


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str
    role: UserRole


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: UserRole
    is_active: bool


# ---------------------------------------------------------------------------
# Clients / Transporters
# ---------------------------------------------------------------------------
class ClientCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    default_client_rate: float = 0.0
    default_penalty_rate: float = 0.0
    notes: Optional[str] = None


class ClientOut(ClientCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TransporterCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    default_transporter_rate: float = 0.0
    default_penalty_rate: float = 0.0
    notes: Optional[str] = None


class TransporterOut(TransporterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
class BookingCreate(BaseModel):
    horse_registration: str
    trailer1_registration: Optional[str] = None
    trailer2_registration: Optional[str] = None
    driver_name: str
    passport_number: Optional[str] = None
    eta: Optional[datetime] = None
    origin: Optional[str] = None
    client_id: int
    transporter_id: int
    # Optional overrides - default to the client/transporter's stored rate if omitted
    client_rate: Optional[float] = None
    transporter_rate: Optional[float] = None
    client_penalty_rate: Optional[float] = None
    transporter_penalty_rate: Optional[float] = None


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_date: datetime
    horse_registration: str
    trailer1_registration: Optional[str]
    trailer2_registration: Optional[str]
    driver_name: str
    passport_number: Optional[str]
    eta: Optional[datetime]
    status: BookingStatus
    loaded_date: Optional[datetime]
    loaded_tonnage: Optional[float]
    origin: Optional[str]
    location_status: Optional[str]
    tracking_status: Optional[str]
    tracking_timestamp: Optional[datetime]
    client_id: int
    transporter_id: int
    payment_status: PaymentStatus
    deposit_amount: float
    balance_amount: float

    # financial fields - stripped for non-admin roles by the router layer
    client_rate: Optional[float] = None
    transporter_rate: Optional[float] = None
    broker_margin_per_tonne: Optional[float] = None
    gross_broker_margin: Optional[float] = None


# ---------------------------------------------------------------------------
# Loading slips
# ---------------------------------------------------------------------------
class LoadingSlipCreate(BaseModel):
    booking_id: int
    ticket_no: str
    slip_date: Optional[datetime] = None
    time_in: Optional[str] = None
    time_out: Optional[str] = None
    driver_name: Optional[str] = None
    passport: Optional[str] = None
    horse: Optional[str] = None
    trailer: Optional[str] = None
    tare_mass: float
    gross_mass: float
    operator_signature: Optional[str] = None
    driver_signature: Optional[str] = None
    location: Optional[str] = None


class LoadingSlipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    ticket_no: str
    slip_date: Optional[datetime]
    tare_mass: float
    gross_mass: float
    net_mass: float
    location: Optional[str]


# ---------------------------------------------------------------------------
# Offloading
# ---------------------------------------------------------------------------
class OffloadingCreate(BaseModel):
    booking_id: int
    transaction_no: Optional[str] = None
    process_type: Optional[str] = "Receipt"
    transaction_status: Optional[str] = None
    pre_advice_no: Optional[str] = None
    client_reference_no: Optional[str] = None
    product: Optional[str] = "Chrome Ore"
    transporter_name: Optional[str] = None
    driver_name: Optional[str] = None
    horse_registration: Optional[str] = None
    trailer1: Optional[str] = None
    trailer2: Optional[str] = None
    first_weight: Optional[float] = None
    second_weight: Optional[float] = None
    tare_weight: Optional[float] = None
    nett_weight_received: float
    destination: Optional[str] = None


class OffloadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    transaction_no: Optional[str]
    nett_weight_received: float
    destination: Optional[str]
    shrinkage_tonnes: float
    client_penalty_charge: float
    transporter_penalty_charge: float
    penalty_margin_recovery: float


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
class TrackingLogCreate(BaseModel):
    booking_id: int
    raw_note: str


class TrackingLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    booking_id: int
    logged_at: datetime
    raw_note: str
    status_flag: Optional[str]
    location_guess: Optional[str]


class TrackingParseRequest(BaseModel):
    raw_whatsapp_text: str


class TrackingParseResponse(BaseModel):
    horse_registration: str
    current_location: str
    trip_status: str
    parsed_notes: str
    booking_id: int
    tracking_timestamp: datetime


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardSummary(BaseModel):
    active_bookings: int
    booked_awaiting_loading: int
    in_transit: int
    expired_this_week: int
    total_loaded_tonnage: float
    total_offloaded_tonnage: float
    outstanding_balance_liability: float
    total_gross_margin: Optional[float] = None  # admin only
    total_penalty_recovery: Optional[float] = None  # admin only
