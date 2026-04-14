from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from textwrap import wrap
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
    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_start": metrics.week_start.isoformat(),
        "week_end": metrics.week_end.isoformat(),
        "summary": summary,
        "total_reviews": metrics.total_reviews,
        "sentiment_distribution": metrics.sentiment_distribution,
        "top_rated_locations": [
            {"location_id": loc, "avg_rating": round(avg, 2)}
            for loc, avg in metrics.top_rated_locations
        ],
        "lowest_rated_locations": [
            {"location_id": loc, "avg_rating": round(avg, 2)}
            for loc, avg in metrics.lowest_rated_locations
        ],
        "top_problem_locations": [
            {"location_id": loc, "negative_count": count}
            for loc, count in metrics.top_problem_locations
        ],
        "category_frequency": metrics.category_frequency,
        "comment_samples": metrics.comment_samples,
    }
    report_payload_json = json.dumps(report_payload, ensure_ascii=False)

    html = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FeedbackIQ | Reporte Semanal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f6f3ee;
      --surface: #fffaf2;
      --ink: #1f2427;
      --muted: #596167;
      --line: #d9d1c5;
      --accent: #0b7a75;
      --accent-soft: #d8f0ed;
      --good: #2f9e44;
      --warn: #d97706;
      --risk: #b42318;
      --radius: 16px;
      --shadow: 0 16px 32px rgba(37, 43, 46, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background:
        radial-gradient(circle at 85% -10%, rgba(11, 122, 117, 0.2), transparent 40%),
        radial-gradient(circle at -20% 10%, rgba(183, 35, 24, 0.1), transparent 35%),
        var(--bg);
      color: var(--ink);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      min-height: 100vh;
      line-height: 1.4;
    }}

    .page {{
      width: min(1200px, 94vw);
      margin: 0 auto;
      padding: 1.2rem 0 2rem;
    }}

    .workspace-header {{
      padding: 1.1rem 0;
      border-bottom: 1px solid var(--line);
      margin-bottom: 1.4rem;
      animation: fadeUp 520ms ease-out both;
    }}

    .workspace-header-top {{
      display: flex;
      gap: 0.8rem;
      justify-content: space-between;
      align-items: baseline;
      flex-wrap: wrap;
    }}

    .brand {{
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.4rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}

    .timestamp {{
      color: var(--muted);
      font-size: 0.9rem;
    }}

    h1 {{
      font-family: "Space Grotesk", sans-serif;
      font-weight: 700;
      font-size: clamp(1.8rem, 3vw, 2.7rem);
      margin: 0.5rem 0 0.35rem;
      max-width: 14ch;
      line-height: 1.05;
    }}

    .subtitle {{
      color: var(--muted);
      margin: 0;
      max-width: 66ch;
    }}

    .toolbar {{
      margin-top: 1rem;
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      border: 1px solid transparent;
      padding: 0.55rem 1rem;
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: transform 180ms ease, box-shadow 180ms ease, background-color 180ms ease;
    }}

    .btn:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}

    .btn-primary {{
      background: var(--ink);
      color: #fff;
      box-shadow: var(--shadow);
    }}

    .btn-secondary {{
      background: transparent;
      color: var(--ink);
      border-color: var(--line);
    }}

    .btn:hover {{
      transform: translateY(-1px);
    }}

    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 1.25rem;
      align-items: start;
    }}

    .main {{
      display: grid;
      gap: 1rem;
    }}

    .kpi-strip {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      background: var(--surface);
    }}

    .kpi {{
      padding: 1rem;
      min-height: 104px;
      border-right: 1px solid var(--line);
    }}

    .kpi:last-child {{
      border-right: none;
    }}

    .kpi-label {{
      color: var(--muted);
      font-size: 0.85rem;
      letter-spacing: 0.01em;
      margin-bottom: 0.3rem;
    }}

    .kpi-value {{
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(1.4rem, 2.4vw, 2rem);
      font-weight: 700;
    }}

    .kpi-hint {{
      margin-top: 0.2rem;
      font-size: 0.82rem;
      color: var(--muted);
    }}

    .panel {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 1rem;
    }}

    .panel h2 {{
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }}

    .panel-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-bottom: 0.8rem;
    }}

    .split {{
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 1rem;
      align-items: center;
    }}

    .sentiment-ring-wrap {{
      display: grid;
      place-items: center;
      min-height: 220px;
    }}

    .sentiment-ring {{
      --positive: 0;
      --negative: 0;
      --neutral: 100;
      width: 210px;
      aspect-ratio: 1 / 1;
      border-radius: 50%;
      background: conic-gradient(
        var(--good) 0 calc(var(--positive) * 1%),
        var(--risk) calc(var(--positive) * 1%) calc((var(--positive) + var(--negative)) * 1%),
        var(--warn) calc((var(--positive) + var(--negative)) * 1%) 100%
      );
      display: grid;
      place-items: center;
      position: relative;
      transition: transform 280ms ease;
    }}

    .sentiment-ring::after {{
      content: "";
      width: 64%;
      aspect-ratio: 1 / 1;
      border-radius: 50%;
      background: var(--surface);
      box-shadow: inset 0 0 0 1px var(--line);
    }}

    .sentiment-ring:hover {{
      transform: rotate(-5deg) scale(1.02);
    }}

    .ring-center {{
      position: absolute;
      text-align: center;
      display: grid;
      gap: 0.1rem;
      z-index: 1;
    }}

    .ring-center strong {{
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.6rem;
      line-height: 1;
    }}

    .ring-center span {{
      color: var(--muted);
      font-size: 0.82rem;
    }}

    .legend {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0.45rem;
    }}

    .legend li {{
      display: grid;
      grid-template-columns: 14px 1fr auto;
      gap: 0.6rem;
      align-items: center;
      font-size: 0.92rem;
      padding-bottom: 0.35rem;
      border-bottom: 1px dashed var(--line);
    }}

    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
    }}

    .table-wrap {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}

    th {{
      color: var(--muted);
      font-weight: 600;
      text-align: left;
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--line);
    }}

    td {{
      padding: 0.58rem 0;
      border-bottom: 1px solid rgba(217, 209, 197, 0.7);
      transition: transform 150ms ease, color 150ms ease;
    }}

    tbody tr:hover td {{
      transform: translateX(3px);
      color: #000;
    }}

    .two-columns {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}

    .controls {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.88rem;
    }}

    .controls input,
    .controls select {{
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 0.36rem 0.5rem;
      font: inherit;
      color: var(--ink);
    }}

    .category-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0.58rem;
    }}

    .category-item {{
      display: grid;
      grid-template-columns: 120px 1fr auto;
      align-items: center;
      gap: 0.75rem;
      font-size: 0.9rem;
    }}

    .comment-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.75rem;
    }}

    .comment-item {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.75rem;
      background: #fffdf8;
    }}

    .comment-head {{
      display: flex;
      gap: 0.5rem;
      align-items: center;
      justify-content: space-between;
      font-size: 0.82rem;
      color: var(--muted);
      margin-bottom: 0.4rem;
      flex-wrap: wrap;
    }}

    .comment-pill {{
      border-radius: 999px;
      padding: 0.12rem 0.45rem;
      font-weight: 600;
      font-size: 0.75rem;
      border: 1px solid var(--line);
      color: var(--ink);
      background: #f5efe4;
    }}

    .comment-text {{
      margin: 0;
      font-size: 0.92rem;
      color: #21282c;
    }}

    .bar-track {{
      position: relative;
      height: 10px;
      border-radius: 999px;
      background: #ebe5db;
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), #54a6a2);
      transform-origin: left center;
      transition: width 240ms ease;
    }}

    .sidebar {{
      position: sticky;
      top: 1rem;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: linear-gradient(180deg, #fffdf9 0%, #fff7eb 100%);
      padding: 1rem;
      box-shadow: var(--shadow);
    }}

    .sidebar h2 {{
      margin: 0 0 0.5rem;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.05rem;
    }}

    .sidebar p {{
      margin: 0;
      color: #2f363a;
      font-size: 0.95rem;
    }}

    .sidebar h3 {{
      margin: 1rem 0 0.45rem;
      font-size: 0.9rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}

    .actions-list {{
      margin: 0;
      padding-left: 1.1rem;
      display: grid;
      gap: 0.46rem;
      font-size: 0.9rem;
    }}

    .footer {{
      margin-top: 1rem;
      color: var(--muted);
      font-size: 0.82rem;
    }}

    .reveal {{
      opacity: 0;
      transform: translateY(14px);
      animation: fadeUp 480ms ease-out forwards;
    }}

    .delay-1 {{ animation-delay: 60ms; }}
    .delay-2 {{ animation-delay: 120ms; }}
    .delay-3 {{ animation-delay: 180ms; }}
    .delay-4 {{ animation-delay: 240ms; }}

    @keyframes fadeUp {{
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}

    @media (max-width: 1024px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}

      .sidebar {{
        position: static;
      }}
    }}

    @media (max-width: 760px) {{
      .kpi-strip {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .kpi:nth-child(2n) {{
        border-right: none;
      }}

      .kpi:nth-child(-n+2) {{
        border-bottom: 1px solid var(--line);
      }}

      .split {{
        grid-template-columns: 1fr;
      }}

      .two-columns {{
        grid-template-columns: 1fr;
      }}

      .category-item {{
        grid-template-columns: 92px 1fr auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="workspace-header">
      <div class="workspace-header-top">
        <div class="brand">BrewMaster | FeedbackIQ Ops</div>
        <div class="timestamp" id="generatedAt">Actualizado: --</div>
      </div>
      <h1>Reporte semanal de reseñas y riesgo operativo</h1>
      <p class="subtitle" id="windowLabel">Ventana de análisis: --</p>
      <div class="toolbar">
        <a class="btn btn-primary" href="./weekly_report.pdf" target="_blank" rel="noopener noreferrer">Descargar PDF</a>
        <button class="btn btn-secondary" id="rerenderBtn" type="button">Reanimar vista</button>
      </div>
    </header>

    <div class="layout">
      <main class="main">
        <section class="kpi-strip reveal delay-1" aria-label="KPI principales">
          <div class="kpi">
            <div class="kpi-label">Total reseñas semana</div>
            <div class="kpi-value" id="kpiTotalReviews">0</div>
            <div class="kpi-hint">Consolidado API + encuestas</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Riesgo negativo</div>
            <div class="kpi-value" id="kpiNegativeRate">0%</div>
            <div class="kpi-hint">Participación de sentimiento negativo</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Rendimiento positivo</div>
            <div class="kpi-value" id="kpiPositiveRate">0%</div>
            <div class="kpi-hint">Share de experiencias favorables</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Intensidad de fricción</div>
            <div class="kpi-value" id="kpiFriction">0</div>
            <div class="kpi-hint">Negativas vs positivas (ratio)</div>
          </div>
        </section>

        <section class="panel reveal delay-2">
          <div class="panel-head">
            <h2>Distribución de sentimiento</h2>
          </div>
          <div class="split">
            <div class="sentiment-ring-wrap">
              <div class="sentiment-ring" id="sentimentRing">
                <div class="ring-center">
                  <strong id="ringRisk">0%</strong>
                  <span>Riesgo negativo</span>
                </div>
              </div>
            </div>
            <ul class="legend" id="sentimentLegend"></ul>
          </div>
        </section>

        <section class="panel reveal delay-3">
          <div class="panel-head">
            <h2>Top 3 por desempeño (rating promedio)</h2>
          </div>
          <div class="two-columns">
            <div class="table-wrap">
              <table aria-label="Top ubicaciones por rating">
                <thead>
                  <tr>
                    <th>Top rating</th>
                    <th>Promedio</th>
                  </tr>
                </thead>
                <tbody id="topRatedBody"></tbody>
              </table>
            </div>
            <div class="table-wrap">
              <table aria-label="Ubicaciones con menor rating">
                <thead>
                  <tr>
                    <th>Top más bajas</th>
                    <th>Promedio</th>
                  </tr>
                </thead>
                <tbody id="lowestRatedBody"></tbody>
              </table>
            </div>
          </div>
        </section>

        <section class="panel reveal delay-4">
          <div class="panel-head">
            <h2>Top 3 locales con más problemas</h2>
          </div>
          <div class="table-wrap">
              <table aria-label="Ubicaciones con más negativas">
                <thead>
                  <tr>
                    <th>Mayor fricción</th>
                    <th>Negativas</th>
                  </tr>
                </thead>
                <tbody id="topProblemBody"></tbody>
              </table>
          </div>
        </section>

        <section class="panel reveal delay-4">
          <div class="panel-head">
            <h2>Categorías con mayor impacto</h2>
            <div class="controls">
              <label for="minMentions">Mínimo menciones</label>
              <input id="minMentions" type="range" min="1" max="1" value="1" />
              <span id="minMentionsValue">1</span>
              <label for="sortMode">Orden</label>
              <select id="sortMode">
                <option value="desc">Más mencionadas</option>
                <option value="asc">Menos mencionadas</option>
                <option value="alpha">A-Z</option>
              </select>
            </div>
          </div>
          <ul class="category-list" id="categoryList"></ul>
        </section>

        <section class="panel reveal delay-4">
          <div class="panel-head">
            <h2>Voz del cliente (muestras negativas y neutrales)</h2>
          </div>
          <ul class="comment-list" id="commentList"></ul>
        </section>
      </main>

      <aside class="sidebar reveal delay-2">
        <h2>Resumen ejecutivo</h2>
        <p id="summaryText"></p>

        <h3>Acciones recomendadas</h3>
        <ol class="actions-list" id="actionsList"></ol>
      </aside>
    </div>

    <footer class="footer" id="footerMeta"></footer>
  </div>

  <script id="report-data" type="application/json">{report_payload_json}</script>
  <script>
    (() => {{
      const state = {{
        status: "booting",
        data: null,
        error: null,
      }};

      const fmtPercent = (value) => `${{Number(value ?? 0).toFixed(2)}}%`;

      const byId = (id) => document.getElementById(id);
      const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

      function transition(event, payload = null) {{
        if (state.status === "booting" && event === "DATA_OK") {{
          state.status = "ready";
          state.data = payload;
          render();
          return;
        }}

        if (event === "FAIL") {{
          state.status = "error";
          state.error = payload || "No se pudo construir el reporte.";
          renderError();
        }}
      }}

      function parseData() {{
        const raw = byId("report-data");
        if (!raw) {{
          transition("FAIL", "No hay payload del reporte.");
          return;
        }}

        try {{
          const parsed = JSON.parse(raw.textContent || "{{}}");
          transition("DATA_OK", parsed);
        }} catch (error) {{
          transition("FAIL", String(error));
        }}
      }}

      function renderHeader(data) {{
        byId("generatedAt").textContent = `Actualizado: ${{new Date(data.generated_at).toLocaleString("es-CO", {{ hour12: false }})}}`;
        byId("windowLabel").textContent = `Ventana: ${{new Date(data.week_start).toLocaleString("es-CO", {{ hour12: false }})}} -> ${{new Date(data.week_end).toLocaleString("es-CO", {{ hour12: false }})}}`;
      }}

      function renderKpi(data) {{
        const sentiment = data.sentiment_distribution || {{}};
        const positive = Number(sentiment.positive || 0);
        const negative = Number(sentiment.negative || 0);

        byId("kpiTotalReviews").textContent = String(data.total_reviews || 0);
        byId("kpiNegativeRate").textContent = fmtPercent(negative);
        byId("kpiPositiveRate").textContent = fmtPercent(positive);

        const friction = positive > 0 ? (negative / positive) : negative;
        byId("kpiFriction").textContent = `${{friction.toFixed(2)}}x`;
      }}

      function renderSentiment(data) {{
        const sentiment = data.sentiment_distribution || {{}};
        const positive = clamp(Number(sentiment.positive || 0), 0, 100);
        const negative = clamp(Number(sentiment.negative || 0), 0, 100);
        let neutral = clamp(Number(sentiment.neutral || 0), 0, 100);
        const total = positive + negative + neutral;

        if (total !== 100 && total > 0) {{
          neutral = clamp(100 - positive - negative, 0, 100);
        }}

        const ring = byId("sentimentRing");
        ring.style.setProperty("--positive", positive.toFixed(2));
        ring.style.setProperty("--negative", negative.toFixed(2));
        ring.style.setProperty("--neutral", neutral.toFixed(2));
        byId("ringRisk").textContent = fmtPercent(negative);

        const legend = byId("sentimentLegend");
        const entries = [
          ["Positivo", positive, "var(--good)"],
          ["Negativo", negative, "var(--risk)"],
          ["Neutral", neutral, "var(--warn)"],
        ];

        legend.innerHTML = entries.map(([label, value, color]) => `
          <li>
            <span class="legend-dot" style="background:${{color}};"></span>
            <span>${{label}}</span>
            <strong>${{fmtPercent(value)}}</strong>
          </li>
        `).join("");
      }}

      function tableRows(entries, leftKey, rightKey, formatter) {{
        if (!entries || entries.length === 0) {{
          return `<tr><td colspan="2">Sin datos para esta ventana.</td></tr>`;
        }}

        return entries.map((entry) => `
          <tr>
            <td>Location ${{entry[leftKey]}}</td>
            <td>${{formatter(entry[rightKey])}}</td>
          </tr>
        `).join("");
      }}

      function renderTables(data) {{
        const rated = Array.isArray(data.top_rated_locations) ? data.top_rated_locations : [];
        const lowest = Array.isArray(data.lowest_rated_locations) ? data.lowest_rated_locations : [];
        const problem = Array.isArray(data.top_problem_locations) ? data.top_problem_locations : [];

        byId("topRatedBody").innerHTML = tableRows(
          rated,
          "location_id",
          "avg_rating",
          (value) => Number(value).toFixed(2),
        );
        byId("lowestRatedBody").innerHTML = tableRows(
          lowest,
          "location_id",
          "avg_rating",
          (value) => Number(value).toFixed(2),
        );
        byId("topProblemBody").innerHTML = tableRows(
          problem,
          "location_id",
          "negative_count",
          (value) => String(value),
        );
      }}

      function buildActions(data) {{
        const sentiment = data.sentiment_distribution || {{}};
        const negative = Number(sentiment.negative || 0);
        const topProblem = (data.top_problem_locations || [])[0];
        const topRated = (data.top_rated_locations || [])[0];
        const actions = [];

        if (negative >= 35) {{
          actions.push("Escalar revisión operativa diaria para ubicaciones con mayor fricción.");
        }} else {{
          actions.push("Mantener monitoreo semanal y revisar picos negativos por turno.");
        }}

        if (topProblem) {{
          actions.push(`Priorizar plan de recuperación para Location ${{topProblem.location_id}} (mayor volumen negativo).`);
        }}

        if (topRated) {{
          actions.push(`Replicar prácticas de Location ${{topRated.location_id}} en locales con desempeño inferior.`);
        }}

        if (actions.length < 3) {{
          actions.push("Validar cumplimiento de protocolos de servicio y tiempos de atención.");
        }}

        return actions.slice(0, 4);
      }}

      function renderSidebar(data) {{
        byId("summaryText").textContent = data.summary || "Sin resumen disponible.";
        const actions = buildActions(data);
        byId("actionsList").innerHTML = actions.map((action) => `<li>${{action}}</li>`).join("");
      }}

      function renderCategoryControls(data) {{
        const values = Object.values(data.category_frequency || {{}}).map((v) => Number(v));
        const maxMentions = values.length ? Math.max(...values) : 1;
        const minMentionsInput = byId("minMentions");
        minMentionsInput.max = String(Math.max(1, maxMentions));
        minMentionsInput.value = minMentionsInput.value || "1";
        byId("minMentionsValue").textContent = minMentionsInput.value;
      }}

      function renderCategories(data) {{
        const categoryList = byId("categoryList");
        const minMentions = Number(byId("minMentions").value || 1);
        const sortMode = byId("sortMode").value;
        const rows = Object.entries(data.category_frequency || {{}})
          .map(([name, mentions]) => ({{ name, mentions: Number(mentions) }}))
          .filter((row) => row.mentions >= minMentions);

        if (sortMode === "asc") {{
          rows.sort((a, b) => a.mentions - b.mentions);
        }} else if (sortMode === "alpha") {{
          rows.sort((a, b) => a.name.localeCompare(b.name, "es"));
        }} else {{
          rows.sort((a, b) => b.mentions - a.mentions);
        }}

        const maxMentions = rows.length ? Math.max(...rows.map((row) => row.mentions)) : 1;
        if (rows.length === 0) {{
          categoryList.innerHTML = `<li>No hay categorías con ese filtro.</li>`;
          return;
        }}

        categoryList.innerHTML = rows.map((row) => {{
          const width = ((row.mentions / maxMentions) * 100).toFixed(2);
          return `
            <li class="category-item">
              <span>${{row.name}}</span>
              <div class="bar-track"><div class="bar-fill" style="width:${{width}}%;"></div></div>
              <strong>${{row.mentions}}</strong>
            </li>
          `;
        }}).join("");
      }}

      function renderCommentSamples(data) {{
        const commentList = byId("commentList");
        const rows = Array.isArray(data.comment_samples) ? data.comment_samples : [];

        if (!rows.length) {{
          commentList.innerHTML = `<li class="comment-item">No hay comentarios destacados en esta ventana.</li>`;
          return;
        }}

        commentList.innerHTML = rows.map((row) => {{
          const sentiment = String(row.sentiment || "").toUpperCase();
          const createdAt = row.created_at
            ? new Date(row.created_at).toLocaleString("es-CO", {{ hour12: false }})
            : "--";
          const text = String(row.text || "").trim();
          const compactText = text.length > 180 ? `${{text.slice(0, 177)}}...` : text;
          return `
            <li class="comment-item">
              <div class="comment-head">
                <span>Local ${{row.location_id}} | Rating ${{row.rating}} | Urgencia ${{row.urgency}}</span>
                <span class="comment-pill">${{sentiment}}</span>
              </div>
              <p class="comment-text">${{compactText}}</p>
              <div class="comment-head" style="margin-top:0.45rem;">
                <span>Resumen IA: ${{row.summary || "Sin resumen"}}</span>
                <span>${{createdAt}}</span>
              </div>
            </li>
          `;
        }}).join("");
      }}

      function rerunRevealAnimations() {{
        document.querySelectorAll(".reveal").forEach((element) => {{
          element.style.animation = "none";
          element.offsetHeight;
          element.style.animation = "";
        }});
      }}

      function wireInteractions(data) {{
        byId("minMentions").addEventListener("input", (event) => {{
          const target = event.target;
          byId("minMentionsValue").textContent = target.value;
          renderCategories(data);
        }});

        byId("sortMode").addEventListener("change", () => {{
          renderCategories(data);
        }});

        byId("rerenderBtn").addEventListener("click", () => {{
          rerunRevealAnimations();
        }});
      }}

      function renderMeta(data) {{
        byId("footerMeta").textContent = `Fuente: pipeline ETL + análisis estructurado LLM | Ventana ${{data.week_start}} -> ${{data.week_end}}`;
      }}

      function render() {{
        if (state.status !== "ready" || !state.data) {{
          return;
        }}

        const data = state.data;
        renderHeader(data);
        renderKpi(data);
        renderSentiment(data);
        renderTables(data);
        renderSidebar(data);
        renderCategoryControls(data);
        renderCategories(data);
        renderCommentSamples(data);
        renderMeta(data);
        wireInteractions(data);
      }}

      function renderError() {{
        document.body.innerHTML = `
          <main style="padding:2rem;font-family:IBM Plex Sans, sans-serif;">
            <h1>No se pudo renderizar el reporte</h1>
            <p>${{state.error || "Error desconocido"}}</p>
          </main>
        `;
      }}

      parseData();
    }})();
  </script>
</body>
</html>
    """.strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _render_pdf(metrics: WeeklyMetrics, summary: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    margin = 36
    y = height - margin

    def ensure_space(required: float) -> None:
        nonlocal y
        if y - required < margin:
            c.showPage()
            y = height - margin

    def draw_section_title(title: str) -> None:
        nonlocal y
        ensure_space(24)
        c.setFillColorRGB(0.11, 0.20, 0.25)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, title)
        y -= 16

    # Header band
    header_height = 68
    c.setFillColorRGB(0.10, 0.22, 0.26)
    c.rect(0, height - header_height, width, header_height, fill=1, stroke=0)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, height - 28, "BrewMaster | FeedbackIQ")
    c.setFont("Helvetica", 10)
    c.drawString(margin, height - 44, "Reporte semanal de experiencia de clientes")

    y = height - header_height - 14
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica", 9)
    c.drawString(
        margin,
        y,
        f"Ventana: {metrics.week_start.strftime('%Y-%m-%d %H:%M UTC')} -> {metrics.week_end.strftime('%Y-%m-%d %H:%M UTC')}",
    )
    y -= 18

    # KPI cards
    card_gap = 10
    card_w = (width - (margin * 2) - (card_gap * 2)) / 3
    card_h = 48
    kpis = [
        ("Total resenas", str(metrics.total_reviews)),
        ("Sentimiento negativo", f"{metrics.sentiment_distribution['negative']:.2f}%"),
        ("Sentimiento positivo", f"{metrics.sentiment_distribution['positive']:.2f}%"),
    ]

    ensure_space(card_h + 18)
    for idx, (label, value) in enumerate(kpis):
        x = margin + idx * (card_w + card_gap)
        c.setFillColorRGB(0.96, 0.95, 0.92)
        c.roundRect(x, y - card_h, card_w, card_h, 6, fill=1, stroke=0)
        c.setFillColorRGB(0.33, 0.37, 0.41)
        c.setFont("Helvetica", 8)
        c.drawString(x + 8, y - 14, label)
        c.setFillColorRGB(0.12, 0.17, 0.20)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x + 8, y - 32, value)
    y -= card_h + 16

    # Executive summary
    draw_section_title("Resumen ejecutivo")
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica", 10)
    summary_lines = wrap(summary.strip() or "Sin resumen disponible.", width=100)
    for line in summary_lines:
        ensure_space(14)
        c.drawString(margin, y, line)
        y -= 13
    y -= 8

    # Sentiment chart (horizontal bars)
    draw_section_title("Grafico de sentimiento (%)")
    chart_x = margin
    chart_w = width - (margin * 2)
    bar_h = 12
    bar_gap = 16
    bars = [
        ("Positivo", float(metrics.sentiment_distribution["positive"]), (0.18, 0.62, 0.27)),
        ("Negativo", float(metrics.sentiment_distribution["negative"]), (0.71, 0.14, 0.09)),
        ("Neutral", float(metrics.sentiment_distribution["neutral"]), (0.85, 0.47, 0.02)),
    ]
    ensure_space((bar_h + bar_gap) * len(bars) + 8)
    for label, pct, color in bars:
        c.setFillColorRGB(0.35, 0.40, 0.43)
        c.setFont("Helvetica", 9)
        c.drawString(chart_x, y, label)
        track_x = chart_x + 68
        track_w = chart_w - 130
        c.setFillColorRGB(0.90, 0.90, 0.90)
        c.rect(track_x, y - 8, track_w, bar_h, fill=1, stroke=0)
        fill_w = max(0, min(track_w, track_w * (pct / 100.0)))
        c.setFillColorRGB(*color)
        c.rect(track_x, y - 8, fill_w, bar_h, fill=1, stroke=0)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(chart_x + chart_w, y, f"{pct:.2f}%")
        y -= bar_h + bar_gap
    y -= 2

    def draw_rank_list(title: str, rows: list[tuple[int, float | int]], value_fmt: str) -> None:
        nonlocal y
        draw_section_title(title)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont("Helvetica", 10)
        if not rows:
            ensure_space(14)
            c.drawString(margin, y, "- Sin datos en esta ventana.")
            y -= 14
            return

        for pos, (location_id, value) in enumerate(rows, start=1):
            ensure_space(14)
            c.drawString(margin, y, f"{pos}. Local {location_id}: {value_fmt.format(value)}")
            y -= 13
        y -= 4

    draw_rank_list(
        "Top 3 locales mejor valorados",
        metrics.top_rated_locations,
        "{:.2f} de rating promedio",
    )
    draw_rank_list(
        "Top 3 locales con menor rating",
        metrics.lowest_rated_locations,
        "{:.2f} de rating promedio",
    )
    draw_rank_list(
        "Top 3 locales con mas problemas",
        [(loc, count) for loc, count in metrics.top_problem_locations],
        "{} resenas negativas",
    )

    draw_section_title("Temas mas mencionados")
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica", 10)
    categories = list(metrics.category_frequency.items())[:6]
    if not categories:
        c.drawString(margin, y, "- Sin categorias disponibles.")
        y -= 13
    else:
        for category, mentions in categories:
            ensure_space(14)
            c.drawString(margin, y, f"- {category}: {mentions} menciones")
            y -= 13

    y -= 4
    draw_section_title("Voz del cliente (muestras negativas y neutrales)")
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica", 9)
    if not metrics.comment_samples:
        ensure_space(14)
        c.drawString(margin, y, "- Sin comentarios destacados en esta ventana.")
        y -= 13
    else:
        for idx, sample in enumerate(metrics.comment_samples[:6], start=1):
            ensure_space(30)
            text = str(sample["text"]).strip()
            compact = text if len(text) <= 120 else f"{text[:117]}..."
            c.drawString(
                margin,
                y,
                f"{idx}. Local {sample['location_id']} | {str(sample['sentiment']).upper()} | urg={sample['urgency']}",
            )
            y -= 12
            c.drawString(margin + 10, y, compact)
            y -= 14

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawRightString(
        width - margin,
        18,
        f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    )

    c.save()


def generate_weekly_report(week_start: date | None = None) -> ReportStats:
    metrics = _collect_metrics(week_start=week_start)
    summary = _executive_summary(metrics)

    html_path = Path("docs/weekly_report.html")
    pdf_path = Path("docs/weekly_report.pdf")

    _render_html(metrics=metrics, summary=summary, output_path=html_path)
    _render_pdf(metrics=metrics, summary=summary, output_path=pdf_path)

    return ReportStats(html_path=str(html_path), pdf_path=str(pdf_path))
