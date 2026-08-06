from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend import auth, models, schemas
from backend.database import get_db
from backend.models import UserRole

router = APIRouter(tags=["auth"])


def ensure_database_is_populated(db: Session):
    """Create tables and populate the users table if needed."""
    try:
        from backend.database import Base, engine

        Base.metadata.create_all(bind=engine)

        user_count = db.execute(text("SELECT count(*) FROM users")).scalar()
        if user_count == 0:
            print("--- Emergency Database Population Event Triggered ---")
            from backend.auth import get_password_hash
            from backend.models import User, UserRole

            account_credentials = {
                "director": ("director123", "Company Director", "ADMIN"),
                "erick": ("erick123", "Erick Logistics", "ADMIN"),
                "lyn": ("lyn123", "Lyn Operations", "TRACKING"),
                "precious": ("password123", "Precious Smiles", "BOOKING"),
                "edina": ("edina123", "Edina Finance", "ACCOUNTS"),
            }

            for username, data in account_credentials.items():
                password, full_name, role_string = data
                db.add(
                    User(
                        username=username,
                        full_name=full_name,
                        hashed_password=get_password_hash(password),
                        role=UserRole(role_string),
                        is_active=True,
                    )
                )

            db.commit()
            print("--- Master Accounts Loaded Successfully into Production Database ---")
    except Exception as exc:
        db.rollback()
        print(f"[Database Auto-Populate Warning] Auto-seeding skipped or failed: {exc}")


@router.post("/api/auth/login")
@router.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "full_name": user.full_name,
    }


@router.get("/api/auth/me")
@router.get("/auth/me")
def me(current_user=Depends(auth.get_current_user)):
    return current_user


@router.post("/users", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_roles(UserRole.ADMIN)),
):
    ensure_database_is_populated(db)
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = models.User(
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=auth.get_password_hash(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_roles(UserRole.ADMIN)),
):
    ensure_database_is_populated(db)
    return db.query(models.User).order_by(models.User.username).all()


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_roles(UserRole.ADMIN)),
):
    ensure_database_is_populated(db)
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return user
