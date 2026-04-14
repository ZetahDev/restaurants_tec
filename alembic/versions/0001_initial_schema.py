"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-13 21:45:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_surveys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_email", sa.Text(), nullable=True),
        sa.CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_customer_surveys_location_range"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_customer_surveys_rating_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_surveys_created_at", "customer_surveys", ["created_at"], unique=False)

    op.create_table(
        "unified_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_review_id", sa.String(length=255), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("source IN ('api', 'survey')", name="ck_unified_reviews_source"),
        sa.CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_unified_reviews_location_range"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_unified_reviews_rating_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_review_id", name="uq_unified_reviews_source_review"),
    )
    op.create_index("ix_unified_reviews_created_location", "unified_reviews", ["created_at", "location_id"], unique=False)

    op.create_table(
        "review_analysis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("unified_review_id", sa.Integer(), nullable=False),
        sa.Column("sentiment", sa.String(length=16), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=100), nullable=False),
        sa.Column("urgency", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("sentiment IN ('positive', 'negative', 'neutral')", name="ck_review_analysis_sentiment"),
        sa.CheckConstraint("urgency BETWEEN 1 AND 5", name="ck_review_analysis_urgency"),
        sa.ForeignKeyConstraint(["unified_review_id"], ["unified_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unified_review_id"),
    )
    op.create_index(
        "ix_review_analysis_sentiment_urgency_created",
        "review_analysis",
        ["sentiment", "urgency", "created_at"],
        unique=False,
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("severity IN ('CRITICA', 'ALTA', 'MEDIA')", name="ck_alerts_severity"),
        sa.CheckConstraint("location_id BETWEEN 1 AND 15", name="ck_alerts_location_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_code",
            "location_id",
            "window_start",
            "window_end",
            name="uq_alerts_rule_location_window",
        ),
    )
    op.create_index("ix_alerts_created_severity", "alerts", ["created_at", "severity"], unique=False)

    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("dead_letter_events")
    op.drop_index("ix_alerts_created_severity", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_review_analysis_sentiment_urgency_created", table_name="review_analysis")
    op.drop_table("review_analysis")
    op.drop_index("ix_unified_reviews_created_location", table_name="unified_reviews")
    op.drop_table("unified_reviews")
    op.drop_index("ix_customer_surveys_created_at", table_name="customer_surveys")
    op.drop_table("customer_surveys")
