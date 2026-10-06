# astra-shared
Общий код и ресурсы Astra

## Модули

- `astra_shared.astro` (extra `astro`) — эфемериды JPL DE421 через Skyfield и
  расчёт натальной карты (планеты, ASC/MC, дома Плацида, средние лунный узел и
  Лилит). Каталог с `de421.bsp` передаётся в `Ephemeris(directory)`; если файла
  нет, Skyfield скачивает его при создании.
- `astra_shared.db.ledger` (extra `db`) — изменение `users.token` вместе с
  записью `token_transactions`. Баланс меняется атомарным
  `UPDATE ... SET token = token ± amount` (списание — только при достаточном
  балансе) в savepoint, поэтому параллельные операции не теряют друг друга.
  `credit_in_session`/`debit_in_session` работают в транзакции вызывающего
  кода и не коммитят, `credit`/`debit` коммитят сами. Повтор с тем же
  `(reason_type, reference_type, reference_id)` не меняет баланс. `amount`
  должен быть больше нуля.
- `astra_shared.referral` (extra `db`) — бонус 3 + 3 сообщения пригласившему и
  приглашённой за онбординг. `award_onboarding_bonus_in_session` работает в
  транзакции вызывающего кода, `award_onboarding_bonus` коммитит. Обе
  возвращают `OnboardingBonusResult` (начислено ли этим вызовом, новые
  балансы) или `None`, если бонус не положен.
