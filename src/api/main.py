import logging
import asyncio
from typing import List, Optional, Dict
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- Imports ---
from src.core.interfaces.datasource import IDataSource
from src.infrastructure.gateways.hl_public_api import HLPublicGateway
from src.core.entities.trade import TradeResponse
from src.core.entities.position import PositionResponse
from src.core.entities.leaderboard import LeaderboardEntry, PnLResponse
from src.core.use_cases.position_reconstructor import PositionReconstructor

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradeTrace")

app = FastAPI(title="TradeTrace API", version="1.0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency Injection ---

def get_datasource() -> IDataSource:
    return HLPublicGateway(use_testnet=False)

# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "mode": "Hyperliquid Public API via Gateway"}

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
    builderOnly: bool = Query(False),
    gateway: IDataSource = Depends(get_datasource)
):
    trades = await gateway.get_trades(user, coin, fromMs, toMs)
    positions = PositionReconstructor.reconstruct(trades)
    
    if builderOnly:
        # Filter to only show positions that are NOT tainted
        # Note: This filters snapshots. If a lifecycle is tainted, all its snapshots are tainted.
        positions = [p for p in positions if not p.tainted]
        
    return positions

@app.get("/v1/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(
    coin: str = Query(...),
    metric: str = Query("pnl", description="'pnl' or 'roi'"),
    builderOnly: bool = Query(False, description="Exclude users with non-builder trades"),
    gateway: IDataSource = Depends(get_datasource)
):
    """
    Real-time Leaderboard:
    Scans active users, calculates their builder-specific PnL, and ranks them.
    """
    # 1. Get active users
    # We use 0 as start_time to get default list for now
    users = await gateway.get_active_users(coin, 0)
    
    entries = []
    
    for user in users:
        # 2. Get trades
        trades = await gateway.get_trades(user, coin)
        if not trades:
            continue
            
        # 3. Reconstruct positions
        positions = PositionReconstructor.reconstruct(trades)
        
        # 4. Filter Tainted Lifecycles
        # Identify lifecycle IDs that are tainted
        tainted_cycles = set()
        for p in positions:
            if p.tainted and p.lifecycleId is not None:
                tainted_cycles.add(p.lifecycleId)
        
        # 5. Calculate PnL
        # We need to sum closed_pnl from trades corresponding to CLEAN lifecycles.
        # We assume positions[i] corresponds to sorted_trades[i].
        # The Reconstructor sorts trades internally. We must sort them here too to match,
        # OR better: The reconstructor should return mapping.
        # But we can't change signature easily.
        # Let's re-sort to match Reconstructor's logic.
        trades.sort(key=lambda x: x.time_ms)
        
        # Make sure lengths match (they should)
        if len(trades) != len(positions):
            logger.warning(f"Mismatch trades/positions for {user}")
            continue
            
        total_pnl = 0.0
        total_fees = 0.0
        
        # Check if user is completely clean if required? 
        # No, builderOnly usually means "Show me the leaderboard calculated using ONLY builder trades".
        
        for i, trade in enumerate(trades):
            pos = positions[i]
            # If builderOnly is requested, and this lifecycle is tainted, skip metrics
            if builderOnly and pos.lifecycleId in tainted_cycles:
                continue
            
            # If not filtering, or it's clean, include it.
            # ARCHITECTURE.md: "is_clean: True if 0 tainted lifecycles"
            
            total_pnl += trade.closed_pnl
            total_fees += trade.fee
            
        net_pnl = total_pnl - total_fees
        
        # 6. Calculate ROE
        # EffectiveCap = max(Equity, 1000)
        equity = await gateway.get_historical_equity(user, 0)
        effective_cap = max(equity, 1000.0)
        roi = (net_pnl / effective_cap) * 100.0
        
        is_user_clean = (len(tainted_cycles) == 0)
        
        entries.append(LeaderboardEntry(
            rank=0, # assigned later
            user=user,
            pnl=net_pnl,
            roi=roi,
            is_clean=is_user_clean
        ))
        
    # Sort
    if metric == "roi":
        entries.sort(key=lambda x: x.roi, reverse=True)
    else:
        entries.sort(key=lambda x: x.pnl, reverse=True)
        
    # Assign Ranks
    for i, entry in enumerate(entries):
        entry.rank = i + 1
        
    return entries

# --- Persistence Endpoint (Fix for "Broken" link) ---
from src.infrastructure.persistence.postgres_repo import PostgresRepo
import os

def get_repo() -> Optional[PostgresRepo]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        return PostgresRepo(db_url)
    except Exception as e:
        logger.error(f"Failed to connect to DB: {e}")
        return None

@app.post("/v1/sync")
async def sync_data(
    coin: str = Query(..., description="Token Symbol"),
    gateway: IDataSource = Depends(get_datasource),
    repo: Optional[PostgresRepo] = Depends(get_repo)
):
    """
    Triggers fetching of data from Hyperliquid and persisting to Postgres.
    """
    if not repo:
        raise HTTPException(status_code=503, detail="Database not configured or unavailable")

    users = await gateway.get_active_users(coin, 0)
    stats = {"users_processed": 0, "positions_saved": 0}
    
    for user in users:
        trades = await gateway.get_trades(user, coin)
        if not trades:
            continue
            
        positions = PositionReconstructor.reconstruct(trades)
        
        # Persist to DB (Offload to thread to avoid blocking async loop)
        try:
            await asyncio.to_thread(repo.bulk_insert_positions, positions, user, coin)
            stats["positions_saved"] += len(positions)
            stats["users_processed"] += 1
        except Exception as e:
            logger.error(f"Failed to persist for {user}: {e}")
            
    return {"status": "success", "stats": stats}