"""Auth Routes - user registration, login, and session identity.

Backed by the real `users` table (database/models.py: User) via SQLAlchemy,
with bcrypt password hashing and JWT bearer tokens (api/auth_utils.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import create_access_token, get_current_user, hash_password, verify_password
from api.routes.audit import log_audit_event
from database.db import get_db
from database.models import User

router = APIRouter()


class RegisterRequest(BaseModel):
    """New account request."""
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Issued auth token."""
    access_token: str
    token_type: str = "bearer"
    expires_at: str


class UserResponse(BaseModel):
    """Authenticated user profile."""
    id: str
    email: str
    name: str
    role: str = "user"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    """Register a new user."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    await db.flush()
    await log_audit_event(db, action="user.register", user_id=user.id, resource_type="user", resource_id=user.id)
    await db.commit()
    await db.refresh(user)

    return UserResponse(id=user.id, email=user.email, name=user.name, role=user.role)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Authenticate and issue a JWT bearer token."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token, expires_at = create_access_token(user.id)
    await log_audit_event(db, action="user.login", user_id=user.id, resource_type="user", resource_id=user.id)
    await db.commit()
    return TokenResponse(access_token=token, expires_at=expires_at.isoformat())


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Get the current authenticated user (requires a valid bearer token)."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
    )
