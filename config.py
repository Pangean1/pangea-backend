from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "PANGEA API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://pangea:pangea@localhost:5432/pangea"

    # Blockchain
    polygon_rpc_url: str = "https://rpc-amoy.polygon.technology"
    contract_address: str = ""
    listener_start_block: int = 0
    listener_poll_interval: int = 5

    # Auth / JWT
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_days: int = 30

    # Redis (OTP storage)
    redis_url: str = "redis://localhost:6379"
    otp_ttl_seconds: int = 600  # 10 minutes

    # Deployer wallet (signs on-chain campaign creation)
    deployer_private_key: str = ""

    # Email (Gmail SMTP)
    gmail_user: str = ""
    gmail_app_password: str = ""

    # Firebase
    firebase_credentials_path: str = "firebase_credentials.json"

    # Pinata (IPFS pinning for impact update media)
    pinata_jwt: str = ""


settings = Settings()
