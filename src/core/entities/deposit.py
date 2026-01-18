"""
Deposit Entity for TradeTrace

Tracks user deposits for fair competition filtering.
"""
from pydantic import BaseModel
from decimal import Decimal
from typing import Optional


class DepositResponse(BaseModel):
    """
    Represents a single deposit/withdrawal event.
    """
    timestamp_ms: int
    asset: str  # e.g., "USDC"
    amount: float  # Positive = deposit, Negative = withdrawal
    tx_hash: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "timestamp_ms": 1705000000000,
                "asset": "USDC",
                "amount": 10000.0,
                "tx_hash": "0xabc123..."
            }
        }


class DepositsAggregateResponse(BaseModel):
    """
    Aggregated deposit data for a user.
    """
    total_deposits: float
    total_withdrawals: float
    net_transfers: float
    deposit_count: int
    withdrawal_count: int
    deposits: list[DepositResponse]
