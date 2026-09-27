from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.schemas.donation import DonationResponse, DonationListResponse
from app.services.user_lookup import emails_by_wallet
from app.utils.display import display_name_and_initials

router = APIRouter(tags=["donations"])


# ─── Response enrichment (donor display name/initials) ───────────────────────
# See app/routes/campaigns.py for the same pattern applied to campaigns.

def _to_donation_response(donation: Donation, email: str | None) -> DonationResponse:
    name, initials = display_name_and_initials(email, donation.donor_address)
    return DonationResponse(
        id=donation.id,
        tx_hash=donation.tx_hash,
        log_index=donation.log_index,
        campaign_id=donation.campaign_id,
        on_chain_campaign_id=donation.on_chain_campaign_id,
        donor_address=donation.donor_address,
        recipient_address=donation.recipient_address,
        token_address=donation.token_address,
        amount_wei=donation.amount_wei,
        message=donation.message,
        block_timestamp=donation.block_timestamp,
        block_number=donation.block_number,
        created_at=donation.created_at,
        donor_name=name,
        donor_initials=initials,
    )


async def _build_donation_responses(db: AsyncSession, donations: list[Donation]) -> list[DonationResponse]:
    emails = await emails_by_wallet(db, {d.donor_address for d in donations})
    return [_to_donation_response(d, emails.get(d.donor_address.lower())) for d in donations]


async def _build_donation_response(db: AsyncSession, donation: Donation) -> DonationResponse:
    return (await _build_donation_responses(db, [donation]))[0]


# ── /donations ────────────────────────────────────────────────────────────────

@router.get("/donations", response_model=DonationListResponse)
async def list_donations(
    donor_address: str | None = None,
    recipient_address: str | None = None,
    token_address: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Donation)
    if donor_address:
        query = query.where(Donation.donor_address == donor_address.lower())
    if recipient_address:
        query = query.where(Donation.recipient_address == recipient_address.lower())
    if token_address:
        query = query.where(Donation.token_address == token_address.lower())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(Donation.block_timestamp.desc()).limit(limit).offset(offset)
    donations = (await db.execute(query)).scalars().all()
    return DonationListResponse(items=await _build_donation_responses(db, list(donations)), total=total)


@router.get("/donations/{tx_hash}", response_model=DonationResponse)
async def get_donation_by_tx(tx_hash: str, db: AsyncSession = Depends(get_db)):
    # Stored without a "0x" prefix (see web3_listener.py); callers (e.g. viem
    # receipts) always send one, so strip it before comparing.
    normalized = tx_hash.lower().removeprefix("0x")
    result = await db.execute(
        select(Donation).where(Donation.tx_hash == normalized)
    )
    donation = result.scalar_one_or_none()
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")
    return await _build_donation_response(db, donation)


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
    return DonationListResponse(items=await _build_donation_responses(db, list(donations)), total=total)
