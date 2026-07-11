# CHANGELOG

## v0.6.0 — EMA Indicators

- Добавлен универсальный `EMAIndicator`.
- Зарегистрированы EMA 5, 8, 10, 13, 20, 30, 50, 100 и 200.
- Первая EMA инициализируется через SMA.
- Последующие значения рассчитываются рекурсивно.
- Indicator Engine теперь передаёт индикаторам всю доступную историю.
- `required_candles` используется как порог готовности.
- Значения снимка форматируются с точностью до восьми знаков.
- Обновлены PROJECT.md, ROADMAP.md и IDEAS.md.

## v0.5.0 — Indicator Engine Foundation

- Добавлены Indicator, Registry, Snapshot и Engine.
- Добавлен технический ClosePriceIndicator.
