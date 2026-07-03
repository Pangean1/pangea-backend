"""
IPFS media storage via Pinata's pinning API.

Beneficiary-uploaded photos/videos are pinned to IPFS rather than stored on
the backend's local disk — the VM has limited free disk space and no CDN in
front of it, and pinning gives durable, publicly verifiable hosting that
matches PANGEA's transparency principle.
"""

import logging

import httpx
from fastapi import HTTPException, UploadFile, status

from config import settings

logger = logging.getLogger(__name__)

_PINATA_UPLOAD_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
_PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs"


async def upload_to_ipfs(file: UploadFile) -> str:
    """Uploads a file to IPFS via Pinata and returns a public gateway URL."""
    if not settings.pinata_jwt:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media upload is not configured.",
        )

    content = await file.read()
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                _PINATA_UPLOAD_URL,
                headers={"Authorization": f"Bearer {settings.pinata_jwt}"},
                files={"file": (file.filename, content, file.content_type)},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text.lower()
            # Pinata returns 402/403 with a message mentioning plan/storage limits
            # when the account has run out of pinning space — this needs a
            # distinct, actionable message since retrying won't help.
            if exc.response.status_code in (402, 403) and any(
                kw in body_text for kw in ("storage", "limit", "quota", "plan", "exceed")
            ):
                logger.error(
                    "Pinata storage limit reached (%s): %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                    detail=(
                        "Photo/video storage is full. Your update was not posted — "
                        "try again without media, or contact support."
                    ),
                )
            logger.error(
                "Pinata upload failed (%s): %s", exc.response.status_code, exc.response.text
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not upload media. Please try again.",
            )
        except httpx.HTTPError as exc:
            logger.error("Pinata upload failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not upload media. Please try again.",
            )

    cid = response.json()["IpfsHash"]
    return f"{_PINATA_GATEWAY}/{cid}"
