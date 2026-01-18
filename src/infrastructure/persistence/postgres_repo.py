import psycopg2
from psycopg2.extras import execute_values
from typing import List, Optional
from src.core.interfaces.datasource import IDataSource
from src.core.entities.trade import TradeResponse
from src.core.entities.position import PositionResponse
from src.core.entities.deposit import DepositResponse

class PostgresRepo(IDataSource):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _init_db(self):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        # Positions Table
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
        
        # Trades Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                time_ms BIGINT,
                coin VARCHAR,
                side VARCHAR,
                sz DECIMAL,
                px DECIMAL,
                fee DECIMAL,
                closed_pnl DECIMAL,
                builder_id VARCHAR,
                hash VARCHAR,
                "user" VARCHAR
            );
        """)

        # Deposits Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                timestamp_ms BIGINT,
                asset VARCHAR,
                amount DECIMAL,
                tx_hash VARCHAR,
                "user" VARCHAR
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()

    def bulk_insert_positions(self, positions: List[PositionResponse], user: str, coin: str):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
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

    def bulk_insert_trades(self, trades: List[TradeResponse], user: str):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        data = [
            (t.time_ms, t.coin, t.side, t.sz, t.px, t.fee, t.closed_pnl, t.builder_id, t.hash, user)
            for t in trades
        ]
        
        insert_query = """
            INSERT INTO trades (time_ms, coin, side, sz, px, fee, closed_pnl, builder_id, hash, "user")
            VALUES %s
        """
        
        execute_values(cur, insert_query, data)
        conn.commit()
        cur.close()
        conn.close()

    def bulk_insert_deposits(self, deposits: List[DepositResponse], user: str):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        data = [
            (d.timestamp_ms, d.asset, d.amount, d.tx_hash, user)
            for d in deposits
        ]
        
        insert_query = """
            INSERT INTO deposits (timestamp_ms, asset, amount, tx_hash, "user")
            VALUES %s
        """
        
        execute_values(cur, insert_query, data)
        conn.commit()
        cur.close()
        conn.close()

    # IDataSource Implementation
    async def get_trades(self, user: str, coin: str, start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[TradeResponse]:
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        query = """
            SELECT time_ms, coin, side, sz, px, fee, closed_pnl, builder_id, hash
            FROM trades
            WHERE "user" = %s AND coin = %s
        """
        params = [user, coin]
        
        if start_time:
            query += " AND time_ms >= %s"
            params.append(start_time)
        if end_time:
            query += " AND time_ms <= %s"
            params.append(end_time)
            
        cur.execute(query, params)
        rows = cur.fetchall()
        
        trades = []
        for row in rows:
            trades.append(TradeResponse(
                time_ms=row[0],
                coin=row[1],
                side=row[2],
                sz=float(row[3]),
                px=float(row[4]),
                fee=float(row[5]),
                closed_pnl=float(row[6]),
                builder_id=row[7],
                hash=row[8]
            ))
            
        cur.close()
        conn.close()
        return trades

    async def get_active_users(self, coin: str, start_time: int) -> List[str]:
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        query = """
            SELECT DISTINCT "user" 
            FROM trades 
            WHERE coin = %s AND time_ms >= %s
        """
        cur.execute(query, (coin, start_time))
        users = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        return users

    async def get_user_deposits(
        self, 
        user: str, 
        from_ms: Optional[int] = None, 
        to_ms: Optional[int] = None
    ) -> List[DepositResponse]:
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor()
        
        query = """
            SELECT timestamp_ms, asset, amount, tx_hash
            FROM deposits
            WHERE "user" = %s
        """
        params = [user]
        
        if from_ms:
            query += " AND timestamp_ms >= %s"
            params.append(from_ms)
        if to_ms:
            query += " AND timestamp_ms <= %s"
            params.append(to_ms)
            
        cur.execute(query, params)
        rows = cur.fetchall()
        
        deposits = []
        for row in rows:
            deposits.append(DepositResponse(
                timestamp_ms=row[0],
                asset=row[1],
                amount=float(row[2]),
                tx_hash=row[3]
            ))
            
        cur.close()
        conn.close()
        return deposits

    async def get_historical_equity(self, user: str, timestamp: int) -> float:
        # Complex to reconstruct exact equity from just trades + initial. 
        # For now, return default or mock.
        return 1000.0
