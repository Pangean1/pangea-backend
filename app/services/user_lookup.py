from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def emails_by_wallet(db: AsyncSession, wallet_addresses: set[str]) -> dict[str, str]:
    """Batch-looks-up registered emails for a set of wallet addresses.

    Returns a dict keyed by lowercased wallet address; a wallet with no user
    row or no registered email is simply absent (never an empty string) — use
    `.get(...)` and pass the result straight to
    `app.utils.display.display_name_and_initials`, which already handles the
    no-email fallback.
    """
    lowered = {w.lower() for w in wallet_addresses if w}
    if not lowered:
        return {}
    result = await db.execute(
        select(User.wallet_address, User.email).where(
            func.lower(User.wallet_address).in_(lowered),
            User.email.isnot(None),
        )
    )
    return {addr.lower(): email for addr, email in result.all()}
