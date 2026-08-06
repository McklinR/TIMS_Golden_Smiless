"""Clients (confidential) and Transporters CRUD."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole

router = APIRouter(tags=["partners"])


def _current_client_rate(client: models.Client) -> tuple[float, float]:
    history = list(client.rate_history or [])
    if not history:
        return client.default_client_rate or 0.0, client.default_penalty_rate or 0.0
    selected = history[-1]
    return selected.client_rate or 0.0, selected.penalty_rate or 0.0


# ---------------- Clients (admin-only: contains confidential rate data) --------------
@router.post("/clients", response_model=schemas.ClientOut)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db),
                   _=Depends(auth.require_roles(UserRole.ADMIN))):
    client = models.Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    current_rate, current_penalty = _current_client_rate(client)
    client.current_client_rate = current_rate
    client.current_penalty_rate = current_penalty
    return client


@router.get("/clients", response_model=list[schemas.ClientOut])
def list_clients(db: Session = Depends(get_db),
                  _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS, UserRole.BOOKING))):
    clients = db.query(models.Client).all()
    for client in clients:
        current_rate, current_penalty = _current_client_rate(client)
        client.current_client_rate = current_rate
        client.current_penalty_rate = current_penalty
    return clients


@router.get("/clients/{client_id}", response_model=schemas.ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db),
                _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS))):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    current_rate, current_penalty = _current_client_rate(client)
    client.current_client_rate = current_rate
    client.current_penalty_rate = current_penalty
    return client


@router.get("/clients/{client_id}/rate-history", response_model=list[schemas.ClientRateHistoryOut])
def list_client_rate_history(client_id: int, db: Session = Depends(get_db),
                              _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS, UserRole.BOOKING))):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return db.query(models.ClientRateHistory).filter(models.ClientRateHistory.client_id == client_id).order_by(models.ClientRateHistory.effective_from.desc()).all()


@router.post("/clients/{client_id}/rate-history", response_model=schemas.ClientRateHistoryOut)
def create_client_rate_history(client_id: int, payload: schemas.ClientRateHistoryCreate, db: Session = Depends(get_db),
                                _=Depends(auth.require_roles(UserRole.ADMIN))):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    history = models.ClientRateHistory(
        client_id=client_id,
        client_rate=payload.client_rate,
        penalty_rate=payload.penalty_rate,
        effective_from=payload.effective_from or datetime.utcnow(),
        notes=payload.notes,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


# ---------------- Transporters (visible to booking/tracking/admin) -------------------
@router.post("/transporters", response_model=schemas.TransporterOut)
def create_transporter(payload: schemas.TransporterCreate, db: Session = Depends(get_db),
                        _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.BOOKING))):
    transporter = models.Transporter(**payload.model_dump())
    db.add(transporter)
    db.commit()
    db.refresh(transporter)
    return transporter


@router.get("/transporters", response_model=list[schemas.TransporterOut])
def list_transporters(db: Session = Depends(get_db), _=Depends(auth.get_current_user)):
    return db.query(models.Transporter).all()
