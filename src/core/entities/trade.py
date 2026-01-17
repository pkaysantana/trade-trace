from pydantic import BaseModel
from typing import Optional

class TradeResponse(BaseModel):
    """
    Standardised Trade entity used throughout the core logic.
    Compatible with FastAPI serialisation.
    """
    time_ms: int
    coin: str
    side: str
    sz: float
    px: float
    fee: float
    closed_pnl: float
    builder_id: Optional[str] = None
    hash: Optional[str] = None