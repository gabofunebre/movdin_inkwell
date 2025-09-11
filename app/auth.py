"""Authentication helpers and dependencies."""

from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from config.db import get_db
from models import User


def hash_password(password: str) -> str:
    """Return a SHA256 hex digest for the given password."""

    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Retrieve the currently logged-in user from the session."""

    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user and not user.is_active:
        return None
    return user


def require_admin(user: User | None = Depends(get_current_user)) -> User:
    """Ensure the user is authenticated and has admin role."""

    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
    return user

