"""
Web3 event listener for PangeaDonation contract.

Polls the Polygon Amoy RPC for CampaignCreated and DonationSent events,
persists new campaigns and donations to the database, and dispatches
Firebase push notifications to the recipient's registered device(s).

The listener runs as a background asyncio task started during FastAPI lifespan.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from web3 import Web3

from app.database import AsyncSessionLocal
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.services.firebase_service import send_push_notification
from config import settings

logger = logging.getLogger(__name__)

_ABI_PATH = Path(__file__).parent.parent / "abi" / "PangeaDonation.json"


def _load_contract(w3: Web3):
    with open(_ABI_PATH) as f:
        abi = json.load(f)
    address = Web3.to_checksum_address(settings.contract_address)
    return w3.eth.contract(address=address, abi=abi)


async def _handle_campaign_event(event: dict) -> None:
    """Upsert a CampaignCreated event into the campaigns table."""
    args = event["args"]
    on_chain_id: int = args["campaignId"]
    recipient: str = args["recipient"].lower()
    name: str = args["name"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.on_chain_id == on_chain_id)
        )
        campaign: Campaign | None = result.scalar_one_or_none()

        if campaign:
            campaign.recipient_address = recipient
            campaign.name = name
            logger.info("Updated campaign %d (%s) from on-chain event.", on_chain_id, name)
        else:
            campaign = Campaign(
                on_chain_id=on_chain_id,
                recipient_address=recipient,
                name=name,
                description="",
                goal_wei="0",
                total_raised_wei="0",
                active=True,
            )
            session.add(campaign)
            logger.info("Created campaign %d (%s) from on-chain event.", on_chain_id, name)

        await session.commit()


async def _handle_donation_event(event: dict) -> None:
    """Persist a DonationSent event and fire a push notification."""
    args = event["args"]
    tx_hash: str = event["transactionHash"].hex()
    log_index: int = event["logIndex"]
    block_number: int = event["blockNumber"]

    donor: str = args["donor"].lower()
    recipient: str = args["recipient"].lower()
    token: str = args["token"].lower()
    amount_wei: int = args["amount"]
    on_chain_campaign_id: int = args["campaignId"]
    block_ts: int = args["timestamp"]
    message: str = args["message"]

    block_timestamp = datetime.fromtimestamp(block_ts, tz=timezone.utc)

    async with AsyncSessionLocal() as session:
        # ── Dedup check ───────────────────────────────────────────────────
        existing = await session.execute(
            select(Donation).where(Donation.tx_hash == tx_hash, Donation.log_index == log_index)
        )
        if existing.scalar_one_or_none():
            logger.debug("Donation %s[%d] already stored — skipping.", tx_hash, log_index)
            return

        # ── Resolve local campaign row ────────────────────────────────────
        campaign_result = await session.execute(
            select(Campaign).where(Campaign.on_chain_id == on_chain_campaign_id)
        )
        campaign: Campaign | None = campaign_result.scalar_one_or_none()
        campaign_uuid = campaign.id if campaign else None

        # ── Persist donation ──────────────────────────────────────────────
        donation = Donation(
            tx_hash=tx_hash,
            log_index=log_index,
            campaign_id=campaign_uuid,
            on_chain_campaign_id=on_chain_campaign_id,
            donor_address=donor,
            recipient_address=recipient,
            token_address=token,
            amount_wei=str(amount_wei),
            message=message,
            block_timestamp=block_timestamp,
            block_number=block_number,
        )
        session.add(donation)

        # ── Update campaign total_raised_wei ──────────────────────────────
        if campaign:
            new_total = int(campaign.total_raised_wei) + amount_wei
            campaign.total_raised_wei = str(new_total)

        await session.flush()  # get donation.id

        # ── Notify recipient ──────────────────────────────────────────────
        user_result = await session.execute(
            select(User).where(User.wallet_address == recipient)
        )
        recipient_user: User | None = user_result.scalar_one_or_none()

        notification = Notification(
            user_id=recipient_user.id if recipient_user else None,
            donation_id=donation.id,
            campaign_id=campaign_uuid,
            type=NotificationType.donation_received,
            title="New donation received!",
            body=(
                f"You received a donation of {amount_wei} wei"
                + (f" for campaign \"{campaign.name}\"." if campaign else ".")
            ),
        )

        if recipient_user:
            notification.user_id = recipient_user.id
            session.add(notification)
            await session.flush()

            if recipient_user.fcm_token:
                sent = await send_push_notification(
                    fcm_token=recipient_user.fcm_token,
                    title=notification.title,
                    body=notification.body,
                    data={
                        "tx_hash": tx_hash,
                        "campaign_id": str(on_chain_campaign_id),
                        "amount_wei": str(amount_wei),
                    },
                )
                notification.is_sent = sent
        else:
            logger.debug(
                "Recipient %s not registered — notification will be deferred.", recipient
            )

        await session.commit()
        logger.info(
            "Stored donation %s (campaign %d, %d wei from %s).",
            tx_hash,
            on_chain_campaign_id,
            amount_wei,
            donor,
        )


async def _scan_block_range(contract, from_block: int, to_block: int) -> None:
    """Fetch and handle all CampaignCreated and DonationSent events in [from_block, to_block]."""
    try:
        campaign_events = contract.events.CampaignCreated.get_logs(
            from_block=from_block,
            to_block=to_block,
        )
        for event in campaign_events:
            try:
                await _handle_campaign_event(event)
            except Exception as exc:
                logger.error("Error handling CampaignCreated event %s: %s", event, exc)
    except Exception as exc:
        logger.error("Error fetching CampaignCreated logs [%d-%d]: %s", from_block, to_block, exc)

    try:
        donation_events = contract.events.DonationSent.get_logs(
            from_block=from_block,
            to_block=to_block,
        )
        for event in donation_events:
            try:
                await _handle_donation_event(event)
            except Exception as exc:
                logger.error("Error handling DonationSent event %s: %s", event, exc)
    except Exception as exc:
        logger.error("Error fetching DonationSent logs [%d-%d]: %s", from_block, to_block, exc)


async def _backfill_campaigns(contract) -> None:
    """Read all campaigns directly from the contract and upsert into the DB."""
    try:
        count: int = contract.functions.campaignCount().call()
    except Exception as exc:
        logger.error("Could not read campaignCount: %s", exc)
        return

    logger.info("Syncing %d on-chain campaigns…", count)
    synced = 0
    for on_chain_id in range(1, count + 1):
        try:
            data = contract.functions.campaigns(on_chain_id).call()
            # campaigns() returns (id, recipient, name, description, active, totalRaised)
            _, recipient, name, description, active, total_raised = data
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Campaign).where(Campaign.on_chain_id == on_chain_id)
                )
                campaign: Campaign | None = result.scalar_one_or_none()
                if campaign:
                    campaign.recipient_address = recipient.lower()
                    campaign.name = name
                    campaign.description = description
                    campaign.active = active
                    campaign.total_raised_wei = str(total_raised)
                else:
                    campaign = Campaign(
                        on_chain_id=on_chain_id,
                        recipient_address=recipient.lower(),
                        name=name,
                        description=description,
                        active=active,
                        total_raised_wei=str(total_raised),
                        goal_wei="0",
                    )
                    session.add(campaign)
                await session.commit()
            synced += 1
            logger.info("Synced campaign %d: %s", on_chain_id, name)
        except Exception as exc:
            logger.error("Error syncing campaign %d: %s", on_chain_id, exc)

    logger.info("Campaign sync complete — %d/%d campaigns synced.", synced, count)


async def run_listener() -> None:
    """
    Main listener loop. Polls for new CampaignCreated and DonationSent events
    every `settings.listener_poll_interval` seconds.

    On startup, backfills all CampaignCreated events from the deployment block
    so the database stays in sync with the chain.
    """
    if not settings.contract_address:
        logger.warning("CONTRACT_ADDRESS not set — Web3 listener will not start.")
        return

    logger.info(
        "Starting Web3 listener on %s for contract %s",
        settings.polygon_rpc_url,
        settings.contract_address,
    )

    try:
        w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
        contract = _load_contract(w3)

        current_block = w3.eth.block_number
        logger.info("Syncing campaigns from contract…")
        await _backfill_campaigns(contract)
    except Exception as exc:
        logger.error("Listener init error: %s", exc, exc_info=True)
        return

    last_block = current_block
    logger.info("Listener polling from block %d", last_block)

    while True:
        try:
            latest = w3.eth.block_number
            if latest > last_block:
                await _scan_block_range(contract, last_block + 1, latest)
                last_block = latest
        except Exception as exc:
            logger.error("Listener loop error: %s", exc)

        await asyncio.sleep(settings.listener_poll_interval)
