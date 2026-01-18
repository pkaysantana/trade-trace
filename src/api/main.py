import logging
import asyncio
from typing import List, Optional, Dict
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- Imports ---
from src.core.interfaces.datasource import IDataSource
from src.infrastructure.gateways.hl_public_api import HLPublicGateway
from src.core.entities.trade import TradeResponse
from src.core.entities.position import PositionResponse, PortfolioPnLResponse
from src.core.entities.leaderboard import LeaderboardEntry, PnLResponse
from src.core.entities.deposit import DepositResponse, DepositsAggregateResponse
from src.core.use_cases.position_reconstructor import PositionReconstructor

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TradeTrace")

app = FastAPI(title="TradeTrace API", version="1.1.0", description="Position reconstruction & leaderboard API with bonus features")

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


# =============================================================================
# BONUS ENDPOINTS - Hyperliquid Challenge High-Impact Features
# =============================================================================

@app.get("/v1/deposits", response_model=DepositsAggregateResponse)
async def get_deposits(
    user: str = Query(..., description="User wallet address"),
    fromMs: Optional[int] = Query(None, description="Start timestamp (ms)"),
    toMs: Optional[int] = Query(None, description="End timestamp (ms)"),
    gateway: HLPublicGateway = Depends(get_datasource)
):
    """
    BONUS: Fetch user deposit/withdrawal history.
    Enables fair competition filtering by tracking capital inflows during comp period.
    """
    deposits = await gateway.get_user_deposits(user, fromMs, toMs)
    
    total_deposits = sum(d.amount for d in deposits if d.amount > 0)
    total_withdrawals = abs(sum(d.amount for d in deposits if d.amount < 0))
    deposit_count = sum(1 for d in deposits if d.amount > 0)
    withdrawal_count = sum(1 for d in deposits if d.amount < 0)
    
    return DepositsAggregateResponse(
        total_deposits=total_deposits,
        total_withdrawals=total_withdrawals,
        net_transfers=total_deposits - total_withdrawals,
        deposit_count=deposit_count,
        withdrawal_count=withdrawal_count,
        deposits=deposits
    )


@app.get("/v1/pnl")
async def get_pnl(
    user: str = Query(..., description="User wallet address"),
    coin: Optional[str] = Query(None, description="Coin symbol or 'portfolio' for all"),
    gateway: HLPublicGateway = Depends(get_datasource)
):
    """
    BONUS: Calculate PnL for single coin or entire portfolio.
    Use coin=portfolio or omit coin for portfolio-level aggregation.
    """
    # Portfolio mode: aggregate across multiple coins
    if coin is None or coin.lower() == "portfolio":
        coins = ["BTC", "ETH", "SOL", "DOGE", "ARB"]  # Top coins
        results = {}
        total_realized = 0.0
        total_unrealized = 0.0
        total_fees = 0.0
        
        for c in coins:
            try:
                trades = await gateway.get_trades(user, c)
                if not trades:
                    continue
                
                realized = sum(t.closed_pnl for t in trades)
                fees = sum(t.fee for t in trades)
                
                # Get current unrealized PnL
                current_pos = await gateway.get_current_position(user, c)
                unrealized = current_pos.get("unrealizedPnl", 0) if current_pos else 0
                
                results[c] = {
                    "realized_pnl": realized,
                    "unrealized_pnl": unrealized,
                    "fees": fees,
                    "net_pnl": realized - fees + unrealized,
                    "trade_count": len(trades)
                }
                
                total_realized += realized
                total_unrealized += unrealized
                total_fees += fees
                
            except Exception as e:
                logger.warning(f"Failed to get PnL for {c}: {e}")
                continue
        
        return PortfolioPnLResponse(
            user=user,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
            total_fees=total_fees,
            net_pnl=total_realized - total_fees + total_unrealized,
            coins=results
        )
    
    # Single coin mode
    trades = await gateway.get_trades(user, coin)
    if not trades:
        return {"user": user, "coin": coin, "realized_pnl": 0, "fees": 0, "net_pnl": 0}
    
    realized = sum(t.closed_pnl for t in trades)
    fees = sum(t.fee for t in trades)
    
    current_pos = await gateway.get_current_position(user, coin)
    unrealized = current_pos.get("unrealizedPnl", 0) if current_pos else 0
    
    return {
        "user": user,
        "coin": coin,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "fees": fees,
        "net_pnl": realized - fees + unrealized,
        "trade_count": len(trades)
    }


@app.get("/v1/positions/current")
async def get_current_position(
    user: str = Query(..., description="User wallet address"),
    coin: str = Query(..., description="Coin symbol"),
    gateway: HLPublicGateway = Depends(get_datasource)
):
    """
    BONUS: Get current live position with risk metrics (liqPx, marginUsed%).
    """
    position = await gateway.get_current_position(user, coin)
    
    if not position:
        return {"user": user, "coin": coin, "hasPosition": False}
    
    # Calculate margin used percentage
    account_value = await gateway.get_account_value(user)
    margin_used_pct = position.get("marginUsed", 0) / account_value if account_value > 0 else 0
    
    return {
        "user": user,
        "coin": coin,
        "hasPosition": True,
        "netSize": position["netSize"],
        "entryPx": position["entryPx"],
        "liqPx": position["liqPx"],
        "unrealizedPnl": position["unrealizedPnl"],
        "leverage": position["leverage"],
        "marginUsedPct": round(margin_used_pct, 4)
    }


@app.get("/v1/leaderboard/fair")
async def get_fair_leaderboard(
    coin: str = Query(..., description="Token Symbol"),
    metric: str = Query("pnl", description="'pnl' or 'roi'"),
    fromMs: Optional[int] = Query(None, description="Competition start time"),
    toMs: Optional[int] = Query(None, description="Competition end time"),
    gateway: HLPublicGateway = Depends(get_datasource)
):
    """
    BONUS: Deposit-adjusted leaderboard for fair competition.
    Adjusts ROE calculation based on deposits during competition period.
    """
    users = await gateway.get_active_users(coin, 0)
    entries = []
    
    for user in users:
        try:
            # Get trades
            trades = await gateway.get_trades(user, coin, fromMs, toMs)
            if not trades:
                continue
            
            # Calculate PnL
            realized_pnl = sum(t.closed_pnl for t in trades)
            fees = sum(t.fee for t in trades)
            net_pnl = realized_pnl - fees
            
            # Get deposits during period for fair scoring
            deposits = await gateway.get_user_deposits(user, fromMs, toMs)
            deposit_total = sum(d.amount for d in deposits if d.amount > 0)
            
            # Fair ROE: PnL / (starting_capital + mid-comp deposits)
            starting_equity = await gateway.get_historical_equity(user, fromMs or 0)
            effective_capital = starting_equity + deposit_total
            fair_roi = (net_pnl / effective_capital) * 100 if effective_capital > 0 else 0
            
            # Check if user had deposits during comp (flag for transparency)
            had_mid_comp_deposits = deposit_total > 0
            
            entries.append({
                "rank": 0,
                "user": user,
                "pnl": net_pnl,
                "roi": fair_roi,
                "starting_equity": starting_equity,
                "deposits_during_comp": deposit_total,
                "effective_capital": effective_capital,
                "had_mid_comp_deposits": had_mid_comp_deposits,
                "trade_count": len(trades)
            })
            
        except Exception as e:
            logger.warning(f"Failed to process {user} for fair leaderboard: {e}")
            continue
    
    # Sort by metric
    if metric == "roi":
        entries.sort(key=lambda x: x["roi"], reverse=True)
    else:
        entries.sort(key=lambda x: x["pnl"], reverse=True)
    
    # Assign ranks
    for i, entry in enumerate(entries):
        entry["rank"] = i + 1
    
    return entries