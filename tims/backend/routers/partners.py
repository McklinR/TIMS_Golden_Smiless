"""Clients (confidential) and Transporters CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas, models, auth
from backend.database import get_db
from backend.models import UserRole

router = APIRouter(tags=["partners"])


# ---------------- Clients (admin-only: contains confidential rate data) --------------
@router.post("/clients", response_model=schemas.ClientOut)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db),
                   _=Depends(auth.require_roles(UserRole.ADMIN))):
    client = models.Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/clients", response_model=list[schemas.ClientOut])
def list_clients(db: Session = Depends(get_db),
                  _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS, UserRole.BOOKING))):
    return db.query(models.Client).all()


@router.get("/clients/{client_id}", response_model=schemas.ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db),
                _=Depends(auth.require_roles(UserRole.ADMIN, UserRole.ACCOUNTS))):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client


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
