import asyncio
from typing import List, Optional
from pydantic import BaseModel
import logging

from src.core.interfaces.datasource import IDataSource
from src.core.entities.trade import TradeResponse

logger = logging.getLogger(__name__)

# --- Output Models ---
class PositionResponse(BaseModel):
    timeMs: int
    netSize: float
    avgEntryPx: float
    realizedPnl: float = 0.0
    tainted: bool = False

class PnLResponse(BaseModel):
    user: str = ""  # Added user field for leaderboard identification
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
    tainted: bool

# --- Business Logic Services ---

class PositionService:
    def __init__(self, datasource: IDataSource):
        self.db = datasource
        self.TARGET_BUILDER = "0x31ca8395cf837de08b24da3f660e77761dfb974b" 

    async def get_history(self, user: str, coin: str, start: Optional[int], end: Optional[int]) -> List[PositionResponse]:
        trades = await self.db.get_trades(user, coin, start, end)
        return self._reconstruct_lifecycle(trades)

    def _reconstruct_lifecycle(self, trades: List[TradeResponse]) -> List[PositionResponse]:
        history = []
        net_size = 0.0
        avg_entry_px = 0.0
        is_tainted = False
        
        for t in trades:
            trade_sz = t.sz if t.side == "Long" else -t.sz
            new_size = net_size + trade_sz
            
            # Taint Logic
            if not is_tainted:
                if t.builder_id != self.TARGET_BUILDER:
                    if net_size != 0 or trade_sz != 0:
                        is_tainted = True

            # Avg Entry Logic (Weighted Average)
            if net_size == 0:
                avg_entry_px = t.px
            elif (net_size > 0 and trade_sz > 0) or (net_size < 0 and trade_sz < 0):
                current_cost = abs(net_size) * avg_entry_px
                added_cost = abs(trade_sz) * t.px
                avg_entry_px = (current_cost + added_cost) / abs(new_size)
            elif (net_size > 0 > new_size) or (net_size < 0 < new_size):
                avg_entry_px = t.px
                if t.builder_id == self.TARGET_BUILDER:
                    is_tainted = False
                else:
                    is_tainted = True

            # Zero Reset
            if new_size == 0:
                avg_entry_px = 0.0
                is_tainted = False

            net_size = new_size
            history.append(PositionResponse(
                timeMs=t.time_ms,
                netSize=net_size,
                avgEntryPx=avg_entry_px,
                tainted=is_tainted
            ))
        return history

class LeaderboardService:
    def __init__(self, datasource: IDataSource):
        self.db = datasource
        self.TARGET_BUILDER = "0x31ca8395cf837de08b24da3f660e77761dfb974b"

    async def calculate_pnl(self, user: str, coin: str) -> PnLResponse:
        trades = await self.db.get_trades(user, coin)
        
        if not trades:
            return PnLResponse(user=user, realizedPnl=0, returnPct=0, feesPaid=0, tradeCount=0)

        realized = sum(t.closed_pnl for t in trades)
        fees = sum(t.fee for t in trades)
        count = len(trades)
        
        # Strict Taint Check: If ANY trade is not ours, the user is tainted
        tainted = any(t.builder_id != self.TARGET_BUILDER for t in trades)

        equity = await self.db.get_historical_equity(user, 0)
        eff_cap = min(equity, 1000.0) 
        roi = ((realized - fees) / eff_cap) * 100 if eff_cap > 0 else 0.0
        
        return PnLResponse(
            user=user,
            realizedPnl=realized,
            returnPct=roi,
            feesPaid=fees,
            tradeCount=count,
            tainted=tainted
        )

    async def get_leaderboard(self, coin: str, metric: str, builder_only: bool) -> List[LeaderboardEntry]:
        # 1. Get all candidates (from Gateway Stub or DB)
        active_users = await self.db.get_active_users(coin, 0)
        
        # 2. Calculate PnL for ALL users in parallel (Fast!)
        tasks = [self.calculate_pnl(user, coin) for user in active_users]
        results = await asyncio.gather(*tasks)

        # 3. Filter and Rank
        leaderboard = []
        for pnl in results:
            # Builder Only Filter: Skip if user is tainted
            if builder_only and pnl.tainted:
                continue
            
            # Select Metric
            val = pnl.returnPct if metric == "roi" else pnl.realizedPnl
            
            leaderboard.append(LeaderboardEntry(
                rank=0, # Placeholder
                user=pnl.user,
                metricValue=val,
                tradeCount=pnl.tradeCount,
                tainted=pnl.tainted
            ))
            
        # 4. Sort Descending
        leaderboard.sort(key=lambda x: x.metricValue, reverse=True)
        
        # 5. Assign Ranks
        for i, entry in enumerate(leaderboard):
            entry.rank = i + 1
            
        return leaderboard