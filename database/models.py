from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Boolean,
    BigInteger,
    UniqueConstraint,
)

from .database import Base


class Candle(Base):
    __tablename__ = "candles"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    asset = Column(
        String(32),
        index=True
    )

    timeframe = Column(
        Integer,
        index=True
    )

    timestamp = Column(
        BigInteger,
        index=True
    )

    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            "asset",
            "timeframe",
            "timestamp",
            name="unique_candle"
        ),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    asset = Column(
        String(32),
        index=True
    )

    timestamp = Column(
        BigInteger,
        index=True
    )

    direction = Column(String(8))

    score = Column(Integer)

    ema = Column(Float)
    adx = Column(Float)
    atr = Column(Float)
    ao = Column(Float)
    stochastic = Column(Float)

    confirmed = Column(
        Boolean,
        default=False
    )

    result = Column(
        String(16),
        default="PENDING"
    )