# AGENTS.md

Пакет с общим кодом сервисов Astra (astra, astra-app, astra-payment). Схемой
БД владеет репозиторий `astra`: здесь только ORM-отражения нужных колонок
(`src/astra_shared/db/models.py`), миграций нет.

## Правила

- Даты — `timestamp without time zone` с UTC, не `timestamptz`. В отражениях
  колонки объявляются `DateTime` без `timezone=True`, значения пишутся
  `utc_now_naive()`. asyncpg не примет datetime с зоной в `timestamp`, а все
  сервисы пишут в общие таблицы наивным UTC. Соответствие отражений схеме
  astra проверяет `tests/test_shared_models_contract.py` в `astra`.
