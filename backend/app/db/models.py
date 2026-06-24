"""SQLAlchemy ORM models for PS Price."""

from __future__ import annotations

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("product_id", "locale", name="uq_games_product_locale"),
        Index("idx_games_discount", "discount_percent"),
        Index("idx_games_name_lower", func.lower("name")),
        Index("idx_games_popularity", "popularity_rank"),
        Index("idx_games_tracked_checked", "is_tracked", "last_checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    store_url: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str | None] = mapped_column(Text)
    current_price_cents: Mapped[int | None] = mapped_column(Integer)
    current_price_formatted: Mapped[str | None] = mapped_column(Text)
    original_price_cents: Mapped[int | None] = mapped_column(Integer)
    original_price_formatted: Mapped[str | None] = mapped_column(Text)
    discount_text: Mapped[str | None] = mapped_column(Text)
    availability: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    price_source: Mapped[str | None] = mapped_column(Text)
    sale_end_at: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    raw_source_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    platforms: Mapped[str | None] = mapped_column(Text)
    discount_percent: Mapped[int | None] = mapped_column(Integer)
    is_tracked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalog_synced_at: Mapped[str | None] = mapped_column(Text)
    description_short: Mapped[str | None] = mapped_column(Text)
    description_long: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[str | None] = mapped_column(Text)
    genres: Mapped[str | None] = mapped_column(Text)
    features: Mapped[str | None] = mapped_column(Text)
    rating_average: Mapped[float | None] = mapped_column(Float)
    rating_count: Mapped[int | None] = mapped_column(Integer)
    content_rating: Mapped[str | None] = mapped_column(Text)
    screenshots: Mapped[str | None] = mapped_column(Text)
    edition: Mapped[str | None] = mapped_column(Text)
    popularity_rank: Mapped[int | None] = mapped_column(Integer)

    price_history: Mapped[list[PriceHistory]] = relationship(back_populates="game")
    watches: Mapped[list[Watch]] = relationship(back_populates="game")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("idx_price_history_game_checked", "game_id", "checked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    original_price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(Text)
    price_formatted: Mapped[str | None] = mapped_column(Text)
    original_price_formatted: Mapped[str | None] = mapped_column(Text)
    discount_text: Mapped[str | None] = mapped_column(Text)
    raw_source_hash: Mapped[str | None] = mapped_column(Text)

    game: Mapped[Game] = relationship(back_populates="price_history")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    email_verified_at: Mapped[str | None] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preferred_theme_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    notification_emails: Mapped[list[UserNotificationEmail]] = relationship(back_populates="user")
    sessions: Mapped[list[RefreshSession]] = relationship(back_populates="user")
    passkeys: Mapped[list[PasskeyCredential]] = relationship(back_populates="user")


class UserNotificationEmail(Base):
    __tablename__ = "user_notification_emails"
    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_user_notification_emails_user_email"),
        Index("idx_user_emails_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="notification_emails")


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (Index("idx_watches_game_enabled", "game_id", "enabled"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    target_price_cents: Mapped[int | None] = mapped_column(Integer)
    notify_on_any_drop: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_notified_price_cents: Mapped[int | None] = mapped_column(Integer)
    last_notified_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    notification_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_notification_emails.id", ondelete="SET NULL")
    )
    theme_id: Mapped[str | None] = mapped_column(Text)
    min_drop_cents: Mapped[int | None] = mapped_column(Integer)
    min_drop_percent: Mapped[int | None] = mapped_column(Integer)

    game: Mapped[Game] = relationship(back_populates="watches")


class CatalogMeta(Base):
    __tablename__ = "catalog_meta"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watch_id: Mapped[int | None] = mapped_column(ForeignKey("watches.id", ondelete="SET NULL"))
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class RefreshSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("idx_sessions_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="sessions")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"
    __table_args__ = (Index("idx_passkeys_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(Text)
    friendly_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="passkeys")


class WebAuthnChallenge(Base):
    __tablename__ = "webauthn_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    challenge: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class UserLibrary(Base):
    __tablename__ = "user_library"
    __table_args__ = (Index("idx_user_library_game", "game_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
