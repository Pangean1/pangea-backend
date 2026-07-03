import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.auth_deps import get_wallet as _get_wallet
from app.database import get_db
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignResponse, CampaignListResponse
from config import settings

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = logging.getLogger(__name__)

_ABI_PATH = Path(__file__).parent.parent / "abi" / "PangeaDonation.json"


# ─── List / get endpoints ─────────────────────────────────────────────────────

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


@router.get("/on-chain/{on_chain_id}", response_model=CampaignResponse)
async def get_campaign_by_chain_id(on_chain_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Campaign).where(Campaign.on_chain_id == on_chain_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


# ─── Create campaign ──────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    description: str
    goal_usd: str


def _create_campaign_on_chain(recipient: str, name: str, description: str) -> int:
    """Signs and sends createCampaign() on-chain. Returns the new on_chain_id."""
    if not settings.deployer_private_key:
        raise RuntimeError("DEPLOYER_PRIVATE_KEY not configured")

    with open(_ABI_PATH) as f:
        abi = json.load(f)

    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    account = w3.eth.account.from_key(settings.deployer_private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.contract_address), abi=abi
    )

    tx = contract.functions.createCampaign(
        Web3.to_checksum_address(recipient), name, description
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 400_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": 80002,  # Polygon Amoy
    })

    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)

    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

    events = contract.events.CampaignCreated().process_receipt(receipt)
    return int(events[0]["args"]["campaignId"])


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    auth: tuple[uuid.UUID, str] = Depends(_get_wallet),
    db: AsyncSession = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Description is required")
    try:
        goal_usd = float(payload.goal_usd)
        if goal_usd <= 0:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Goal must be a positive number")

    _, wallet_address = auth
    goal_wei = str(int(goal_usd * 1_000_000))

    try:
        on_chain_id = await asyncio.to_thread(
            _create_campaign_on_chain,
            wallet_address,
            payload.name.strip(),
            payload.description.strip(),
        )
    except RuntimeError as e:
        logger.error("On-chain campaign creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Blockchain transaction failed. Please try again.")
    except Exception as e:
        logger.error("Unexpected error creating campaign: %s", e)
        raise HTTPException(status_code=502, detail="Could not create campaign on-chain.")

    campaign = Campaign(
        on_chain_id=on_chain_id,
        recipient_address=wallet_address.lower(),
        name=payload.name.strip(),
        description=payload.description.strip(),
        active=True,
        total_raised_wei="0",
        goal_wei=goal_wei,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    logger.info("Campaign %d created on-chain and saved to DB.", on_chain_id)
    return campaign


# ─── Sync endpoint ────────────────────────────────────────────────────────────

@router.post("/sync", response_model=list[CampaignResponse], summary="Sync campaigns from chain")
async def sync_campaigns(db: AsyncSession = Depends(get_db)):
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
