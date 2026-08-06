"""
SQLAlchemy models for TIMS.

Covers the full trip lifecycle:
  Booking (BOOKED -> LOADED -> EXPIRED)  -->  LoadingSlip  -->  Offloading

and the financial arbitrage logic described in the business spec:
  - Broker margin        = client_rate - transporter_rate (per tonne)
  - 80/20 cash flow split on the transporter payout
  - Split shrinkage penalty rates (client -> broker, broker -> transporter)
"""
import enum
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship

from backend.database import Base

BOOKING_EXPIRY_HOURS = 48


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"                # Director - full financial visibility
    BOOKING = "BOOKING"            # Erick - booking & loading
    TRACKING = "TRACKING"          # Lyn & Precious - route operations
    ACCOUNTS = "ACCOUNTS"          # Connie - invoicing & accounts payable


class BookingStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    LOADED = "LOADED"
    IN_TRANSIT = "IN_TRANSIT"
    OFFLOADED = "OFFLOADED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    NONE = "NONE"
    DEPOSIT_PAID = "DEPOSIT_PAID"
    BALANCE_INVOICED = "BALANCE_INVOICED"
    FULLY_PAID = "FULLY_PAID"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    full_name = Column(String(128), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Client(Base):
    """Confidential client (e.g. Icebay, Eastlook). True identity + rate
    is admin-only information - other roles only ever see the booking's
    public reference, never this table directly."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    contact_name = Column(String(128))
    contact_phone = Column(String(64))
    contact_email = Column(String(128))
    default_client_rate = Column(Float, default=0.0)          # $ per tonne
    default_penalty_rate = Column(Float, default=0.0)         # $ per lost tonne, client -> broker
    notes = Column(Text)

    bookings = relationship("Booking", back_populates="client")
    rate_history = relationship("ClientRateHistory", back_populates="client", order_by="ClientRateHistory.effective_from")


class Transporter(Base):
    __tablename__ = "transporters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    contact_name = Column(String(128))
    contact_phone = Column(String(64))
    default_transporter_rate = Column(Float, default=0.0)     # $ per tonne
    default_penalty_rate = Column(Float, default=0.0)         # $ per lost tonne, broker -> transporter
    notes = Column(Text)

    bookings = relationship("Booking", back_populates="transporter")


class ClientRateHistory(Base):
    __tablename__ = "client_rate_history"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    client_rate = Column(Float, nullable=False)
    penalty_rate = Column(Float, nullable=False, default=0.0)
    effective_from = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text)

    client = relationship("Client", back_populates="rate_history")


class Booking(Base):
    """The master trip record - mirrors the Excel booking sheet."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    horse_registration = Column(String(32), nullable=False)
    trailer1_registration = Column(String(32))
    trailer2_registration = Column(String(32))
    driver_name = Column(String(128), nullable=False)
    passport_number = Column(String(64))

    eta = Column(DateTime)
    status = Column(Enum(BookingStatus), default=BookingStatus.BOOKED, nullable=False)

    loaded_date = Column(DateTime)
    loaded_tonnage = Column(Float)          # filled in once the loading slip is captured
    origin = Column(String(128))            # e.g. Lalapanzi, Mapanzure, NETA...
    location_status = Column(String(128))
    tracking_status = Column(String(32))
    tracking_timestamp = Column(DateTime)

    client_id = Column(Integer, ForeignKey("clients.id"))
    transporter_id = Column(Integer, ForeignKey("transporters.id"))

    # Rates are snapshotted onto the booking at creation time so historic
    # margin figures never shift if a client/transporter's default rate
    # changes later.
    client_rate = Column(Float, default=0.0)          # $ per tonne, client -> broker
    transporter_rate = Column(Float, default=0.0)     # $ per tonne, broker -> transporter
    client_penalty_rate = Column(Float, default=0.0)  # $ per lost tonne
    transporter_penalty_rate = Column(Float, default=0.0)

    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.NONE, nullable=False)
    deposit_amount = Column(Float, default=0.0)
    deposit_paid_at = Column(DateTime)
    balance_amount = Column(Float, default=0.0)
    balance_invoiced_at = Column(DateTime)

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="bookings")
    transporter = relationship("Transporter", back_populates="bookings")
    loading_slip = relationship("LoadingSlip", back_populates="booking", uselist=False)
    offloading = relationship("Offloading", back_populates="booking", uselist=False)
    tracking_logs = relationship("TrackingLog", back_populates="booking", order_by="TrackingLog.logged_at")

    # ---- business logic helpers -------------------------------------------------

    @property
    def expiry_deadline(self) -> datetime:
        return self.booking_date + timedelta(hours=BOOKING_EXPIRY_HOURS)

    def refresh_expiry(self) -> bool:
        """Auto-flip BOOKED -> EXPIRED once the 48h SLA has passed with no
        loading slip. Returns True if the status changed (caller should commit)."""
        if self.status == BookingStatus.BOOKED and datetime.utcnow() > self.expiry_deadline:
            self.status = BookingStatus.EXPIRED
            return True
        return False

    @property
    def broker_margin_per_tonne(self) -> float:
        return (self.client_rate or 0.0) - (self.transporter_rate or 0.0)

    @property
    def gross_broker_margin(self) -> float:
        if not self.loaded_tonnage:
            return 0.0
        return self.broker_margin_per_tonne * self.loaded_tonnage


class LoadingSlip(Base):
    """Mirrors the physical weighbridge ticket."""
    __tablename__ = "loading_slips"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)

    ticket_no = Column(String(64), unique=True, nullable=False)
    slip_date = Column(DateTime, default=datetime.utcnow)
    time_in = Column(String(16))
    time_out = Column(String(16))

    driver_name = Column(String(128))
    passport = Column(String(64))
    horse = Column(String(32))
    trailer = Column(String(32))

    tare_mass = Column(Float, nullable=False)      # 1st mass
    gross_mass = Column(Float, nullable=False)      # 2nd mass
    net_mass = Column(Float, nullable=False)         # calculated loaded tonnage

    operator_signature = Column(String(128))
    driver_signature = Column(String(128))

    location = Column(String(128))   # origin, e.g. Shurugwi

    booking = relationship("Booking", back_populates="loading_slip")


class Offloading(Base):
    """Mirrors the Grindrod / terminal offloading slip."""
    __tablename__ = "offloadings"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)

    transaction_no = Column(String(64))
    process_type = Column(String(64), default="Receipt")
    transaction_status = Column(String(64))
    pre_advice_no = Column(String(64))
    client_reference_no = Column(String(64))
    product = Column(String(64), default="Chrome Ore")

    transporter_name = Column(String(128))
    driver_name = Column(String(128))
    horse_registration = Column(String(32))
    trailer1 = Column(String(32))
    trailer2 = Column(String(32))

    first_weight = Column(Float)
    second_weight = Column(Float)
    tare_weight = Column(Float)
    nett_weight_received = Column(Float, nullable=False)   # destination tonnage

    first_weigh_at = Column(DateTime)
    second_weigh_at = Column(DateTime)

    destination = Column(String(128))   # e.g. Costco, Grindrod, Vayela

    # shrinkage - computed and cached at offload-capture time
    shrinkage_tonnes = Column(Float, default=0.0)
    client_penalty_charge = Column(Float, default=0.0)     # client charges broker
    transporter_penalty_charge = Column(Float, default=0.0)  # broker charges transporter
    penalty_margin_recovery = Column(Float, default=0.0)    # difference kept by broker

    captured_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="offloading")


class TrackingLog(Base):
    """Manual phone check-in call log for route tracking (Lyn & Precious)."""
    __tablename__ = "tracking_logs"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)

    logged_at = Column(DateTime, default=datetime.utcnow)
    logged_by = Column(Integer, ForeignKey("users.id"))

    raw_note = Column(Text)               # free-text note as typed/spoken
    status_flag = Column(String(32))      # parsed quick-flag, e.g. ON_ROUTE, BORDER, BREAKDOWN, ARRIVED, DELAYED
    location_guess = Column(String(128))  # parsed location entity, if any

    booking = relationship("Booking", back_populates="tracking_logs")
