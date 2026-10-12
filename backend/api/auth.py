"""JWT authentication: signup, login, current-user dependency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.schemas import LoginRequest, Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
BCRYPT_MAX_BYTES = 72  # bcrypt ignores bytes beyond this length


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode()[:BCRYPT_MAX_BYTES], password_hash.encode())


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user.username, "exp": expires}, settings.SECRET_KEY,
                      algorithm=settings.JWT_ALGORITHM)


async def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                           db: AsyncSession = Depends(get_db)) -> Optional[User]:
    """Return the signed-in user. Anonymous access is allowed unless REQUIRE_AUTH=true."""
    if creds is None:
        if settings.REQUIRE_AUTH:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
        return None
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.") from exc
    user = (await db.execute(select(User).where(User.username == payload.get("sub")))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user.")
    return user


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(body: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    exists = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken.")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    return user


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")
    return Token(access_token=create_token(user))


@router.get("/me", response_model=UserOut)
async def me(user: Optional[User] = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user
