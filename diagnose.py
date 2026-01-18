
import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.getcwd())

try:
    from src.core.entities.position import PositionResponse
    from src.core.entities.trade import TradeResponse
    from src.core.use_cases.position_reconstructor import PositionReconstructor
    from src.infrastructure.gateways.hl_public_api import HLPublicGateway
    from src.api.main import app
    print("✅ All imports successful.")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test Reconstructor Logic Simple
def test_reconstruct():
    try:
        t1 = TradeResponse(time_ms=1000, coin="BTC", side="Long", sz=1.0, px=50000.0, fee=0.0, closed_pnl=0.0, builder_id="0xBuild")
        t2 = TradeResponse(time_ms=2000, coin="BTC", side="Short", sz=1.0, px=51000.0, fee=0.0, closed_pnl=1000.0, builder_id="0xBuild")
        
        trades = [t1, t2]
        positions = PositionReconstructor.reconstruct(trades, "0xBuild")
        
        if len(positions) == 2:
            print("✅ Reconstruction logic basic test passed.")
        else:
            print(f"❌ Reconstruction logic failed, expected 2 positions, got {len(positions)}")
    except Exception as e:
        print(f"❌ Reconstruction raised exception: {e}")

if __name__ == "__main__":
    test_reconstruct()
