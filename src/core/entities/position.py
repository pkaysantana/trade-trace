from pydantic import BaseModel
from typing import Optional

class PositionResponse(BaseModel):
    timeMs: int
    netSize: float
    avgEntryPx: float
    tainted: bool = False
    lifecycleId: Optional[int] = None

