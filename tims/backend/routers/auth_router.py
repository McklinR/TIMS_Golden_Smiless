from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend import auth, models
from backend.database import get_db

router = APIRouter(tags=["auth"])


def ensure_database_is_populated(db: Session):
    """Checks if the user table is completely empty on request and force-seeds the baseline accounts."""
    try:
        # Check if the users table exists and count rows
        user_count = db.execute(text("SELECT count(*) FROM users")).scalar()
        
        if user_count == 0:
            print("--- Emergency Database Population Event Triggered ---")
            from backend.models import User
            from backend.auth import get_password_hash
            
            # Master accounts structured exactly to your system's uppercase Enum specifications
            account_credentials = {
                "director": ("director123", "Company Director", "ADMIN"),
                "erick": ("erick123", "Erick Logistics", "ADMIN"),
                "lyn": ("lyn123", "Lyn Operations", "TRACKING"),
                "precious": ("password123", "Precious Smiles", "BOOKING"),
                "connie": ("connie123", "Connie Finance", "ACCOUNTS")
            }
            
            for username, data in account_credentials.items():
                password, full_name, role_string = data
                
                new_profile = User(
                    username=username,
                    full_name=full_name,       
                    hashed_password=get_password_hash(password), 
                    role=role_string, 
                    is_active=True
                )
                db.add(new_profile)
                
            db.commit()
            print("--- Master Accounts Loaded Successfully into Production Database ---")
    except Exception as e:
        db.rollback()
        print(f"[Database Auto-Populate Warning] Auto-seeding skipped or failed: {e}")


@router.post("/api/auth/login")
@router.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 🚨 CRITICAL INTERCEPT: Force populate the database before running the authentication check
    ensure_database_is_populated(db)

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
    
    # Returns a flat dictionary structure matching your frontend JS expectations perfectly
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "full_name": user.full_name
    }


@router.get("/api/auth/me")
@router.get("/auth/me")
def me(current_user=Depends(auth.get_current_user)):
    return current_user
