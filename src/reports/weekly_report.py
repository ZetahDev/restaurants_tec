from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from sqlalchemy import and_, func, select

from src.core.config import get_settings
from src.core.db import session_scope
from src.db.models import ReviewAnalysis, UnifiedReview
from src.reports.prompts import REPORT_SUMMARY_SYSTEM_PROMPT, build_report_summary_user_prompt
from src.reports.renderers import _render_html, _render_pdf


@dataclass
class WeeklyMetrics:
    week_start: datetime
    week_end: datetime
    total_reviews: int
    sentiment_distribution: dict[str, float]
    top_rated_locations: list[tuple[int, float]]
    lowest_rated_locations: list[tuple[int, float]]
    top_problem_locations: list[tuple[int, int]]
    category_frequency: dict[str, int]
    comment_samples: list[dict[str, Any]]


@dataclass
class ReportStats:
    html_path: str
    pdf_path: str


def _window(week_start: date | None = None) -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)
    if week_start is None:
        week_end = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start_dt = week_end - timedelta(days=7)
        return week_start_dt, week_end

    week_start_dt = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    return week_start_dt, week_start_dt + timedelta(days=7)


def _collect_metrics(week_start: date | None = None) -> WeeklyMetrics:
    start, end = _window(week_start=week_start)

    with session_scope() as session:
        total_reviews = session.scalar(
            select(func.count(UnifiedReview.id)).where(
                and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end)
            )
        ) or 0

        sentiment_rows = session.execute(
            select(ReviewAnalysis.sentiment, func.count(ReviewAnalysis.id))
            .join(UnifiedReview, UnifiedReview.id == ReviewAnalysis.unified_review_id)
            .where(and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end))
            .group_by(ReviewAnalysis.sentiment)
        ).all()

        sentiment_distribution: dict[str, float] = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        total_sentiment = sum(count for _, count in sentiment_rows)
        if total_sentiment:
            for sentiment, count in sentiment_rows:
                sentiment_distribution[sentiment] = round((count / total_sentiment) * 100, 2)

        top_rated_locations = session.execute(
            select(UnifiedReview.location_id, func.avg(UnifiedReview.rating).label("avg_rating"))
            .where(and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end))
            .group_by(UnifiedReview.location_id)
            .order_by(func.avg(UnifiedReview.rating).desc())
            .limit(3)
        ).all()

        top_problem_locations = session.execute(
            select(UnifiedReview.location_id, func.count(ReviewAnalysis.id).label("negative_count"))
            .join(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
            .where(
                and_(
                    UnifiedReview.created_at >= start,
                    UnifiedReview.created_at < end,
                    ReviewAnalysis.sentiment == "negative",
                )
            )
            .group_by(UnifiedReview.location_id)
            .order_by(func.count(ReviewAnalysis.id).desc())
            .limit(3)
        ).all()

        lowest_rated_locations = session.execute(
            select(UnifiedReview.location_id, func.avg(UnifiedReview.rating).label("avg_rating"))
            .where(and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end))
            .group_by(UnifiedReview.location_id)
            .order_by(func.avg(UnifiedReview.rating).asc())
            .limit(3)
        ).all()

        category_rows = session.execute(
            select(ReviewAnalysis.categories)
            .join(UnifiedReview, UnifiedReview.id == ReviewAnalysis.unified_review_id)
            .where(and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end))
        ).all()

        sample_rows = session.execute(
            select(
                UnifiedReview.location_id,
                UnifiedReview.rating,
                UnifiedReview.text,
                UnifiedReview.created_at,
                ReviewAnalysis.sentiment,
                ReviewAnalysis.urgency,
                ReviewAnalysis.summary,
            )
            .join(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
            .where(
                and_(
                    UnifiedReview.created_at >= start,
                    UnifiedReview.created_at < end,
                    ReviewAnalysis.sentiment.in_(["negative", "neutral"]),
                )
            )
            .order_by(ReviewAnalysis.urgency.desc(), UnifiedReview.created_at.desc())
            .limit(8)
        ).all()

    category_frequency: dict[str, int] = {}
    for (categories,) in category_rows:
        for category in categories:
            category_frequency[category] = category_frequency.get(category, 0) + 1
    category_frequency = dict(sorted(category_frequency.items(), key=lambda item: item[1], reverse=True))

    return WeeklyMetrics(
        week_start=start,
        week_end=end,
        total_reviews=int(total_reviews),
        sentiment_distribution=sentiment_distribution,
        top_rated_locations=[(int(loc), float(avg)) for loc, avg in top_rated_locations],
        lowest_rated_locations=[(int(loc), float(avg)) for loc, avg in lowest_rated_locations],
        top_problem_locations=[(int(loc), int(count)) for loc, count in top_problem_locations],
        category_frequency=category_frequency,
        comment_samples=[
            {
                "location_id": int(loc),
                "rating": int(rating),
                "text": str(text),
                "created_at": created_at.isoformat(),
                "sentiment": str(sentiment),
                "urgency": int(urgency),
                "summary": str(summary),
            }
            for loc, rating, text, created_at, sentiment, urgency, summary in sample_rows
        ],
    )


def _executive_summary(metrics: WeeklyMetrics) -> str:
    settings = get_settings()
    fallback = (
        f"Se procesaron {metrics.total_reviews} reseñas en la semana. "
        f"Sentimiento positivo {metrics.sentiment_distribution['positive']}%, "
        f"negativo {metrics.sentiment_distribution['negative']}%."
    )

    if not settings.openai_api_key:
        return fallback

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        prompt = build_report_summary_user_prompt(asdict(metrics))
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": REPORT_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else fallback
    except Exception:
        return fallback


def generate_weekly_report(week_start: date | None = None) -> ReportStats:
    settings = get_settings()
    metrics = _collect_metrics(week_start=week_start)
    summary = _executive_summary(metrics)

    html_path = Path(settings.report_html_path)
    pdf_path = Path(settings.report_pdf_path)

    _render_html(metrics=metrics, summary=summary, output_path=html_path)
    _render_pdf(metrics=metrics, summary=summary, output_path=pdf_path)

    return ReportStats(html_path=str(html_path), pdf_path=str(pdf_path))

