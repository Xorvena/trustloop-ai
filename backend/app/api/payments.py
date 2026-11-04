from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ServiceError
from app.core.security import current_user, rate_limit
from app.database.session import get_db
from app.models import User
from app.payments import service
from app.schemas.schemas import CaptureIn, CreateOrderIn

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/config")
def public_config(user: User = Depends(current_user)):
    """Only PUBLIC values for the PayPal JS SDK. The client secret never leaves the backend."""
    s = get_settings()
    return {"client_id": s.paypal_client_id or None, "currency": s.paypal_currency, "configured": bool(s.paypal_client_id and s.paypal_client_secret),
            "inr_rate": str(s.inr_per_unit_paypal_currency), "environment": "sandbox" if "sandbox" in s.paypal_base_url else "live"}


@router.post("/create-order", dependencies=[Depends(rate_limit("pay", 20))])
def create_order(body: CreateOrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.create_order(db, user.id, body.proposal_id)


@router.post("/capture", dependencies=[Depends(rate_limit("pay", 20))])
def capture(body: CaptureIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.capture(db, user.id, body.paypal_order_id)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        event = await request.json()
    except Exception:
        raise ServiceError(400, "bad_payload", "Invalid JSON.")
    if not isinstance(event, dict):
        raise ServiceError(400, "bad_payload", "Invalid event.")
    return service.handle_webhook(db, dict(request.headers), event)
