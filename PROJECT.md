# Pocket Option Strategy Research Lab

## Назначение

Это **НЕ торговый бот**.

Это исследовательская лаборатория стратегий.

### Цели

-   Сбор истории рынка
-   Хранение истории в SQLite
-   Тестирование тысяч стратегий
-   Поиск лучших параметров
-   Windows-приложение

## Структура

    PocketOptionStrategyLab/
    main.py
    config.py
    database/
    scanner/
    indicators/
    strategy/
    reports/
    optimizer/
    ui/
    data/
    logs/

## Scanner

Работает 24/7. Получает свечи и записывает их в SQLite. В памяти хранит
только последние 500 свечей.

## Database

SQLite. Таблицы: - candles - signals - results - reports - settings

## Indicator Engine

EMA, ADX, ATR, AO, Stochastic, SuperTrend, RSI.

## Strategy Engine

Экспирация 10 минут. Система оценки 9 баллов. Минимум для входа --- 7
баллов.

## Отчеты

Каждый час: - сигналы - WIN/LOSS - WinRate - средний Score

## Работа с парами

Пары делятся на блоки по 9. Каждый блок работает 24 часа. После этого
автоматически переключается следующий.

## AI Optimizer

Будет автоматически искать лучшие параметры стратегий.

## Текущий прогресс

-   Создан проект
-   Настроено окружение
-   Создан модуль database
-   Автоматически создается history.db

## Следующий этап

Подключить Scanner к новой архитектуре и начать запись свечей в SQLite.
