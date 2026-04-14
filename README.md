# FeedbackIQ (Technical Test Solution)

## ES
Pipeline de datos + IA para consolidar reseñas, analizarlas con LLM, generar alertas y reporte semanal.

## EN
Data + AI pipeline to consolidate reviews, analyze with an LLM, generate alerts, and produce a weekly report.

## Quick Start (5 steps)
1. Copy env: `cp .env.example .env`
2. Install deps: `uv sync`
3. Start DB/API: `docker compose up -d postgres reviews_api`
4. Run migrations + seed: `alembic upgrade head && python -m src.main seed`
5. Run pipeline: `python -m src.main run-all`

## Commit Strategy
Descriptive English commits with validation gate per step.

## Private learning docs
- `.private/guide.md`
- `.private/logbook.md`

Both are intentionally excluded from git.
