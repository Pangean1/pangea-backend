# PANGEA Backend

> 📄 For the full project vision and technical specification, see the [PANGEA White Paper](docs/WHITEPAPER.md)

> Non-profit peer-to-peer humanitarian donation platform on **Polygon PoS** (Amoy testnet).

PANGEA lets donors send ERC-20 tokens directly to verified humanitarian campaigns. This repository is the Python/FastAPI backend that indexes on-chain `DonationSent` events, stores them in PostgreSQL, and delivers Firebase push notifications to campaign recipients in real time.

- Smart contracts: [pangea-contracts](https://github.com/pangea-project/pangea-contracts) _(see also §Smart Contract)_
- Network: Polygon Amoy (testnet) → Polygon PoS mainnet

---

## Table of Contents

1. [Architecture](#architecture)
2. [Event Listener Flow](#event-listener-flow)
3. [Getting Started](#getting-started)
4. [PostgreSQL Setup](#postgresql-setup)
5. [Environment Variables](#environment-variables)
6. [Running the Server](#running-the-server)
7. [API Endpoints](#api-endpoints)
8. [Systemd Service](#systemd-service)
9. [Database Schema](#database-schema)
10. [Package Versions](#package-versions)
11. [License](#license)

---

## Architecture

```
/home/pangea/backend/
├── main.py                        # FastAPI app + lifespan (startup / shutdown)
├── config.py                      # Pydantic-settings – all env vars in one place
├── requirements.txt               # Python dependencies
├── .env                           # Local env overrides  (not committed)
├── .env.example                   # Template – copy to .env and fill in values
├── firebase-credentials.json      # Firebase service-account key  (not committed)
│
└── app/
    ├── database.py                # Async SQLAlchemy engine + session factory
    ├── abi/
    │   └── PangeaDonation.json    # Compiled ABI for the smart contract
    ├── models/
    │   ├── user.py                # User  – wallet address + FCM token
    │   ├── campaign.py            # Campaign – mirrors on-chain campaign struct
    │   ├── donation.py            # Donation – one row per DonationSent event
    │   └── notification.py        # Notification – FCM delivery record
    ├── schemas/
    │   ├── user.py
    │   ├── campaign.py
    │   ├── donation.py
    │   └── notification.py
    ├── routes/
    │   ├── users.py               # POST/GET/PUT /users  + notification sub-routes
    │   ├── campaigns.py           # GET /campaigns  + POST /campaigns/sync
    │   └── donations.py           # GET /donations  + GET /campaigns/{id}/donations
    └── services/
        ├── web3_listener.py       # Background asyncio task – polls for chain events
        └── firebase_service.py    # Firebase Admin SDK wrapper
```

**Request path (REST)**

```
Client → FastAPI router → SQLAlchemy (asyncpg) → PostgreSQL
```

**Event path (background)**

```
Polygon Amoy RPC
      │  HTTP polling (get_logs)
      ▼
web3_listener  ──► PostgreSQL  (donations, campaigns, notifications)
                └► Firebase FCM  (push notification to recipient)
```

---

## Event Listener Flow

The `run_listener()` coroutine starts as a background `asyncio` task during FastAPI's lifespan startup and runs until the server shuts down.

```
┌─────────────────────────────────────────────────────────┐
│  run_listener()  – polls every LISTENER_POLL_INTERVAL s  │
│                                                           │
│  1. Get latest block from Polygon RPC                    │
│  2. call contract.events.DonationSent.get_logs(          │
│         from_block = last_seen + 1,                      │
│         to_block   = latest                              │
│     )                                                    │
│  3. For each event → _handle_donation_event()            │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│  _handle_donation_event(event)                            │
│                                                           │
│  a. Dedup check  (tx_hash + log_index already in DB?)    │
│  b. Resolve local Campaign row by on_chain_id            │
│  c. INSERT Donation row                                   │
│  d. UPDATE campaigns.total_raised_wei  (+= amount)       │
│  e. Lookup recipient User by wallet_address              │
│  f. INSERT Notification row                               │
│  g. If user has fcm_token → send_push_notification()     │
│  h. COMMIT                                                │
└─────────────────────────────────────────────────────────┘
```

> **Polling vs WebSocket** — the listener uses HTTP `get_logs` so it works with any RPC provider (Alchemy, Infura, public endpoints). To reduce latency, replace `Web3.HTTPProvider` with `Web3.WebsocketProvider` and subscribe to event filters.

---

## Getting Started

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| pip / venv | latest |
| A Polygon Amoy RPC URL | e.g. `https://rpc-amoy.polygon.technology` |
| Firebase service-account JSON | from Firebase console |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/pangea-project/pangea-backend.git
cd pangea-backend

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the env template and fill in your values
cp .env.example .env
nano .env                           # set DATABASE_URL, CONTRACT_ADDRESS, etc.

# 5. Place your Firebase service-account key
cp /path/to/downloaded-key.json firebase-credentials.json
```

---

## PostgreSQL Setup

```sql
-- Run as the postgres superuser
CREATE USER pangea WITH PASSWORD 'pangea';
CREATE DATABASE pangea OWNER pangea;
GRANT ALL PRIVILEGES ON DATABASE pangea TO pangea;
```

```bash
# Verify the connection string works
psql postgresql://pangea:pangea@localhost:5432/pangea -c '\l'
```

Tables are created automatically on first startup via SQLAlchemy's `Base.metadata.create_all`.
If you prefer explicit migrations, initialize Alembic:

```bash
alembic init alembic
# edit alembic/env.py to import Base from app.database
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

---

## Environment Variables

Copy `.env.example` to `.env` and set the values below.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `PANGEA API` | Title shown in OpenAPI docs |
| `APP_VERSION` | `0.1.0` | Semantic version |
| `DEBUG` | `false` | Enable SQLAlchemy echo + DEBUG log level |
| `DATABASE_URL` | `postgresql+asyncpg://pangea:pangea@localhost:5432/pangea` | Async PostgreSQL DSN |
| `POLYGON_RPC_URL` | `https://rpc-amoy.polygon.technology` | Polygon Amoy (or mainnet) HTTP/WS RPC |
| `CONTRACT_ADDRESS` | _(empty)_ | Deployed `PangeaDonation` contract address |
| `LISTENER_START_BLOCK` | `0` | Block to begin scanning from (set to deployment block) |
| `LISTENER_POLL_INTERVAL` | `5` | Seconds between RPC polling cycles |
| `FIREBASE_CREDENTIALS_PATH` | `firebase_credentials.json` | Path to Firebase service-account JSON |

---

## Running the Server

```bash
# Development (auto-reload on file changes)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

> Use `--workers 1` in production — the Web3 listener is an asyncio background task tied to a single process. Multiple workers would each start their own listener and duplicate database writes.

Interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## API Endpoints

### Meta

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check — returns `{"status":"ok","version":"..."}` |

### Users

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/users` | Register or upsert a user by `wallet_address` |
| `GET` | `/users/{wallet_address}` | Fetch a user profile |
| `PUT` | `/users/{wallet_address}` | Update `fcm_token`, `username`, or `email` |
| `GET` | `/users/{wallet_address}/notifications` | List notifications (`?unread_only`, `?limit`, `?offset`) |
| `PATCH` | `/users/{wallet_address}/notifications/{notification_id}/read` | Mark a notification as read |

**POST /users body**

```json
{
  "wallet_address": "0xAbC...123",
  "fcm_token": "firebase-token",
  "username": "alice",
  "email": "alice@example.com"
}
```

### Campaigns

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/campaigns` | List campaigns (`?active_only=true`, `?limit`, `?offset`) |
| `GET` | `/campaigns/{campaign_id}` | Fetch campaign by internal UUID |
| `GET` | `/campaigns/on-chain/{on_chain_id}` | Fetch campaign by smart-contract ID |
| `POST` | `/campaigns/sync` | Pull all campaigns from chain and upsert into DB |

### Donations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/donations` | List donations (`?donor_address`, `?token_address`, `?limit`, `?offset`) |
| `GET` | `/donations/{tx_hash}` | Fetch a single donation by transaction hash |
| `GET` | `/campaigns/{campaign_id}/donations` | List donations for a specific campaign |

---

## Systemd Service

Create `/etc/systemd/system/pangea-backend.service`:

```ini
[Unit]
Description=PANGEA FastAPI Backend
After=network.target postgresql.service

[Service]
Type=simple
User=pangea
WorkingDirectory=/home/pangea/backend
EnvironmentFile=/home/pangea/backend/.env
ExecStart=/home/pangea/backend/.venv/bin/uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable pangea-backend
sudo systemctl start pangea-backend

# Check status and logs
sudo systemctl status pangea-backend
sudo journalctl -u pangea-backend -f
```

---

## Database Schema

### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `wallet_address` | VARCHAR(42) | Checksummed Ethereum address, unique |
| `fcm_token` | VARCHAR(512) | Firebase Cloud Messaging token, nullable |
| `username` | VARCHAR(64) | Optional display name |
| `email` | VARCHAR(256) | Optional email |
| `created_at` | TIMESTAMPTZ | Server default |
| `updated_at` | TIMESTAMPTZ | Server default, updated on write |

### `campaigns`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `on_chain_id` | BIGINT | Smart contract campaign ID, unique |
| `recipient_address` | VARCHAR(42) | Recipient wallet |
| `name` | VARCHAR(256) | Campaign name |
| `description` | TEXT | Campaign description |
| `active` | BOOLEAN | Mirrors contract state |
| `total_raised_wei` | VARCHAR(78) | Running total in wei (string to hold uint256) |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### `donations`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `tx_hash` | VARCHAR(66) | Transaction hash, unique |
| `log_index` | INTEGER | Log index within tx (dedup with tx_hash) |
| `campaign_id` | UUID (FK) | → `campaigns.id`, SET NULL on delete |
| `on_chain_campaign_id` | BIGINT | Raw on-chain ID (preserved if FK is null) |
| `donor_address` | VARCHAR(42) | Sender wallet |
| `recipient_address` | VARCHAR(42) | Receiver wallet |
| `token_address` | VARCHAR(42) | ERC-20 token contract |
| `amount_wei` | VARCHAR(78) | Donation amount in wei |
| `message` | TEXT | Donor message |
| `block_timestamp` | TIMESTAMPTZ | Timestamp from the chain event |
| `block_number` | BIGINT | |
| `created_at` | TIMESTAMPTZ | |

### `notifications`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID (FK) | → `users.id`, CASCADE delete |
| `donation_id` | UUID (FK) | → `donations.id`, SET NULL on delete, nullable |
| `campaign_id` | UUID (FK) | → `campaigns.id`, SET NULL on delete, nullable |
| `type` | ENUM | `donation_received`, `campaign_created`, `campaign_status_changed`, `general` |
| `title` | VARCHAR(256) | Notification title |
| `body` | TEXT | Notification body |
| `is_read` | BOOLEAN | Client has read this notification |
| `is_sent` | BOOLEAN | FCM delivery succeeded |
| `created_at` | TIMESTAMPTZ | |

---

## Package Versions

| Package | Pinned version | Purpose |
|---------|---------------|---------|
| `fastapi` | ≥ 0.115.0 | Async web framework |
| `uvicorn[standard]` | ≥ 0.30.0 | ASGI server |
| `pydantic` | ≥ 2.7.0 | Data validation (v2) |
| `pydantic-settings` | ≥ 2.3.0 | Env-var settings management |
| `sqlalchemy` | ≥ 2.0.0 | ORM + async session |
| `alembic` | ≥ 1.13.0 | Database migrations |
| `asyncpg` | ≥ 0.29.0 | Async PostgreSQL driver |
| `psycopg2-binary` | ≥ 2.9.9 | Sync driver (Alembic) |
| `web3` | ≥ 7.0.0 | Ethereum / Polygon client |
| `firebase-admin` | ≥ 6.5.0 | Firebase Cloud Messaging |
| `python-dotenv` | ≥ 1.0.0 | `.env` file loading |
| `httpx` | ≥ 0.27.0 | Async HTTP client |

---

## Smart Contract

The on-chain logic lives in the [pangea-contracts](https://github.com/pangea-project/pangea-contracts) repository. The compiled ABI is vendored at `app/abi/PangeaDonation.json`.

Key events and functions used by this backend:

| Name | Type | Description |
|------|------|-------------|
| `DonationSent` | event | Emitted for every donation — triggers the listener flow |
| `CampaignCreated` | event | Emitted when a new campaign is registered on chain |
| `campaignCount()` | view | Returns total number of campaigns (used by `/campaigns/sync`) |
| `campaigns(uint256)` | view | Returns campaign struct by ID |

---

## License

This project is released under the **MIT License**.

```
MIT License

Copyright (c) 2026 PANGEA Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
