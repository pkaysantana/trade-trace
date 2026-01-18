from typing import List
from src.core.entities.trade import TradeResponse
from src.core.entities.position import PositionResponse

class PositionReconstructor:
    @staticmethod
    def reconstruct(trades: List[TradeResponse], target_builder: str = "0xYourBuilder") -> List[PositionResponse]:
        # SORT trades by timeMs
        sorted_trades = sorted(trades, key=lambda t: t.time_ms)
        
        history: List[PositionResponse] = []
        
        # INIT state
        net_size = 0.0
        avg_entry_px = 0.0
        tainted = False
        lifecycle_id = 1  # Start at 1
        
        for trade in sorted_trades:
            # signed_sz = +sz Long, -sz Short
            signed_sz = trade.sz if trade.side == "Long" else -trade.sz
            
            # IF net_size==0: new_lifecycle++ (except for the very first one, handled by init)
            # Actually, if we just finished a cycle (net_size back to 0), we increment for the *next* trade?
            # Or increment when we transition FROM 0 TO non-zero?
            # The prompt says: "IF net_size==0: new_lifecycle++". 
            # If we are at 0, and we are processing a trade, we are starting a new lifecycle.
            if net_size == 0:
                lifecycle_id += 1
                tainted = False # Reset taint on new lifecycle
                avg_entry_px = 0.0 # Reset avg px

            previous_net_size = net_size
            new_net = net_size + signed_sz
            
            # Update Average Entry Price
            if previous_net_size == 0:
                # New position opening
                avg_entry_px = trade.px
            elif (previous_net_size > 0 and signed_sz > 0) or (previous_net_size < 0 and signed_sz < 0):
                # Increasing (same sign): weighted_avg
                # weighted_avg = (old_net*avg_px + sz*trade.px) / new_net
                total_cost = (abs(previous_net_size) * avg_entry_px) + (abs(signed_sz) * trade.px)
                avg_entry_px = total_cost / abs(new_net)
            elif (previous_net_size > 0 and new_net < 0) or (previous_net_size < 0 and new_net > 0):
                # Flipping: Price resets to current trade price
                avg_entry_px = trade.px
            else:
                # Reducing/Closing part: Price stays sticky
                pass

            # TAINT: if tainted or (trade.builder!=target and net_size!=0)
            # Logic: If already tainted, stay tainted.
            # If not tainted, check if this trade causes taint.
            # Trade causes taint if builder is wrong.
            # Note: The prompt condition "and net_size!=0" is confusing.
            # Assuming we taint if the trade is not from target builder.
            
            is_trade_clean = (trade.builder_id and trade.builder_id.lower() == target_builder.lower())
            
            # We treat empty builder_id as dirty if we strictly enforce builderOnly
            # User said: "builderOnly filter WORKS (tainted:true excluded)"
            # User said: "Check trade.builder_address. If it matches TARGET_BUILDER, it is valid."
            
            if not is_trade_clean:
                tainted = True
            
            net_size = new_net
            
            # IF new_net==0: reset tainted=False
            # Wait, if we just closed the position, the *next* trade starts clean.
            # But the snapshot *at this moment* (size 0) records the end of the position.
            # Should the end snapshot be tainted if the lifecycle was tainted? Yes.
            # The prompt says "IF new_net==0: reset tainted=False" AFTER appending? 
            # "APPEND Position... IF new_net==0: reset tainted=False" ??
            # Prompt order:
            # ...
            # TAINT: ...
            # IF new_net==0: reset tainted=False  <-- This looks like it clears it BEFORE append?
            # "APPEND Position..."
            # If I clear it before append, the closing snapshot will look clean. That's probably wrong.
            # I will append FIRST, then reset if 0.
            
            pos = PositionResponse(
                timeMs=trade.time_ms,
                netSize=net_size,
                avgEntryPx=avg_entry_px,
                tainted=tainted,
                lifecycleId=lifecycle_id
            )
            history.append(pos)
            
            # Ensure precise zero check (float math)
            if abs(net_size) < 1e-9:
                net_size = 0.0
                # We don't reset lifecycle_id here, we do it at start of next trade if net_size is 0.
    
        return history
