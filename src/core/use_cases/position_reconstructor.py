from ..entities.position import PositionState
from ..entities.trade import TradeObject
import math

def signs_match(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)

def check_taint(current_state: PositionState, trade: TradeObject) -> bool:
    return False  # Stub

def process_trade(current_state: PositionState, trade: TradeObject) -> PositionState:
    prev_sz = current_state.net_size
    trade_sz = trade.size if trade.side == "Long" else -trade.size
    new_sz = prev_sz + trade_sz
    
    tainted = check_taint(current_state, trade)
    
    if prev_sz == 0:
        new_px = trade.price
    elif signs_match(prev_sz, trade_sz):
        total_cost = abs(prev_sz) * current_state.avg_entry_px + abs(trade_sz) * trade.price
        new_px = total_cost / abs(new_sz)
    elif abs(trade_sz) > abs(prev_sz):
        new_px = trade.price
    else:
        new_px = current_state.avg_entry_px
    
    if new_sz == 0:
        new_px = 0.0
        tainted = False
    
    return PositionState(new_sz, new_px, tainted, trade.timestamp)
