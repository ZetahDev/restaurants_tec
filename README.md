# FeedbackIQ

Intelligent review consolidation and analysis pipeline for the BrewMaster technical challenge.

## ES - Qué resuelve
- Consolida reseñas desde 2 fuentes (`API` + `customer_surveys`).
- Ejecuta ETL idempotente con `upsert` y control de errores por `dead_letter_events`.
- Analiza reseñas con LLM (salida estructurada) y guarda en `review_analysis`.
- Genera alertas automáticas (`CRITICA`, `ALTA`, `MEDIA`) con deduplicación por ventana.
- Publica reporte semanal en HTML y PDF.

## EN - What it delivers
- Consolidates reviews from two sources (`API` + `customer_surveys`).
- Runs idempotent ETL with `upsert` and dead-letter handling.
- Performs structured LLM analysis and persists results in `review_analysis`.
- Generates automatic alerts (`CRITICA`, `ALTA`, `MEDIA`) with window-based dedupe.
- Produces weekly report in HTML and PDF.

## Architecture
- `src/api`: dummy FastAPI source (`GET /api/reviews`).
- `src/etl`: extractors, transformers, loader, ETL orchestration.
- `src/analysis`: prompts, schema, OpenAI analyzer with retry/backoff.
- `src/alerts`: detector rules and notifier (Slack + JSON fallback).
- `src/reports`: weekly metrics + HTML/PDF generation.
- `src/scripts`: seed utilities.

## Database model
- `customer_surveys`
- `unified_reviews` (`UNIQUE(source, source_review_id)`)
- `review_analysis` (`UNIQUE(unified_review_id)`)
- `alerts` (`UNIQUE(rule_code, location_id, window_start, window_end)`)
- `dead_letter_events`

## 5-step run (Docker-first)
1. Copy env values:
   - `cp .env.example .env`
2. Install dependencies:
   - `uv sync --extra dev`
3. Start infrastructure:
   - `docker compose up -d postgres reviews_api`
4. Apply migrations and seed:
   - `uv run alembic upgrade head`
   - `uv run python -m src.main seed --total 220`
5. Execute pipeline:
   - `uv run python -m src.main run-all --analyze-limit 100`

## CLI reference
- `uv run python -m src.main seed --total 220`
- `uv run python -m src.main etl --since 2026-04-10T00:00:00+00:00`
- `uv run python -m src.main analyze --limit 100`
- `uv run python -m src.main alerts --now 2026-04-14T12:00:00+00:00`
- `uv run python -m src.main report --week-start 2026-04-07`
- `uv run python -m src.main run-all --analyze-limit 100`

## Testing
- `uv run pytest -q`

## Environment variables
- `DATABASE_URL`
- `API_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `SLACK_WEBHOOK_URL`
- `TIMEZONE`

## Troubleshooting
- `docker: command not found`:
  - Install Docker Desktop and rerun `docker compose` commands.
- `OPENAI_API_KEY is not set`:
  - Analysis stage is skipped by design for local offline execution.
- No Slack webhook configured:
  - Notifications are written to `artifacts/alerts_webhook_fallback.jsonl`.

## Notes
- Private learning files live in `.private/` and are excluded via `.gitignore`.
- Commit history follows descriptive English commit messages per milestone.
