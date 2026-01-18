import psycopg2
from psycopg2.extras import execute_values
from typing import List, Optional
from src.core.interfaces.datasource import IDataSource
from src.core.entities.trade import TradeResponse
from src.core.entities.position import PositionResponse

class PostgresRepo(IDataSource):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _init_db(self):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS positionsnapshots (
                timeMs BIGINT, 
                netSize DECIMAL, 
                avgEntryPx DECIMAL, 
                tainted BOOLEAN, 
                "user" VARCHAR, 
                coin VARCHAR,
                lifecycleId BIGINT
            );
        """)
        conn.commit()
        cur.close()
        conn.close()

    def bulk_insert_positions(self, positions: List[PositionResponse], user: str, coin: str):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        # Prepare data tuple
        data = [
            (p.timeMs, p.netSize, p.avgEntryPx, p.tainted, user, coin, p.lifecycleId)
            for p in positions
        ]
        
        insert_query = """
            INSERT INTO positionsnapshots (timeMs, netSize, avgEntryPx, tainted, "user", coin, lifecycleId)
            VALUES %s
        """
        
        execute_values(cur, insert_query, data)
        conn.commit()
        cur.close()
        conn.close()

    # IDataSource Stub Implementations
    async def get_trades(self, user: str, coin: str, start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[TradeResponse]:
        # In future, read from DB
        return []

    async def get_active_users(self, coin: str, start_time: int) -> List[str]:
        return []

    async def get_historical_equity(self, user: str, timestamp: int) -> float:
        return 1000.0
