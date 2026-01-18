from pydantic import BaseModel
from typing import Optional


class PositionResponse(BaseModel):
    """
    Position snapshot at a point in time.
    Extended with risk metrics for bonus features.
    """
    timeMs: int
    netSize: float
    avgEntryPx: float
    tainted: bool = False
    lifecycleId: Optional[int] = None
    
    # Bonus: Risk Metrics
    liqPx: Optional[float] = None  # Liquidation price
    marginUsedPct: Optional[float] = None  # 0.0 - 1.0 (margin utilization)
    unrealizedPnl: Optional[float] = None  # Current unrealized PnL
    leverage: Optional[float] = None  # Effective leverage


class PortfolioPnLResponse(BaseModel):
    """
    Aggregated PnL across multiple coins.
    """
    user: str
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees: float
    net_pnl: float
    coins: dict  # coin -> PnL breakdown
