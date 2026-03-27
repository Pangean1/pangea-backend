from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.schemas.donation import DonationResponse, DonationListResponse

router = APIRouter(tags=["donations"])


# ── /donations ────────────────────────────────────────────────────────────────

@router.get("/donations", response_model=DonationListResponse)
async def list_donations(
    donor_address: str | None = None,
    token_address: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Donation)
    if donor_address:
        query = query.where(Donation.donor_address == donor_address.lower())
    if token_address:
        query = query.where(Donation.token_address == token_address.lower())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(Donation.block_timestamp.desc()).limit(limit).offset(offset)
    donations = (await db.execute(query)).scalars().all()
    return DonationListResponse(items=list(donations), total=total)


@router.get("/donations/{tx_hash}", response_model=DonationResponse)
async def get_donation_by_tx(tx_hash: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Donation).where(Donation.tx_hash == tx_hash.lower())
    )
    donation = result.scalar_one_or_none()
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    return donation


# ── /campaigns/{id}/donations ─────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/donations", response_model=DonationListResponse)
async def list_campaign_donations(
    campaign_id: UUID,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(Donation).where(Donation.campaign_id == campaign_id)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(Donation.block_timestamp.desc()).limit(limit).offset(offset)
    donations = (await db.execute(query)).scalars().all()
    return DonationListResponse(items=list(donations), total=total)
