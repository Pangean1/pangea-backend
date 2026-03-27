from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "PANGEA API"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    # e.g. postgresql+asyncpg://user:pass@localhost:5432/pangea
    database_url: str = "postgresql+asyncpg://pangea:pangea@localhost:5432/pangea"

    # ── Blockchain ────────────────────────────────────────────────────────────
    # Polygon Amoy RPC (HTTP or WS)
    polygon_rpc_url: str = "https://rpc-amoy.polygon.technology"
    # Deployed PangeaDonation contract address
    contract_address: str = ""
    # Block number to start scanning from (set to deployment block for efficiency)
    listener_start_block: int = 0
    # How often the polling loop sleeps between scans (seconds)
    listener_poll_interval: int = 5

    # ── Firebase ─────────────────────────────────────────────────────────────
    # Path to Firebase service-account credentials JSON
    firebase_credentials_path: str = "firebase_credentials.json"


settings = Settings()
