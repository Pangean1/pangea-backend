import uuid

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

_bearer = HTTPBearer()


def get_wallet(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> tuple[uuid.UUID, str]:
    """Returns (user_id, wallet_address) from a valid JWT."""
    try:
        claims = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
        )
        wallet = claims.get("wallet")
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No wallet address on your account. Please log out and log in again.",
            )
        return uuid.UUID(claims["sub"]), wallet
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
