import logging
from typing import List, Optional
from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware

# --- Imports ---
from src.core.interfaces.datasource import IDataSource
from src.infrastructure.gateways.hl_public_api import HLPublicGateway
from src.core.entities.trade import TradeResponse
from src.core.services import (
    PositionService, 
    LeaderboardService, 
    PositionResponse, 
    PnLResponse, 
    LeaderboardEntry
)

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradeTrace")

app = FastAPI(title="TradeTrace API", version="1.0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency Injection ---

def get_datasource() -> IDataSource:
    return HLPublicGateway(use_testnet=False)

def get_position_service(db: IDataSource = Depends(get_datasource)) -> PositionService:
    return PositionService(db)

def get_leaderboard_service(db: IDataSource = Depends(get_datasource)) -> LeaderboardService:
    return LeaderboardService(db)

# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "mode": "Hyperliquid Public API"}

@app.get("/v1/trades", response_model=List[TradeResponse])
async def get_trades(
    user: str = Query(..., description="User Address"),
    coin: str = Query(..., description="Token Symbol"),
    fromMs: Optional[int] = Query(None),
    toMs: Optional[int] = Query(None),
    gateway: IDataSource = Depends(get_datasource)
):
    trades = await gateway.get_trades(user, coin, fromMs, toMs)
    return trades if trades else []

@app.get("/v1/positions/history", response_model=List[PositionResponse])
async def get_positions_history(
    user: str = Query(...),
    coin: str = Query(...),
    fromMs: Optional[int] = None,
    toMs: Optional[int] = None,
    service: PositionService = Depends(get_position_service)
):
    return await service.get_history(user, coin, fromMs, toMs)

@app.get("/v1/pnl", response_model=PnLResponse)
async def get_pnl(
    user: str = Query(...),
    coin: str = Query(...),
    service: LeaderboardService = Depends(get_leaderboard_service)
):
    return await service.calculate_pnl(user, coin)

@app.get("/v1/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(
    coin: str = Query(...),
    metric: str = Query("pnl", description="'pnl' or 'roi'"),
    builderOnly: bool = Query(False, description="Exclude users with non-builder trades"),
    service: LeaderboardService = Depends(get_leaderboard_service)
):
    """
    Real-time Leaderboard:
    Scans active users, calculates their builder-specific PnL, and ranks them.
    """
    return await service.get_leaderboard(coin, metric, builderOnly)