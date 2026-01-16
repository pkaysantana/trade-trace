@dataclass
class TradeObject:
    timestamp: int
    side: str  # "Long"/"Short"
    size: float
    price: float
    fee: float
    builder_id: Optional[str] = None
    closed_pnl: float = 0.0
