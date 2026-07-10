from sqlalchemy import select

from .database import engine, Base, get_session
from .models import Candle, Signal


def create_database():
    Base.metadata.create_all(bind=engine)
    print("✓ SQLite база готова")


# ---------------------------------------------------
# CANDLES
# ---------------------------------------------------

def save_candle(
    asset,
    timeframe,
    timestamp,
    open_price,
    high,
    low,
    close,
    volume=0,
):
    session = get_session()

    candle = Candle(
        asset=asset,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )

    session.add(candle)
    session.commit()
    session.close()


def get_last_candles(asset, timeframe=60, limit=500):
    session = get_session()

    candles = (
        session.query(Candle)
        .filter(
            Candle.asset == asset,
            Candle.timeframe == timeframe,
        )
        .order_by(Candle.timestamp.desc())
        .limit(limit)
        .all()
    )

    session.close()

    candles.reverse()

    return candles


# ---------------------------------------------------
# SIGNALS
# ---------------------------------------------------

def save_signal(
    asset,
    timestamp,
    direction,
    score,
    ema,
    adx,
    atr,
    ao,
    stochastic,
):
    session = get_session()

    signal = Signal(
        asset=asset,
        timestamp=timestamp,
        direction=direction,
        score=score,
        ema=ema,
        adx=adx,
        atr=atr,
        ao=ao,
        stochastic=stochastic,
    )

    session.add(signal)
    session.commit()

    session.close()