"""Authentication and authorization helpers for TIMS."""

import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db


def ensure_database_ready(db: Session) -> None:
    """Create database tables before auth dependencies read from them."""
    from backend.database import Base, engine

    Base.metadata.create_all(bind=engine)

SECRET_KEY = os.getenv("TIMS_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret-change-me-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOHours = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOHours))
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> models.User | None:
    """Queries the database to validate the username and hashed password safely."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise _credentials_exception() from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    ensure_database_ready(db)

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _credentials_exception("Not authenticated")

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("id")
    username = payload.get("username")

    query = db.query(models.User)
    if user_id is not None:
        user = query.filter(models.User.id == user_id).first()
    elif username:
        user = query.filter(models.User.username == username).first()
    else:
        raise _credentials_exception("Invalid token payload")

    if user is None or not user.is_active:
        raise _credentials_exception("User not found")

    token_role = payload.get("role")
    if token_role and user.role.value != token_role:
        raise _credentials_exception("Role mismatch")

    return user


def require_roles(*roles: models.UserRole):
    allowed = set(roles)

    def _checker(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to perform this action.",
            )
        return current_user

    return _checker
