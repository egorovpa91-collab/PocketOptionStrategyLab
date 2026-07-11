# ROADMAP

## Этап 1 — Фундамент данных

- [x] Scanner, SQLite и UPSERT
- [x] new_closed_candle
- [x] Candle Manager
- [x] Цикл из 6 активов

## Этап 2 — Indicator Engine

- [x] Контракт Indicator
- [x] Indicator Registry
- [x] Indicator Snapshot
- [x] ClosePriceIndicator
- [x] Универсальный EMAIndicator
- [x] EMA 5, 8, 10, 13, 20, 30, 50, 100, 200
- [ ] Проверить EMA в живом запуске
- [ ] Добавить эталонные автоматические тесты EMA
- [ ] RSI
- [ ] ATR
- [ ] ADX, +DI, -DI
- [ ] AO
- [ ] Stochastic
- [ ] SuperTrend
- [ ] Сохранение результатов в SQLite

## Этап 3 — Strategy Engine

- [ ] Контракт стратегии
- [ ] CALL / PUT / NO SIGNAL
- [ ] Экспирация 10 минут
- [ ] Проверка результатов
