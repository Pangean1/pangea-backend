import logging
import secrets
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

import aiosmtplib
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.database import get_db
from app.models.user import User
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _otp_key(email: str) -> str:
    return f"otp:{email.lower()}"


async def _send_otp_email(to_email: str, otp: str) -> None:
    msg = MIMEText(
        f"Your PANGEA verification code is:\n\n"
        f"    {otp}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this, ignore this email."
    )
    msg["Subject"] = f"{otp} is your PANGEA code"
    msg["From"] = settings.gmail_user
    msg["To"] = to_email

    await aiosmtplib.send(
        msg,
        hostname="smtp.gmail.com",
        port=587,
        start_tls=True,
        username=settings.gmail_user,
        password=settings.gmail_app_password,
    )


# ── Request / Response schemas ────────────────────────────────────────────────

class SendCodeRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str
    wallet_address: str | None = None


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str
    wallet_address: str | None


class MeResponse(BaseModel):
    user_id: str
    email: str
    wallet_address: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/send-code", status_code=200)
async def send_code(payload: SendCodeRequest):
    email = payload.email.lower()
    otp = str(secrets.randbelow(1_000_000)).zfill(6)

    redis = _get_redis()
    try:
        await redis.setex(_otp_key(email), settings.otp_ttl_seconds, otp)
    finally:
        await redis.aclose()

    if settings.gmail_user and settings.gmail_app_password:
        try:
            await _send_otp_email(email, otp)
        except Exception as e:
            logger.error("Failed to send OTP email to %s: %s", email, e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not send verification email. Please try again.",
            )
    else:
        # Email not configured — log the code for development use
        logger.warning("EMAIL NOT CONFIGURED. OTP for %s: %s", email, otp)

    return {"message": "Verification code sent"}


@router.post("/verify-code", response_model=AuthResponse)
async def verify_code(payload: VerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower()

    redis = _get_redis()
    try:
        stored_otp = await redis.get(_otp_key(email))
    finally:
        await redis.aclose()

    if not stored_otp or stored_otp != payload.code.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code.",
        )

    # Delete OTP so it can't be reused
    redis = _get_redis()
    try:
        await redis.delete(_otp_key(email))
    finally:
        await redis.aclose()

    # Get or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    wallet_address = payload.wallet_address.lower() if payload.wallet_address else None
    if user is None:
        user = User(email=email, wallet_address=wallet_address)
        db.add(user)
    elif wallet_address:
        user.wallet_address = wallet_address

    try:
        await db.commit()
    except IntegrityError:
        # wallet_address is unique — this fires if the same wallet key is
        # already linked to a different account (e.g. two accounts signed in
        # on the same device before the per-email wallet key fix).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This wallet is already linked to a different account. Please sign out and sign in again to generate a new wallet.",
        )
    await db.refresh(user)

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "email": email,
            "wallet": user.wallet_address,
            "iat": now,
            "exp": now + timedelta(days=settings.jwt_expiry_days),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    return AuthResponse(
        token=token,
        user_id=str(user.id),
        email=email,
        wallet_address=user.wallet_address,
    )


@router.post("/wallet", status_code=200)
async def register_wallet(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Called by the frontend after generating a wallet key to register the address."""
    token = payload.get("token")
    wallet_address = payload.get("wallet_address")

    if not token or not wallet_address:
        raise HTTPException(status_code=400, detail="token and wallet_address required")

    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == claims["sub"]))
    user = result.scalar_one_or_none()

    if user and user.wallet_address is None:
        user.wallet_address = wallet_address.lower()
        await db.commit()

    return {"message": "Wallet registered"}
