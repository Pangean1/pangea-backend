import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_deps import get_wallet
from app.database import get_db
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.models.impact_update import ImpactUpdate, MediaType
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.schemas.impact_update import ImpactUpdateResponse, ImpactUpdateListResponse
from app.services.firebase_service import send_push_notification_multicast
from app.services.pinata_service import upload_to_ipfs

router = APIRouter(tags=["impact-updates"])


# ── /impact-updates ─────────────────────────────────────────────────────────

@router.get("/impact-updates", response_model=ImpactUpdateListResponse)
async def list_impact_updates(
    donor_address: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(ImpactUpdate)
    if donor_address:
        campaign_ids = select(Donation.campaign_id).where(
            Donation.donor_address == donor_address.lower(),
            Donation.campaign_id.isnot(None),
        ).distinct()
        query = query.where(ImpactUpdate.campaign_id.in_(campaign_ids))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(ImpactUpdate.created_at.desc()).limit(limit).offset(offset)
    updates = (await db.execute(query)).scalars().all()
    return ImpactUpdateListResponse(items=list(updates), total=total)


# ── /campaigns/{id}/impact-updates ──────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/impact-updates", response_model=ImpactUpdateListResponse)
async def list_campaign_impact_updates(
    campaign_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(ImpactUpdate).where(ImpactUpdate.campaign_id == campaign_id)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(ImpactUpdate.created_at.desc()).limit(limit).offset(offset)
    updates = (await db.execute(query)).scalars().all()
    return ImpactUpdateListResponse(items=list(updates), total=total)


@router.post("/campaigns/{campaign_id}/impact-updates", response_model=ImpactUpdateResponse)
async def create_impact_update(
    campaign_id: uuid.UUID,
    message: str = Form(...),
    media: UploadFile | None = File(None),
    wallet_info: tuple[uuid.UUID, str] = Depends(get_wallet),
    db: AsyncSession = Depends(get_db),
):
    _, wallet = wallet_info

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.recipient_address != wallet.lower():
        raise HTTPException(status_code=403, detail="You can only post updates for your own campaign.")
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    media_url: str | None = None
    media_type: MediaType | None = None
    if media is not None:
        media_url = await upload_to_ipfs(media)
        media_type = MediaType.video if (media.content_type or "").startswith("video") else MediaType.image

    update = ImpactUpdate(
        campaign_id=campaign_id,
        message=message.strip(),
        media_url=media_url,
        media_type=media_type,
    )
    db.add(update)
    await db.flush()

    await _notify_donors(db, campaign, update)

    await db.commit()
    await db.refresh(update)
    return update


async def _notify_donors(db: AsyncSession, campaign: Campaign, update: ImpactUpdate) -> None:
    """Creates a Notification row and sends a push to every distinct past donor of this campaign."""
    donor_result = await db.execute(
        select(Donation.donor_address).where(Donation.campaign_id == campaign.id).distinct()
    )
    donor_addresses = {row[0] for row in donor_result}
    if not donor_addresses:
        return

    # Donation addresses are always stored lowercase, but users.wallet_address
    # isn't consistently normalized elsewhere in the codebase — compare lowered.
    users_result = await db.execute(
        select(User).where(func.lower(User.wallet_address).in_(donor_addresses))
    )
    donor_users = users_result.scalars().all()

    title = "New impact update!"
    body = f'"{campaign.name}" posted an update: {update.message[:120]}'

    fcm_tokens = [u.fcm_token for u in donor_users if u.fcm_token]
    sent_count = 0
    if fcm_tokens:
        sent_count = await send_push_notification_multicast(fcm_tokens, title, body)

    # Best-effort delivery flag — the multicast helper only returns an aggregate
    # success count, not per-token results, so we mark a notification sent if
    # its donor had a token registered and at least one push in the batch succeeded.
    for donor_user in donor_users:
        db.add(Notification(
            user_id=donor_user.id,
            campaign_id=campaign.id,
            type=NotificationType.impact_update,
            title=title,
            body=body,
            is_sent=bool(donor_user.fcm_token) and sent_count > 0,
        ))
