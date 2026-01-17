from dataclasses import dataclass

@dataclass
class PositionState:
    net_size: float
    avg_entry_px: float
    is_tainted: bool
    timestamp: int
