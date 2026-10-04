"""
Email notification service.

Sends notification emails (donation received, impact update) through the same
Gmail SMTP account used for OTP login codes. This is the prototype-stage
replacement for Firebase push delivery, which needs device-token registration
the app doesn't do yet (see CLAUDE.md, "Push notifications").

Gmail caps a personal account at roughly 500 sent emails/day and can revoke the
App Password when that's abused (2026-09-16 incident). Notifications share that
budget with OTP login codes, so they're capped below it here — a cap hit skips
the email (the Notification DB row still exists), it never blocks OTP sending.
"""

import logging
from datetime import datetime, timezone
from email.mime.text import MIMEText

import aiosmtplib
from redis.asyncio import Redis

from config import settings

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_EMAILS_PER_DAY = 200            # all recipients combined
MAX_NOTIFICATION_EMAILS_PER_DAY_PER_RECIPIENT = 10

_FOOTER = (
    "\n\n—\n"
    "PANGEA — Making Every Donation Count\n"
    "You're receiving this because you have a PANGEA account. "
    "To stop these emails, reply with \"unsubscribe\"."
)


async def _within_daily_caps(to_email: str) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        for key, limit in (
            (f"notif_email:count:{today}", MAX_NOTIFICATION_EMAILS_PER_DAY),
            (f"notif_email:count:{today}:{to_email.lower()}", MAX_NOTIFICATION_EMAILS_PER_DAY_PER_RECIPIENT),
        ):
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 86400)
            if count > limit:
                logger.warning("Notification email cap reached (%s) — skipping.", key)
                return False
        return True
    finally:
        await redis.aclose()


async def send_notification_email(to_email: str, subject: str, body: str) -> bool:
    """Sends one notification email. Returns True on success; never raises."""
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.debug("Gmail SMTP not configured; skipping notification email.")
        return False
    try:
        if not await _within_daily_caps(to_email):
            return False

        msg = MIMEText(body + _FOOTER)
        msg["Subject"] = subject
        msg["From"] = f"PANGEA <{settings.gmail_user}>"
        msg["To"] = to_email

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.gmail_user,
            password=settings.gmail_app_password,
        )
        return True
    except Exception as exc:
        logger.error("Failed to send notification email: %s", exc)
        return False


def format_usd(amount_wei: int) -> str:
    """USDC has 6 decimals; shown to users as plain dollars (no crypto feel)."""
    return f"${amount_wei / 1_000_000:,.2f}"
