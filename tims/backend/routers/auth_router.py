from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend import schemas, auth
from backend.database import get_db

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login") # Removed response_model to prevent field blocking
@router.post("/auth/login")     # Removed response_model to prevent field blocking
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(
        {"id": user.id, "username": user.username, "role": user.role.value}
    )
    
    # Returns a clean, flat dictionary matching your JavaScript requirements perfectly
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "full_name": user.full_name
    }


@router.get("/api/auth/me", response_model=schemas.UserOut)
@router.get("/auth/me", response_model=schemas.UserOut)
def me(current_user=Depends(auth.get_current_user)):
    return current_user
