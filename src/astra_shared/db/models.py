import uuid as uuid_lib
from datetime import UTC, date, datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy import Date as SqlDate
from sqlalchemy import Time as SqlTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    # Отражение только тех колонок `users`, что нужны потребителям пакета —
    # DDL и полный набор колонок остаются у astra (docs/architecture.md §1.1).
    __tablename__ = "users"

    uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid_lib.uuid4())
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    birthday: Mapped[date | None] = mapped_column(SqlDate, nullable=True)
    birth_time: Mapped[time | None] = mapped_column(SqlTime, nullable=True)
    token: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    referral_code: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    referred_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    onboarding: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_user_identities_provider_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class TokenTransaction(Base):
    __tablename__ = "token_transactions"
    __table_args__ = (
        UniqueConstraint(
            "user_uuid", "reason_type", "reference_type", "reference_id",
            name="uq_token_transactions_reference",
        ),
        Index("ix_token_transactions_user_created", "user_uuid", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    user_uuid: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.uuid", ondelete="SET NULL"), nullable=True, index=True
    )
    source_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    confirmation_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
