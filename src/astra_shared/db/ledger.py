from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from astra_shared.db.models import TokenTransaction, User, utc_now_naive

CREDIT = "credit"
DEBIT = "debit"


@dataclass(frozen=True)
class LedgerResult:
    ok: bool
    transaction_id: int | None = None
    balance: int | None = None


class TokenLedgerService:
    @staticmethod
    async def _existing_id(
        session: AsyncSession,
        user_uuid: str,
        reason_type: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> int | None:
        if reference_type is None or reference_id is None:
            return None
        result = await session.execute(
            select(TokenTransaction.id).where(
                TokenTransaction.user_uuid == user_uuid,
                TokenTransaction.reason_type == reason_type,
                TokenTransaction.reference_type == reference_type,
                TokenTransaction.reference_id == reference_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def apply_in_session(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        direction: str,
        *,
        reason_type: str,
        reference_type: str | None = None,
        reference_id: str | int | None = None,
        comment: str | None = None,
    ) -> LedgerResult:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if direction not in (CREDIT, DEBIT):
            raise ValueError(f"Unsupported direction: {direction}")
        reference_id = str(reference_id) if reference_id is not None else None

        existing_id = await TokenLedgerService._existing_id(
            session, user_uuid, reason_type, reference_type, reference_id
        )
        if existing_id is not None:
            return LedgerResult(ok=True, transaction_id=existing_id)

        now = utc_now_naive()
        new_token = User.token + amount if direction == CREDIT else User.token - amount
        balance_update = (
            update(User)
            .where(User.uuid == user_uuid)
            .values(token=new_token, updated_at=now)
            .returning(User.token)
            .execution_options(synchronize_session="fetch")
        )
        if direction == DEBIT:
            balance_update = balance_update.where(User.token >= amount)

        try:
            async with session.begin_nested():
                balance = (await session.execute(balance_update)).scalar_one_or_none()
                if balance is None:
                    return LedgerResult(ok=False)
                transaction_id = (
                    await session.execute(
                        insert(TokenTransaction)
                        .values(
                            user_uuid=user_uuid,
                            amount=amount,
                            direction=direction,
                            reason_type=reason_type,
                            reference_type=reference_type,
                            reference_id=reference_id,
                            comment=comment,
                            created_at=now,
                        )
                        .returning(TokenTransaction.id)
                    )
                ).scalar_one()
        except IntegrityError:
            # Гонка на уникальном (user_uuid, reason_type, reference_type,
            # reference_id) — это и есть идемпотентность: конкурентный вызов
            # уже применил операцию, возвращаем его результат вместо повтора.
            existing_id = await TokenLedgerService._existing_id(
                session, user_uuid, reason_type, reference_type, reference_id
            )
            if existing_id is not None:
                return LedgerResult(ok=True, transaction_id=existing_id)
            raise
        return LedgerResult(ok=True, transaction_id=transaction_id, balance=balance)

    @staticmethod
    async def credit_in_session(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        *,
        reason_type: str,
        reference_type: str | None = None,
        reference_id: str | int | None = None,
        comment: str | None = None,
    ) -> LedgerResult:
        return await TokenLedgerService.apply_in_session(
            session, user_uuid, amount, CREDIT,
            reason_type=reason_type, reference_type=reference_type, reference_id=reference_id, comment=comment,
        )

    @staticmethod
    async def debit_in_session(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        *,
        reason_type: str,
        reference_type: str | None = None,
        reference_id: str | int | None = None,
        comment: str | None = None,
    ) -> LedgerResult:
        return await TokenLedgerService.apply_in_session(
            session, user_uuid, amount, DEBIT,
            reason_type=reason_type, reference_type=reference_type, reference_id=reference_id, comment=comment,
        )

    @staticmethod
    async def _apply_and_commit(
        session: AsyncSession,
        user_uuid: str,
        amount: int,
        direction: str,
        **kwargs,
    ) -> tuple[bool, TokenTransaction | None]:
        result = await TokenLedgerService.apply_in_session(session, user_uuid, amount, direction, **kwargs)
        if not result.ok:
            await session.rollback()
            return False, None
        await session.commit()
        return True, await session.get(TokenTransaction, result.transaction_id)

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
        return await TokenLedgerService._apply_and_commit(
            session, user_uuid, amount, CREDIT,
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
        return await TokenLedgerService._apply_and_commit(
            session, user_uuid, amount, DEBIT,
            reason_type=reason_type, reference_type=reference_type, reference_id=reference_id, comment=comment,
        )
