"""
PANGEA FastAPI backend entrypoint.

Start with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine, Base
from app.routes import users, campaigns, donations, auth, impact_updates, faucet
from app.services.web3_listener import run_listener
from config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("Creating database tables (if not exist)…")
    async with engine.begin() as conn:
        # Allow wallet_address to be null (email OTP users don't have one at login time)
        await conn.execute(
            text("ALTER TABLE users ALTER COLUMN wallet_address DROP NOT NULL")
        )
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Starting Web3 event listener…")
    listener_task = asyncio.create_task(run_listener(), name="web3_listener")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Stopping Web3 listener…")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(campaigns.router)
app.include_router(donations.router)
app.include_router(impact_updates.router)
app.include_router(faucet.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "version": settings.app_version}
