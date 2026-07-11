import asyncio
import logging
import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from web3 import Web3

from app.auth_deps import get_wallet as _get_wallet
from config import settings

# Caps total successful faucet payouts per day so a wave of new signups
# (e.g. from a public website) can't drain the deployer's testnet USDC pool
# faster than it can be manually topped up.
_DAILY_FAUCET_CAP = 20


def _daily_faucet_key() -> str:
    return f"faucet:count:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

router = APIRouter(prefix="/dev", tags=["dev"])
logger = logging.getLogger(__name__)

# The Amoy "USDC" in use (see backend/.env USDC_ADDRESS) is a shared testnet
# token, not one PANGEA controls — mint() is owner-gated to a key we don't
# hold. Funding new wallets works by transferring out of the deployer
# wallet's own USDC balance instead (same approach as
# contracts/scripts/fundDemoWallet.js).
_USDC_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

# Top up any wallet under this balance to this target (both in whole USDC).
# Kept small — the deployer wallet's own USDC balance is the funding source
# and isn't unlimited.
_FUND_THRESHOLD_USDC = 2
_FUND_TARGET_USDC = 5


class FundWalletResponse(BaseModel):
    funded: bool
    usdc_balance: str


def _transfer_usdc(to_address: str, amount_wei: int) -> None:
    if not settings.deployer_private_key:
        raise RuntimeError("DEPLOYER_PRIVATE_KEY not configured")

    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    account = w3.eth.account.from_key(settings.deployer_private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.usdc_address), abi=_USDC_ABI
    )

    deployer_balance = contract.functions.balanceOf(account.address).call()
    if deployer_balance < amount_wei:
        raise RuntimeError(
            f"Faucet pool is out of USDC (deployer has {deployer_balance / 1_000_000} USDC, "
            f"needs {amount_wei / 1_000_000}). Top up {account.address} from the Amoy USDC faucet."
        )

    tx = contract.functions.transfer(
        Web3.to_checksum_address(to_address), amount_wei
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": 80002,  # Polygon Amoy
    })

    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)

    if receipt.status != 1:
        raise RuntimeError(f"Transfer transaction reverted: {tx_hash.hex()}")


@router.post("/fund-wallet", response_model=FundWalletResponse)
async def fund_wallet(auth: tuple[uuid.UUID, str] = Depends(_get_wallet)):
    """Testnet-only faucet: tops up the caller's own wallet with test USDC,
    transferred from the deployer wallet's own balance, so new donor
    accounts can donate without being funded by hand. Never enable in
    production."""
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.usdc_address:
        raise HTTPException(status_code=503, detail="USDC address not configured")

    _, wallet_address = auth
    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.usdc_address), abi=_USDC_ABI
    )
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(wallet_address)
    ).call()

    threshold_wei = _FUND_THRESHOLD_USDC * 1_000_000
    if balance >= threshold_wei:
        return FundWalletResponse(funded=False, usdc_balance=str(balance))

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        count = await redis.incr(_daily_faucet_key())
        if count == 1:
            await redis.expire(_daily_faucet_key(), 86400)
    finally:
        await redis.aclose()

    if count > _DAILY_FAUCET_CAP:
        raise HTTPException(
            status_code=429,
            detail="Faucet's daily test-fund limit has been reached. Please try again tomorrow.",
        )

    top_up_wei = _FUND_TARGET_USDC * 1_000_000 - balance
    try:
        await asyncio.to_thread(_transfer_usdc, wallet_address, top_up_wei)
    except RuntimeError as e:
        logger.error("Faucet transfer failed for %s: %s", wallet_address, e)
        raise HTTPException(status_code=502, detail=str(e))

    new_balance = balance + top_up_wei
    logger.info("Faucet funded %s with %d USDC (wei: %d).", wallet_address, _FUND_TARGET_USDC, top_up_wei)
    return FundWalletResponse(funded=True, usdc_balance=str(new_balance))
