from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.exc import SQLAlchemyError

from .database import Base, engine, get_session
from .models import Candle, Signal


class CandleWriteStatus(str, Enum):
    """Результат сохранения свечи в базе данных."""

    INSERTED = "INSERTED"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class CandleWriteResult:
    """Результат операции UPSERT для одной свечи."""

    status: CandleWriteStatus
    asset: str
    timeframe: int
    timestamp: int


def create_database() -> None:
    """Создаёт отсутствующие таблицы SQLite."""

    Base.metadata.create_all(bind=engine)
    print("✓ SQLite база готова")


# ---------------------------------------------------
# CANDLES
# ---------------------------------------------------


def save_candle(
    asset: str,
    timeframe: int,
    timestamp: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0,
) -> CandleWriteResult:
    """
    Создаёт свечу или обновляет существующую запись.

    Уникальность свечи определяется составным ключом:

    asset + timeframe + timestamp

    Returns:
        CandleWriteResult со статусом INSERTED, UPDATED или UNCHANGED.
    """

    session = get_session()

    try:
        candle = (
            session.query(Candle)
            .filter(
                Candle.asset == asset,
                Candle.timeframe == timeframe,
                Candle.timestamp == timestamp,
            )
            .one_or_none()
        )

        if candle is None:
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

            return CandleWriteResult(
                status=CandleWriteStatus.INSERTED,
                asset=asset,
                timeframe=timeframe,
                timestamp=timestamp,
            )

        has_changes = any(
            (
                candle.open != open_price,
                candle.high != high,
                candle.low != low,
                candle.close != close,
                candle.volume != volume,
            )
        )

        if not has_changes:
            return CandleWriteResult(
                status=CandleWriteStatus.UNCHANGED,
                asset=asset,
                timeframe=timeframe,
                timestamp=timestamp,
            )

        candle.open = open_price
        candle.high = high
        candle.low = low
        candle.close = close
        candle.volume = volume

        session.commit()

        return CandleWriteResult(
            status=CandleWriteStatus.UPDATED,
            asset=asset,
            timeframe=timeframe,
            timestamp=timestamp,
        )

    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


def get_last_candles(
    asset: str,
    timeframe: int = 60,
    limit: int = 500,
) -> list[Candle]:
    """Возвращает последние свечи актива в хронологическом порядке."""

    session = get_session()

    try:
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

        candles.reverse()
        return candles
    finally:
        session.close()


def get_candles_until(
    asset: str,
    timeframe: int,
    timestamp: int,
    limit: int = 500,
) -> list[Candle]:
    """
    Возвращает свечи не позднее заданного timestamp.

    Результат ограничивается последними ``limit`` записями и возвращается
    в хронологическом порядке. Метод используется Candle Manager для
    восстановления истории только до подтверждённой закрытой свечи.
    """

    if limit <= 0:
        raise ValueError("limit должен быть больше нуля")

    session = get_session()

    try:
        candles = (
            session.query(Candle)
            .filter(
                Candle.asset == asset,
                Candle.timeframe == timeframe,
                Candle.timestamp <= timestamp,
            )
            .order_by(Candle.timestamp.desc())
            .limit(limit)
            .all()
        )

        candles.reverse()
        return candles
    finally:
        session.close()


# ---------------------------------------------------
# SIGNALS
# ---------------------------------------------------


def save_signal(
    asset: str,
    timestamp: int,
    direction: str,
    score: int,
    ema: float,
    adx: float,
    atr: float,
    ao: float,
    stochastic: float,
) -> None:
    """Сохраняет торговый сигнал в SQLite."""

    session = get_session()

    try:
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
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()
