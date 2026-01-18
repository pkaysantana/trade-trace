from pydantic import BaseModel
from typing import Optional

class PnLResponse(BaseModel):
    user: str
    total_pnl: float
    roi: float
    # We can add more fields if needed

class LeaderboardEntry(BaseModel):
    rank: int
    user: str
    pnl: float
    roi: float
    is_clean: bool
