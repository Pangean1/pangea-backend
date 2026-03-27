import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.database import get_db
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignResponse, CampaignListResponse
from config import settings

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = logging.getLogger(__name__)

_ABI_PATH = Path(__file__).parent.parent / "abi" / "PangeaDonation.json"


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    active_only: bool = True,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign)
    if active_only:
        query = query.where(Campaign.active == True)  # noqa: E712
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(Campaign.on_chain_id.asc()).limit(limit).offset(offset)
    campaigns = (await db.execute(query)).scalars().all()
    return CampaignListResponse(items=list(campaigns), total=total)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/on-chain/{on_chain_id}", response_model=CampaignResponse)
async def get_campaign_by_chain_id(on_chain_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign).where(Campaign.on_chain_id == on_chain_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/sync", response_model=list[CampaignResponse], summary="Sync campaigns from chain")
async def sync_campaigns(db: AsyncSession = Depends(get_db)):
    """
    Pull all campaigns from the smart contract and upsert them into the database.
    Typically called by an admin or a cron job after contract state changes.
    """
    if not settings.contract_address:
        raise HTTPException(status_code=503, detail="Contract address not configured")

    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    with open(_ABI_PATH) as f:
        abi = json.load(f)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.contract_address), abi=abi
    )

    try:
        campaign_count: int = contract.functions.campaignCount().call()
    except Exception as exc:
        logger.error("Failed to read campaignCount: %s", exc)
        raise HTTPException(status_code=502, detail="Chain call failed")

    upserted: list[Campaign] = []
    for chain_id in range(1, campaign_count + 1):
        try:
            data = contract.functions.campaigns(chain_id).call()
            # Returns (id, recipient, name, description, active, totalRaised)
            _, recipient, name, description, active, total_raised = data

            result = await db.execute(
                select(Campaign).where(Campaign.on_chain_id == chain_id)
            )
            campaign = result.scalar_one_or_none()

            if campaign:
                campaign.recipient_address = recipient.lower()
                campaign.name = name
                campaign.description = description
                campaign.active = active
                campaign.total_raised_wei = str(total_raised)
            else:
                campaign = Campaign(
                    on_chain_id=chain_id,
                    recipient_address=recipient.lower(),
                    name=name,
                    description=description,
                    active=active,
                    total_raised_wei=str(total_raised),
                )
                db.add(campaign)

            upserted.append(campaign)
        except Exception as exc:
            logger.error("Failed to sync campaign %d: %s", chain_id, exc)

    await db.commit()
    for c in upserted:
        await db.refresh(c)

    logger.info("Synced %d campaigns from chain.", len(upserted))
    return upserted
