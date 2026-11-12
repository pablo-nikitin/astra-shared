"""Цены и подарки, общие для бота и мини-аппа.

`NATAL_CHART_PRICE` — цена расшифровки своей натальной карты в гемах: её
списывает мини-апп, а бот называет в оффере и создаёт платёж на неё.

Подарки акций хранятся в `user_entitlements` (DDL — у astra): бесплатный
доступ к функции в окне `[starts_at, ends_at)`, у поштучного подарка — остаток
`uses_left`. Выдаёт их бот; платная функция до списания гемов проверяет подарок
через `active_entitlement` и, если он поштучный, расходует его
`use_entitlement_in_session` в той же транзакции, что и выдачу результата.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from astra_shared.db.models import UserEntitlement

NATAL_CHART_PRICE = 200

FEATURE_HOROSCOPE_DAY = "horoscope_day"
"""Открытие дня гороскопа по натальной карте без списания. Окно подарка — дни,
которые можно открыть: день покрыт, если его местный полдень попадает в окно."""

FEATURE_DREAM_INTERPRETATION = "dream_interpretation"
"""Расшифровка сна в чате бота без списания сообщения."""


async def active_entitlement(
    session: AsyncSession, user_uuid: str, feature: str, moment: datetime
) -> UserEntitlement | None:
    """Действующий в `moment` (naive UTC) подарок функции; None — подарка нет."""
    return await session.scalar(
        select(UserEntitlement)
        .where(
            UserEntitlement.user_uuid == user_uuid,
            UserEntitlement.feature == feature,
            UserEntitlement.starts_at <= moment,
            or_(UserEntitlement.ends_at.is_(None), UserEntitlement.ends_at > moment),
            or_(UserEntitlement.uses_left.is_(None), UserEntitlement.uses_left > 0),
        )
        .order_by(UserEntitlement.ends_at.asc().nulls_last(), UserEntitlement.id)
        .limit(1)
    )


async def use_entitlement_in_session(session: AsyncSession, entitlement: UserEntitlement) -> bool:
    """Расходует одно использование поштучного подарка, не коммитит.

    Подарок без `uses_left` не расходуется. False — остаток уже израсходован
    параллельным запросом.
    """
    if entitlement.uses_left is None:
        return True
    result = await session.execute(
        update(UserEntitlement)
        .where(UserEntitlement.id == entitlement.id, UserEntitlement.uses_left > 0)
        .values(uses_left=UserEntitlement.uses_left - 1)
        .returning(UserEntitlement.uses_left)
    )
    return result.scalar_one_or_none() is not None
