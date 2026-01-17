from ..entities.trade import TradeObject
from typing import List
from decimal import Decimal

def calculate_pnl(trades: List[TradeObject], equity_start: float = 1000, max_capital: float = 1000) -> dict:
    """From ARCHITECTURE.md Section 5"""
    realized_pnl = sum(t.closed_pnl for t in trades) - sum(t.fee for t in trades)
    effective_cap = min(equity_start, max_capital)
    return_pct = (realized_pnl / effective_cap) * 100 if effective_cap > 0 else 0
    
    return {
        "realized_pnl": realized_pnl,
        "return_pct": return_pct,
        "fees_paid": sum(t.fee for t in trades),
        "trade_count": len(trades)
    }
