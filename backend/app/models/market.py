from sqlalchemy import Column, Integer, Float, String, DateTime, func, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.core.db import Base

class TickData(Base):
    __tablename__ = "tick_data"
    
    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String, index=True)
    last_price = Column(Float)
    volume = Column(Integer, default=0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False, index=True)
    balance = Column(Numeric(15, 2), default=100000.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class TradeModel(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direction = Column(String(10), nullable=False)
    strike = Column(String(20), nullable=False)
    qty = Column(Integer, nullable=False)
    entry_spot = Column(Numeric(12, 2), nullable=False)
    exit_spot = Column(Numeric(12, 2), nullable=True)
    entry_premium = Column(Numeric(10, 2), nullable=False)
    exit_premium = Column(Numeric(10, 2), nullable=True)
    entry_time = Column(DateTime(timezone=True), server_default=func.now())
    exit_time = Column(DateTime(timezone=True), nullable=True)
    pnl = Column(Numeric(15, 2), nullable=True)
    reason = Column(String, nullable=True)
    status = Column(String(20), default="ACTIVE")
