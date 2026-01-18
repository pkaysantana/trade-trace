from ..entities.position import PositionState
from ..entities.trade import TradeObject

TARGET_BUILDER = "0x..."  # Env var

def check_taint(current_state: PositionState, trade: TradeObject) -> bool:
    """From ARCHITECTURE.md Section 4"""
    if current_state.is_tainted:
        return True
    
    if trade.builder_id != TARGET_BUILDER:
        if current_state.net_size != 0 or trade.size != 0:
            return True
    
    return False
