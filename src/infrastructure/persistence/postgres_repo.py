"""
Full PostgreSQL implementation from ARCHITECTURE.md Section 6
All 3 tables + indexes for leaderboard performance
"""

from sqlalchemy import (
    Column, BigInteger, String, Float, Boolean, DateTime, create_engine, Index,
    ForeignKey, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from typing import List
from datetime import datetime
import uuid

Base = declarative_base()

class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(BigInteger, primary_key=True)
    user_address = Column(String(42), index=True)
    coin = Column(String(12), index=True)
    sz = Column(Float)
    px = Column(Float)
    closed_pnl = Column(Float)
    fee = Column(Float)
    builder_id = Column(String(42))
    time_ms = Column(BigInteger, index=True)
    lifecycle_id = Column(UUID(as_uuid=True))
    
    # ARCHITECTURE.md indexes
    __table_args__ = (
        Index('idx_user_coin_time', 'user_address', 'coin', 'time_ms'),
        Index('idx_builder_time', 'builder_id', 'time_ms'),
    )

class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"
    
    id = Column(BigInteger, primary_key=True)
    trade_id = Column(BigInteger, ForeignKey('trades.id'))
    user_address = Column(String(42), index=True)
    coin = Column(String(12), index=True)
    net_size = Column(Float)
    avg_entry_px = Column(Float)
    is_tainted = Column(Boolean, index=True)
    lifecycle_id = Column(UUID(as_uuid=True), index=True)
    
    # ARCHITECTURE.md indexes
    __table_args__ = (
        Index('idx_coin_tainted_lifecycle', 'coin', 'is_tainted', 'lifecycle_id'),
    )

class LeaderboardCache(Base):
    __tablename__ = "leaderboard_cache"
    
    rank_id = Column(BigInteger, primary_key=True)
    user_address = Column(String(42), index=True)
    coin = Column(String(12))
    total_pnl = Column(Float)
    return_pct = Column(Float)
    trade_count = Column(BigInteger)
    is_clean = Column(Boolean, index=True)
    as_of = Column(DateTime, default=func.now())

class PostgresRepo:
    """Full Postgres repository implementation"""
    
    def __init__(self, db_url: str = "postgresql://user:pass@localhost/tradetrace"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def save_trade(self, trade: Trade):
        with self.get_session() as session:
            session.add(trade)
            session.commit()
    
    def get_trades(self, user: str, coin: str, from_ms: int, to_ms: int) -> List[Trade]:
        with self.get_session() as session:
            return session.query(Trade).filter(
                Trade.user_address == user,
                Trade.coin == coin,
                Trade.time_ms >= from_ms,
                Trade.time_ms <= to_ms
            ).order_by(Trade.time_ms).all()
    
    # Leaderboard query (ARCHITECTURE.md optimized)
    def get_leaderboard(self, coin: str, is_clean: bool = True) -> List[LeaderboardCache]:
        with self.get_session() as session:
            return session.query(LeaderboardCache).filter(
                LeaderboardCache.coin == coin,
                LeaderboardCache.is_clean == is_clean
            ).order_by(LeaderboardCache.return_pct.desc()).all()
