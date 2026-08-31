import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from astra_shared.db.models import User, UserIdentity, utc_now_naive


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_uuid(self, user_uuid: str) -> User | None:
        return await self._session.get(User, user_uuid)

    async def get_by_referral_code(self, referral_code: str) -> User | None:
        result = await self._session.execute(select(User).where(User.referral_code == referral_code))
        return result.scalar_one_or_none()

    async def increment_referral_count(self, user_uuid: str) -> None:
        user = await self.get_by_uuid(user_uuid)
        if user is not None:
            user.referral_count += 1

    async def _get_by_identity(self, provider: str, external_id: str) -> User | None:
        result = await self._session.execute(
            select(User)
            .join(UserIdentity, UserIdentity.user_uuid == User.uuid)
            .where(UserIdentity.provider == provider, UserIdentity.external_id == str(external_id))
        )
        return result.scalar_one_or_none()

    async def get_or_create_by_identity(self, provider: str, external_id: str) -> tuple[User, bool]:
        existing = await self._get_by_identity(provider, external_id)
        if existing is not None:
            return existing, False

        user = User(uuid=str(uuid_lib.uuid4()), updated_at=utc_now_naive())
        identity = UserIdentity(user_uuid=user.uuid, provider=provider, external_id=str(external_id))
        self._session.add_all([user, identity])
        try:
            await self._session.commit()
        except IntegrityError:
            # Гонка на уникальном (provider, external_id) — конкурентный запрос
            # уже создал identity первым, подхватываем его результат.
            await self._session.rollback()
            existing = await self._get_by_identity(provider, external_id)
            if existing is not None:
                return existing, False
            raise
        await self._session.refresh(user)
        return user, True
