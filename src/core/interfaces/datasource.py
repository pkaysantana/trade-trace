from abc import ABC, abstractmethod
from typing import List, Optional
from src.core.entities.trade import TradeResponse

class IDataSource(ABC):
    @abstractmethod
    async def get_trades(
        self, 
        user: str, 
        coin: str, 
        start_time: Optional[int] = None, 
        end_time: Optional[int] = None
    ) -> List[TradeResponse]:
        pass

    @abstractmethod
    async def get_active_users(self, coin: str, start_time: int) -> List[str]:
        pass

    @abstractmethod
    async def get_historical_equity(self, user: str, timestamp: int) -> float:
        pass

    @abstractmethod
    async def get_user_deposits(
        self, 
        user: str, 
        from_ms: Optional[int] = None, 
        to_ms: Optional[int] = None
    ) -> List[dict]:
        """
        Returns list of DepositResponse objects (as dicts or objects).
        """
        pass