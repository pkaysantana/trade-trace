# 🚀 TradeTrace - Hyperliquid Position Reconstruction API

[![API Version](https://img.shields.io/badge/API-v1.1.0-blue)](http://localhost:8000/docs)
[![Docker](https://img.shields.io/badge/Docker-Ready-green)](docker-compose.yml)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**TradeTrace** is a high-performance API for reconstructing trading positions from Hyperliquid fills data, with builder attribution tracking for fair competition leaderboards.

## ✨ Features

### Core Features
- **Position Reconstruction** - Rebuild position history from trade fills
- **Builder Attribution** - Track "tainted" vs "clean" position lifecycles
- **Leaderboard API** - Rank traders by PnL/ROI with builder filtering
- **Historical Snapshots** - Query position state at any point in time
- **Postgres Persistence** - Durable storage with TimescaleDB

### Bonus Features 🔥
- **Deposit Tracking** (`/v1/deposits`) - Fair competition filtering
- **Portfolio PnL** (`/v1/pnl`) - Multi-coin aggregation
- **Live Risk Metrics** (`/v1/positions/current`) - liqPx, marginUsed%
- **Fair Leaderboard** (`/v1/leaderboard/fair`) - Deposit-adjusted scoring

---

## 🏗️ Architecture

```
src/
├── api/
│   └── main.py              # FastAPI endpoints
├── core/
│   ├── entities/            # Domain models (Trade, Position, Deposit)
│   ├── interfaces/          # Abstract datasource interface
│   └── use_cases/           # Position reconstruction logic
└── infrastructure/
    ├── gateways/            # Hyperliquid API integration
    └── persistence/         # PostgreSQL repository
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- WSL2 (Windows) or Linux/macOS

### 1. Clone & Run

```bash
git clone https://github.com/pkaysantana/trade-trace.git
cd trade-trace

# Start all services
docker-compose up --build -d

# Verify
curl http://localhost:8000/health
```

### 2. Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Get position history
curl "http://localhost:8000/v1/positions/history?user=0x31ca8395cf837de08b24da3f660e77761dfb974b&coin=BTC"

# Get leaderboard
curl "http://localhost:8000/v1/leaderboard?coin=BTC"

# Portfolio PnL (Bonus)
curl "http://localhost:8000/v1/pnl?user=0x31ca8395cf837de08b24da3f660e77761dfb974b"

# Sync to database
curl -X POST "http://localhost:8000/v1/sync?coin=BTC"
```

### 3. View API Docs
Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger UI.

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/v1/trades` | GET | Raw trade fills |
| `/v1/positions/history` | GET | Reconstructed position snapshots |
| `/v1/positions/current` | GET | Live position with risk metrics |
| `/v1/leaderboard` | GET | Ranked traders by PnL/ROI |
| `/v1/leaderboard/fair` | GET | Deposit-adjusted leaderboard |
| `/v1/deposits` | GET | User deposit/withdrawal history |
| `/v1/pnl` | GET | PnL calculation (single/portfolio) |
| `/v1/sync` | POST | Sync & persist to database |

---

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@postgres:5432/tradetrace` | PostgreSQL connection |
| `USE_TESTNET` | `false` | Use Hyperliquid testnet |

### Docker Services

| Service | Port | Image |
|---------|------|-------|
| API | 8000 | `python:3.11-slim` |
| PostgreSQL | 5432 | `timescale/timescaledb:latest-pg16` |
| Redis | 6379 | `redis:7-alpine` |

---

## 🧪 Testing

```bash
# Run unit tests
docker exec -it trade-trace-1_api_1 pytest tests/ -v

# Or locally with venv
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
pytest tests/ -v
```

---

## 🌐 Deployment

### Option 1: Railway (Recommended)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up
```

### Option 2: Render
1. Connect GitHub repo to [render.com](https://render.com)
2. Create Web Service from `Dockerfile`
3. Add PostgreSQL and Redis add-ons

### Option 3: DigitalOcean App Platform
```bash
doctl apps create --spec .do/app.yaml
```

---

## 📊 Database Schema

```sql
-- Position snapshots table
CREATE TABLE positionsnapshots (
    timeMs BIGINT,
    netSize DECIMAL,
    avgEntryPx DECIMAL,
    tainted BOOLEAN,
    "user" VARCHAR,
    coin VARCHAR,
    lifecycleId BIGINT
);
```

---

## 🏆 Hyperliquid Challenge Compliance

| Requirement | Status |
|-------------|--------|
| Position reconstruction | ✅ |
| Builder attribution | ✅ |
| Leaderboard with ROE | ✅ |
| REST API | ✅ |
| Docker deployment | ✅ |
| PostgreSQL persistence | ✅ |
| Deposit tracking (Bonus) | ✅ |
| Portfolio PnL (Bonus) | ✅ |
| Risk metrics (Bonus) | ✅ |
| Fair leaderboard (Bonus) | ✅ |

---

## 📝 Changelog

### v1.1.0 (Current)
- Added `/v1/deposits` endpoint
- Added `/v1/pnl` with portfolio aggregation
- Added `/v1/positions/current` with liqPx, marginUsed%
- Added `/v1/leaderboard/fair` with deposit adjustment
- Extended Position model with risk metrics

### v1.0.0
- Core position reconstruction
- Builder attribution tracking
- Basic leaderboard
- Docker + PostgreSQL setup

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

PRs welcome! Please follow the existing code style and add tests.

---

Built with ❤️ for the Hyperliquid Builder Challenge
