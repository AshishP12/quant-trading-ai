from sqlalchemy import Column, Integer, Float, String, DateTime, func
from app.core.db import Base

class TickData(Base):
    __tablename__ = "tick_data"
    
    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String, index=True)
    last_price = Column(Float)
    volume = Column(Integer, default=0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
