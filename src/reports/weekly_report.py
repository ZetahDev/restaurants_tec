from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import and_, func, select

from src.core.config import get_settings
from src.core.db import session_scope
from src.db.models import ReviewAnalysis, UnifiedReview


@dataclass
class WeeklyMetrics:
    week_start: datetime
    week_end: datetime
    total_reviews: int
    sentiment_distribution: dict[str, float]
    top_rated_locations: list[tuple[int, float]]
    top_problem_locations: list[tuple[int, int]]
    category_frequency: dict[str, int]


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

        category_rows = session.execute(
            select(ReviewAnalysis.categories)
            .join(UnifiedReview, UnifiedReview.id == ReviewAnalysis.unified_review_id)
            .where(and_(UnifiedReview.created_at >= start, UnifiedReview.created_at < end))
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
        top_problem_locations=[(int(loc), int(count)) for loc, count in top_problem_locations],
        category_frequency=category_frequency,
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
        prompt = (
            "Escribe un resumen ejecutivo en un párrafo (max 450 caracteres) para gerencia. "
            "Usa un tono profesional y accionable en español.\n"
            f"Métricas: {asdict(metrics)}"
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "Eres un analista senior de operaciones."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else fallback
    except Exception:
        return fallback


def _render_html(metrics: WeeklyMetrics, summary: str, output_path: Path) -> None:
    html = f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>FeedbackIQ Weekly Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #111; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.2rem; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    .small {{ color: #555; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>FeedbackIQ Weekly Report</h1>
  <p class=\"small\">Window: {metrics.week_start.isoformat()} → {metrics.week_end.isoformat()}</p>

  <h2>Executive Summary</h2>
  <p>{summary}</p>

  <h2>Core Metrics</h2>
  <table>
    <tr><th>Total Reviews</th><td>{metrics.total_reviews}</td></tr>
    <tr><th>Positive %</th><td>{metrics.sentiment_distribution['positive']}</td></tr>
    <tr><th>Negative %</th><td>{metrics.sentiment_distribution['negative']}</td></tr>
    <tr><th>Neutral %</th><td>{metrics.sentiment_distribution['neutral']}</td></tr>
  </table>

  <h2>Top Rated Locations</h2>
  <table>
    <tr><th>Location</th><th>Avg Rating</th></tr>
    {''.join(f'<tr><td>{loc}</td><td>{avg:.2f}</td></tr>' for loc, avg in metrics.top_rated_locations)}
  </table>

  <h2>Top Problem Locations</h2>
  <table>
    <tr><th>Location</th><th>Negative Reviews</th></tr>
    {''.join(f'<tr><td>{loc}</td><td>{count}</td></tr>' for loc, count in metrics.top_problem_locations)}
  </table>

  <h2>Category Frequency</h2>
  <table>
    <tr><th>Category</th><th>Mentions</th></tr>
    {''.join(f'<tr><td>{cat}</td><td>{cnt}</td></tr>' for cat, cnt in metrics.category_frequency.items())}
  </table>
</body>
</html>
    """.strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _render_pdf(metrics: WeeklyMetrics, summary: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "FeedbackIQ Weekly Report")
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Window: {metrics.week_start.isoformat()} -> {metrics.week_end.isoformat()}")
    y -= 25

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Executive Summary")
    y -= 16

    c.setFont("Helvetica", 10)
    for line in [summary[i:i + 95] for i in range(0, len(summary), 95)]:
        c.drawString(40, y, line)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Metrics")
    y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Total reviews: {metrics.total_reviews}")
    y -= 14
    c.drawString(40, y, f"Positive: {metrics.sentiment_distribution['positive']}%")
    y -= 14
    c.drawString(40, y, f"Negative: {metrics.sentiment_distribution['negative']}%")
    y -= 14
    c.drawString(40, y, f"Neutral: {metrics.sentiment_distribution['neutral']}%")
    y -= 20

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Top rated locations")
    y -= 16
    c.setFont("Helvetica", 10)
    for loc, avg in metrics.top_rated_locations:
        c.drawString(40, y, f"- Location {loc}: {avg:.2f}")
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Top problem locations")
    y -= 16
    c.setFont("Helvetica", 10)
    for loc, count in metrics.top_problem_locations:
        c.drawString(40, y, f"- Location {loc}: {count} negative reviews")
        y -= 14

    c.showPage()
    c.save()


def generate_weekly_report(week_start: date | None = None) -> ReportStats:
    metrics = _collect_metrics(week_start=week_start)
    summary = _executive_summary(metrics)

    html_path = Path("docs/weekly_report.html")
    pdf_path = Path("docs/weekly_report.pdf")

    _render_html(metrics=metrics, summary=summary, output_path=html_path)
    _render_pdf(metrics=metrics, summary=summary, output_path=pdf_path)

    return ReportStats(html_path=str(html_path), pdf_path=str(pdf_path))
