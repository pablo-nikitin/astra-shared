from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from astra_shared.db.models import TokenTransaction, User, utc_now_naive


class TokenLedgerService:
    @staticmethod
    async def _existing(
        session: AsyncSession,
        user_uuid: str,
        reason_type: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> TokenTransaction | None:
        if reference_type is None or reference_id is None:
            return None
        result = await session.execute(
            select(TokenTransaction).where(
                TokenTransaction.user_uuid == user_uuid,
                TokenTransaction.reason_type == reason_type,
                TokenTransaction.reference_type == reference_type,
                TokenTransaction.reference_id == reference_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _apply(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        direction: str,
        *,
        reason_type: str,
        reference_type: str | None,
        reference_id: str | int | None,
        comment: str | None,
    ) -> tuple[bool, TokenTransaction | None]:
        reference_id = str(reference_id) if reference_id is not None else None
        existing = await TokenLedgerService._existing(session, user_uuid, reason_type, reference_type, reference_id)
        if existing is not None:
            return True, existing

        user = await session.get(User, user_uuid)
        if user is None:
            return False, None
        if direction == "debit" and user.token < amount:
            return False, None

        user.token += amount if direction == "credit" else -amount
        transaction = TokenTransaction(
            user_uuid=user_uuid,
            amount=amount,
            direction=direction,
            reason_type=reason_type,
            reference_type=reference_type,
            reference_id=reference_id,
            comment=comment,
            created_at=utc_now_naive(),
        )
        session.add(transaction)
        try:
            await session.commit()
        except IntegrityError:
            # Гонка на уникальном (user_uuid, reason_type, reference_type,
            # reference_id) — это и есть идемпотентность: конкурентный вызов
            # уже применил операцию, возвращаем его результат вместо повтора.
            await session.rollback()
            existing = await TokenLedgerService._existing(session, user_uuid, reason_type, reference_type, reference_id)
            if existing is not None:
                return True, existing
            raise
        await session.refresh(transaction)
        return True, transaction

    @staticmethod
    async def credit(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        *,
        reason_type: str,
        reference_type: str | None = None,
        reference_id: str | int | None = None,
        comment: str | None = None,
    ) -> tuple[bool, TokenTransaction | None]:
        return await TokenLedgerService._apply(
            session, user_uuid, amount, "credit",
            reason_type=reason_type, reference_type=reference_type, reference_id=reference_id, comment=comment,
        )

    @staticmethod
    async def debit(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        *,
        reason_type: str,
        reference_type: str | None = None,
        reference_id: str | int | None = None,
        comment: str | None = None,
    ) -> tuple[bool, TokenTransaction | None]:
        return await TokenLedgerService._apply(
            session, user_uuid, amount, "debit",
            reason_type=reason_type, reference_type=reference_type, reference_id=reference_id, comment=comment,
        )
