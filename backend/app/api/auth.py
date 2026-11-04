from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.security import create_token, current_user, hash_password, rate_limit, verify_password
from app.database.session import get_db
from app.models import User
from app.schemas.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[Depends(rate_limit("auth", 10))])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalars(select(User).where(User.email == body.email.lower())).first():
        raise HTTPException(409, "Email already registered.")
    u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.record(db, action="user.registered", actor=f"user:{u.id}", user_id=u.id)
    db.commit()
    return TokenOut(access_token=create_token(u.id), user=UserOut.model_validate(u))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("auth", 10))])
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    return TokenOut(access_token=create_token(u.id), user=UserOut.model_validate(u))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
