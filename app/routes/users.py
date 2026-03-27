from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user or update an existing one (upsert by wallet_address)."""
    result = await db.execute(
        select(User).where(User.wallet_address == payload.wallet_address.lower())
    )
    user = result.scalar_one_or_none()

    if user:
        # Update mutable fields if provided
        if payload.fcm_token is not None:
            user.fcm_token = payload.fcm_token
        if payload.username is not None:
            user.username = payload.username
        if payload.email is not None:
            user.email = payload.email
    else:
        user = User(
            wallet_address=payload.wallet_address.lower(),
            fcm_token=payload.fcm_token,
            username=payload.username,
            email=payload.email,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{wallet_address}", response_model=UserResponse)
async def get_user(wallet_address: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address.lower())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{wallet_address}", response_model=UserResponse)
async def update_user(
    wallet_address: str, payload: UserUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address.lower())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.fcm_token is not None:
        user.fcm_token = payload.fcm_token
    if payload.username is not None:
        user.username = payload.username
    if payload.email is not None:
        user.email = payload.email

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{wallet_address}/notifications", response_model=list[NotificationResponse])
async def get_user_notifications(
    wallet_address: str,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address.lower())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712
    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

    notifications = (await db.execute(query)).scalars().all()
    return notifications


@router.patch("/{wallet_address}/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    wallet_address: str,
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.wallet_address == wallet_address.lower())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    notif_result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notification = notif_result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification
