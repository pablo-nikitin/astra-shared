from sqlalchemy.ext.asyncio import AsyncSession

from astra_shared.db.ledger import TokenLedgerService
from astra_shared.db.repository import UserRepository


async def award_onboarding_bonus(session: AsyncSession, referred_user_uuid: str) -> None:
    repository = UserRepository(session)
    user = await repository.get_by_uuid(referred_user_uuid)
    if user is None or not user.referred_by:
        return

    referrer = await repository.get_by_referral_code(user.referred_by)
    if referrer is None or referrer.uuid == user.uuid or not referrer.onboarding:
        return

    await TokenLedgerService.credit(
        session, referrer.uuid, 3,
        reason_type="referral_reward", reference_type="referred_user", reference_id=user.uuid,
        comment="onboarding_referral_bonus",
    )
    await TokenLedgerService.credit(
        session, user.uuid, 3,
        reason_type="referral_signup_bonus", reference_type="referrer", reference_id=referrer.uuid,
        comment="welcome_gift_for_referred_user",
    )
    await repository.increment_referral_count(referrer.uuid)
    await session.commit()
