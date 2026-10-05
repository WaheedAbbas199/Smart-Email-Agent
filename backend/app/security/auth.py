"""Authentication boundary.

MVP: single local user. Every route depends on get_current_user, so replacing this with real
session/JWT auth later requires changing only this function.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User

LOCAL_USER_EMAIL = "demo.user@example.com"


def get_or_create_local_user(db: Session) -> User:
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, email=LOCAL_USER_EMAIL, name="Demo User")
        db.add(user)
        db.commit()
    return user


def get_current_user(db: Session = Depends(get_db)) -> User:
    return get_or_create_local_user(db)
