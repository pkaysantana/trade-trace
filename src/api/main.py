#!/usr/bin/env python3
"""
TradeTrace API - Hyperliquid Trade Ledger (Phase 1 Complete)
Minimal working version - All 5 endpoints + mocks inline
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict
from pydantic import BaseModel
from datetime import datetime
import asyncio

app = FastAPI(title="TradeTrace API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class TradeResponse(BaseModel):
    timeMs: int
    coin: str
    side: str
    px: float
    sz: float
    fee: float
    closedPnl: float
    builder: Optional[str] = None

class PositionResponse(BaseModel):
    timeMs: int
    netSize: float
    avgEntryPx: float
    tainted: bool = False

class PnLResponse(BaseModel):
    realizedPnl: float
    returnPct: float
    feesPaid: float
    tradeCount: int
    tainted: bool = False

class LeaderboardEntry(BaseModel):
    rank: int
    user: str
    metricValue: float
    tradeCount: int
    tainted: bool = False

class LeaderboardResponse(BaseModel):
    entries: List[LeaderboardEntry]

# Mock data
MOCK_TRADES = [
    TradeResponse(timeMs=1737091200000, coin="BTC", side="Long", px=95000.0, sz=0.1, fee=0.5, closedPnl=150.0),
    TradeResponse(timeMs=1737094800000, coin="BTC", side="Short", px=96000.0, sz=0.05, fee=0.3, closedPnl=-75.0),
]

MOCK_POSITIONS = [
    PositionResponse(timeMs=1737091200000, netSize=0.1, avgEntryPx=95000.0),
    PositionResponse(timeMs=1737094800000, netSize=0.05, avgEntryPx=95000.0),
]

# Endpoints
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/v1/trades", response_model=List[TradeResponse])
async def get_trades(
    user: str = Query(...),
    coin: str = Query(...),
    fromMs: Optional[int] = None,
    toMs: Optional[int] = None,
    builderOnly: bool = Query(False)
):
    # Mock filter logic
    return MOCK_TRADES

@app.get("/v1/positions/history", response_model=List[PositionResponse])
async def get_positions_history(
    user: str = Query(...),
    coin: str = Query(...),
    fromMs: Optional[int] = None,
    toMs: Optional[int] = None,
    builderOnly: bool = Query(False)
):
    return MOCK_POSITIONS

@app.get("/v1/pnl", response_model=PnLResponse)
async def get_pnl(
    user: str = Query(...),
    coin: str = Query(...),
    fromMs: Optional[int] = None,
    toMs: Optional[int] = None,
    builderOnly: bool = Query(False),
    maxStartCapital: Optional[float] = 1000.0
):
    return PnLResponse(realizedPnl=75.0, returnPct=7.5, feesPaid=0.8, tradeCount=2)

@app.get("/v1/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    coin: str = Query(...),
    fromMs: Optional[int] = None,
    toMs: Optional[int] = None,
    metric: str = Query("pnl"),
    builderOnly: bool = Query(False),
    maxStartCapital: Optional[float] = 1000.0
):
    return LeaderboardResponse(entries=[
        LeaderboardEntry(rank=1, user="0x123...", metricValue=500.0, tradeCount=10),
        LeaderboardEntry(rank=2, user="0x456...", metricValue=300.0, tradeCount=8),
    ])
