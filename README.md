# FeedbackIQ

Intelligent review consolidation and analysis pipeline for the BrewMaster technical challenge.

## ES - Qué resuelve
- Consolida reseñas desde API + encuestas.
- Ejecuta ETL idempotente con `upsert` y `dead_letter_events`.
- Analiza reseñas con LLM en salida estructurada validada.
- Genera alertas deduplicadas y notifica por Slack en formato digest legible.
- Produce reporte semanal en HTML/PDF.
- Incluye comando de preparación de demo (`prep-demo`) para estado de presentación.

## EN - What it delivers
- Consolidates reviews from API + survey sources.
- Runs idempotent ETL with upsert and dead-letter handling.
- Performs structured LLM analysis with schema validation.
- Generates deduplicated alerts and readable Slack digest notifications.
- Produces weekly HTML/PDF report.
- Includes a `prep-demo` command for deterministic presentation readiness.

## Architecture
- `src/api`: dummy FastAPI source (`GET /api/reviews`).
- `src/etl`: extractors, transformers, loader, ETL pipeline.
- `src/analysis`: prompts, output schema, OpenAI analyzer with retries.
- `src/alerts`: detector rules + digest notifier.
- `src/reports`: weekly metrics + HTML/PDF rendering.
- `src/scripts`: seed + prep-demo orchestration.

## Core data model
- `customer_surveys`
- `unified_reviews` (`UNIQUE(source, source_review_id)`)
- `review_analysis` (`UNIQUE(unified_review_id)`)
- `alerts` (`UNIQUE(rule_code, location_id, window_start, window_end)`)
- `dead_letter_events`

## Run Path A (Docker evaluator path)
1. `cp .env.example .env`
2. `uv sync --extra dev`
3. `docker compose up -d postgres reviews_api`
4. `uv run alembic upgrade head`
5. `uv run python -m src.main seed --total 220`
6. `uv run python -m src.main prep-demo --batch-size 100 --max-batches 20 --clean-dead-letters true`

## Run Path B (No Docker / local SQLite)
1. `cp .env.example .env`
2. `uv sync --extra dev`
3. `export DATABASE_URL=sqlite:///./feedbackiq.db`
4. Terminal A: `uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8081`
5. Terminal B:
   - `uv run alembic upgrade head`
   - `uv run python -m src.main seed --total 220`
   - `uv run python -m src.main prep-demo --batch-size 100 --max-batches 20 --clean-dead-letters true`

## One-command demo launcher (macOS + Windows Git Bash)
- Make sure `.env` exists (`cp .env.example .env`) and `uv` is installed.
- Run:
  - `./scripts/start_demo.sh --sync`
  - batch mode (CI/demo loop): `./scripts/start_demo.sh --sync --exit-after-ready --no-open-browser`
- Behavior:
  - If `DATABASE_URL` points to PostgreSQL and the server is up, it runs with PostgreSQL (evaluator path).
  - If PostgreSQL is configured but not reachable, it automatically falls back to SQLite (`sqlite:///./feedbackiq.db`) so local demo can continue.
  - To force strict PostgreSQL-only execution: add `--no-sqlite-fallback`.
- The script will:
  - run migrations
  - start API service on `:8081`
  - seed data
  - run `prep-demo`
  - serve `docs/weekly_report.html` on `:8090`
  - open the report in your browser

### PostgreSQL requirement for technical evaluation
- For the official PostgreSQL path, evaluators should run:
  - `docker compose up -d postgres reviews_api`
  - then `./scripts/start_demo.sh --sync --no-sqlite-fallback`

## CLI reference
- `uv run python -m src.main seed --total 220`
- `uv run python -m src.main etl --since 2026-04-10T00:00:00+00:00`
- `uv run python -m src.main analyze --limit 100`
- `uv run python -m src.main alerts --now 2026-04-14T12:00:00+00:00`
- `uv run python -m src.main report --week-start 2026-04-07`
- `uv run python -m src.main run-all --analyze-limit 100`
- `uv run python -m src.main prep-demo --batch-size 100 --max-batches 20 --clean-dead-letters true`

## Testing
- `uv run pytest -q`

## LLM token observability
- Every successful analysis call stores one usage event in:
  - `artifacts/llm_usage.jsonl`
- Event includes:
  - timestamp, model, prompt/completion/total tokens
  - review context (`unified_review_id`, `source`, `location_id`, rating, text length)
- Usage summary command:
  - `uv run python -m src.main llm-usage`
  - `uv run python -m src.main llm-usage --since-hours 24`
- This is the recommended proof for:
  - how many tokens were consumed
  - where consumption is concentrated
  - whether LLM usage remains stable across runs

## Environment variables
- `DATABASE_URL`
- `API_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `SLACK_WEBHOOK_URL`
- `TIMEZONE`

## Troubleshooting
- `OPENAI_API_KEY is not set`:
  - Analysis stage is skipped by design.
- Slack webhook missing/failing:
  - Digest payload is written to `artifacts/alerts_webhook_fallback.jsonl`.
- Want a clean demo state:
  - Use `prep-demo` to backfill analysis, archive/clean dead letters, run alerts, and regenerate report.

## Included evidence artifacts
- `docs/weekly_report.html`
- `docs/weekly_report.pdf`
- `docs/OPERATIONS.md`
- `docs/LEARNING_SUMMARY.md`
- `docs/TECHNICAL_EVALUATION_CHECKLIST.md`

## Notes
- Private learning files live in `.private/` and are intentionally excluded from git.
- Commit history uses descriptive English messages by milestone.
