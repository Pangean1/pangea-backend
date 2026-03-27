"""
Firebase Cloud Messaging service.

Initialises the Firebase Admin SDK once at import time (if credentials exist)
and exposes a single async-friendly helper to send push notifications.
"""

import logging
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, messaging

from config import settings

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None


def _init_firebase() -> None:
    global _app
    cred_path = Path(settings.firebase_credentials_path)
    if not cred_path.exists():
        logger.warning(
            "Firebase credentials file not found at '%s'. "
            "Push notifications will be disabled.",
            cred_path,
        )
        return
    try:
        cred = credentials.Certificate(str(cred_path))
        _app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialised successfully.")
    except Exception as exc:
        logger.error("Failed to initialise Firebase Admin SDK: %s", exc)


_init_firebase()


async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """
    Send a Firebase push notification to a single device.

    Returns True if the message was accepted by FCM, False otherwise.
    Runs synchronously inside the event loop — acceptable for low-frequency
    notification delivery; swap for asyncio.to_thread() if volume grows.
    """
    if _app is None:
        logger.debug("Firebase not initialised; skipping notification to %s", fcm_token[:8])
        return False

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=fcm_token,
    )
    try:
        response = messaging.send(message, app=_app)
        logger.info("FCM message sent: %s", response)
        return True
    except messaging.UnregisteredError:
        logger.warning("FCM token is no longer registered: %s…", fcm_token[:12])
        return False
    except Exception as exc:
        logger.error("Failed to send FCM notification: %s", exc)
        return False


async def send_push_notification_multicast(
    fcm_tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """
    Send the same notification to multiple devices.
    Returns the count of successful deliveries.
    """
    if _app is None or not fcm_tokens:
        return 0

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=fcm_tokens,
    )
    try:
        batch_response = messaging.send_each_for_multicast(message, app=_app)
        success_count = batch_response.success_count
        logger.info(
            "Multicast FCM: %d/%d succeeded", success_count, len(fcm_tokens)
        )
        return success_count
    except Exception as exc:
        logger.error("Failed to send multicast FCM notification: %s", exc)
        return 0
