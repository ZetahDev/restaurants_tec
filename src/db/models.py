from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def json_type() -> JSON | JSONB:
    """Use JSONB on PostgreSQL, JSON otherwise (resolved by migration/runtime dialect)."""
    return JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class CustomerSurvey(Base):
    __tablename__ = "customer_surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comments: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    customer_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_customer_surveys_location_range"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_customer_surveys_rating_range"),
    )


class UnifiedReview(Base):
    __tablename__ = "unified_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_review_id: Mapped[str] = mapped_column(String(255), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    analysis: Mapped[ReviewAnalysis | None] = relationship(
        back_populates="review", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "source_review_id", name="uq_unified_reviews_source_review"),
        CheckConstraint("source IN ('api', 'survey')", name="ck_unified_reviews_source"),
        CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_unified_reviews_location_range"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_unified_reviews_rating_range"),
        Index("ix_unified_reviews_created_location", "created_at", "location_id"),
    )


class ReviewAnalysis(Base):
    __tablename__ = "review_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unified_review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("unified_reviews.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    categories: Mapped[list[str]] = mapped_column(json_type(), nullable=False)
    summary: Mapped[str] = mapped_column(String(100), nullable=False)
    urgency: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    review: Mapped[UnifiedReview] = relationship(back_populates="analysis")

    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('positive', 'negative', 'neutral')",
            name="ck_review_analysis_sentiment",
        ),
        CheckConstraint("urgency BETWEEN 1 AND 5", name="ck_review_analysis_urgency"),
        Index("ix_review_analysis_sentiment_urgency_created", "sentiment", "urgency", "created_at"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("severity IN ('CRITICA', 'ALTA', 'MEDIA')", name="ck_alerts_severity"),
        CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_alerts_location_range"),
        UniqueConstraint(
            "rule_code",
            "location_id",
            "window_start",
            "window_end",
            name="uq_alerts_rule_location_window",
        ),
        Index("ix_alerts_created_severity", "created_at", "severity"),
    )


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type(), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
