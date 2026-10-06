from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from astra_shared.db.ledger import TokenLedgerService
from astra_shared.db.repository import UserRepository

ONBOARDING_REFERRAL_BONUS = 3
REFERRAL_REWARD_REASON = "referral_reward"
REFERRAL_SIGNUP_BONUS_REASON = "referral_signup_bonus"


@dataclass(frozen=True)
class OnboardingBonusResult:
    referred_user_uuid: str
    referrer_uuid: str
    referrer_credited: bool
    invitee_credited: bool
    referrer_balance: int | None
    invitee_balance: int | None


async def award_onboarding_bonus_in_session(
    session: AsyncSession, referred_user_uuid: str
) -> OnboardingBonusResult | None:
    # Онбординг приглашённой (users.onboarding) здесь не проверяется: astra
    # проверяет его сама перед вызовом, а astra-app начисляет бонус при первом
    # сохранении имени в профиле. При онбординге v2 бота доступ к общению
    # открывается только после оплаты, поэтому через astra-app приглашённая
    # получает бонус, не заплатив в боте. Повторно бонус не начислится —
    # ключи идемпотентности ledger общие.
    repository = UserRepository(session)
    user = await repository.get_by_uuid(referred_user_uuid)
    if user is None or not user.referred_by:
        return None

    referrer = await repository.get_by_referral_code(user.referred_by)
    if referrer is None or referrer.uuid == user.uuid or not referrer.onboarding:
        return None

    referrer_result = await TokenLedgerService.credit_in_session(
        session, referrer.uuid, ONBOARDING_REFERRAL_BONUS,
        reason_type=REFERRAL_REWARD_REASON, reference_type="referred_user", reference_id=user.uuid,
        comment="onboarding_referral_bonus",
    )
    invitee_result = await TokenLedgerService.credit_in_session(
        session, user.uuid, ONBOARDING_REFERRAL_BONUS,
        reason_type=REFERRAL_SIGNUP_BONUS_REASON, reference_type="referrer", reference_id=referrer.uuid,
        comment="welcome_gift_for_referred_user",
    )
    return OnboardingBonusResult(
        referred_user_uuid=user.uuid,
        referrer_uuid=referrer.uuid,
        referrer_credited=referrer_result.ok and referrer_result.balance is not None,
        invitee_credited=invitee_result.ok and invitee_result.balance is not None,
        referrer_balance=referrer_result.balance,
        invitee_balance=invitee_result.balance,
    )


async def award_onboarding_bonus(session: AsyncSession, referred_user_uuid: str) -> OnboardingBonusResult | None:
    result = await award_onboarding_bonus_in_session(session, referred_user_uuid)
    await session.commit()
    return result
