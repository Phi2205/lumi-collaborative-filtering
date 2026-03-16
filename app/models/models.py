"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


class UserInteractionEvent(Base):
    __tablename__ = "user_interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    content_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_uie_actor_time", "actor_user_id", "occurred_at"),
        Index("idx_uie_target_time", "target_user_id", "occurred_at"),
        Index("idx_uie_pair_time", "actor_user_id", "target_user_id", "occurred_at"),
        Index("idx_uie_type_time", "event_type", "occurred_at"),
    )


class User(Base):
    """ORM model for the `users` table."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    birthday: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    posts: Mapped[list["Post"]] = relationship(back_populates="user")
    comments: Mapped[list["Comment"]] = relationship(back_populates="user")
    post_likes: Mapped[list["PostLike"]] = relationship(back_populates="user")


class Post(Base):
    """ORM model for the `posts` table (tương ứng Prisma `model posts`)."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", onupdate="NO ACTION"),
        nullable=False,
    )

    content: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Quan hệ – cần các model `User`, `Comment`, `PostLike`, `PostMedia`
    # được định nghĩa ở nơi khác trong codebase để dùng đầy đủ type hints.
    user: Mapped["User"] = relationship(back_populates="posts")

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )

    post_likes: Mapped[list["PostLike"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )

    post_media: Mapped[list["PostMedia"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_posts_created_at", created_at.desc()),
        Index("idx_posts_user", "user_id"),
    )


class Comment(Base):
    """ORM model for the `post_comments` table."""

    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    post: Mapped["Post"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="comments")
    replies: Mapped[list["Comment"]] = relationship(
        back_populates="parent_comment", cascade="all, delete-orphan"
    )
    parent_comment: Mapped[Optional["Comment"]] = relationship(
        back_populates="replies", remote_side=[id]
    )


class PostLike(Base):
    """ORM model for the `post_likes` table."""

    __tablename__ = "post_likes"

    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    post: Mapped["Post"] = relationship(back_populates="post_likes")
    user: Mapped["User"] = relationship(back_populates="post_likes")


class PostMedia(Base):
    """ORM model for the `post_media` table."""

    __tablename__ = "post_media"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    media_url: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    post: Mapped["Post"] = relationship(back_populates="post_media")


class UserPostEngagement(Base):
    """Bảng aggregate engagement giữa user và post (từ events)."""

    __tablename__ = "user_post_engagement"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    post_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    # Engagement score với time-decay
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Số lượng interactions (để debug/analytics)
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Thời gian tương tác gần nhất
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metadata: breakdown theo event_type (JSON)
    # Ví dụ: {"like": 5, "comment": 2, "share": 1}
    event_breakdown: Mapped[dict[str, int]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Timestamp để track khi nào record được cập nhật
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_upe_user_score", "user_id", "engagement_score"),
        Index("idx_upe_post_score", "post_id", "engagement_score"),
        Index("idx_upe_last_interaction", "user_id", "last_interaction_at"),
    )


class UserProfileFeatures(Base):
    """Bảng features của user (tính từ lịch sử interactions)."""

    __tablename__ = "user_profile_features"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)

    # Tổng số interactions user đã thực hiện
    total_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Engagement score trung bình (normalized)
    avg_engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Phân bố theo event_type (JSON)
    # Ví dụ: {"like": 0.4, "comment": 0.3, "share": 0.2, "view_post": 0.1}
    event_type_distribution: Mapped[dict[str, float]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Phân bố theo topic/category (nếu có trong meta của events)
    # Ví dụ: {"tech": 0.5, "sports": 0.3, "entertainment": 0.2}
    topic_distribution: Mapped[dict[str, float]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Thời gian active gần nhất
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Số lượng post user đã tương tác (unique posts)
    unique_posts_interacted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Số lượng users user đã tương tác (unique targets)
    unique_users_interacted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_upf_last_active", "last_active_at"),
        Index("idx_upf_total_interactions", "total_interactions"),
    )


class Friend(Base):
    """ORM model for the `friends` table."""

    __tablename__ = "friends"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    friend_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
