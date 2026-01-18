from ...interfaces.IDataSource import IDataSource
from ...entities.trade import TradeObject
from typing import List
from datetime import datetime

class LocalMockDataSource(IDataSource):
    async def get_trades(self, user: str, coin: str, start_time: int, end_time: int) -> List[TradeObject]:
        # Mock trades for testing
        return [
            TradeObject(
                timestamp=int(datetime.now().timestamp() * 1000),
                side="Long", size=1.0, price=40000, fee=0.1, 
                builder_id="0xmock", closed_pnl=50.0
            )
        ]
    
    async def get_active_users(self, coin: str, start_time: int) -> List[str]:
        return ["0xmockuser1", "0xmockuser2"]
    
    async def get_historical_equity(self, user: str, timestamp: int) -> float:
        return 1000.0
