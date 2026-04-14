# Operations Runbook (ES/EN)

## ES - Operación diaria
1. Ejecutar migraciones: `uv run alembic upgrade head`
2. Cargar data demo: `uv run python -m src.main seed --total 220`
3. Levantar API dummy: `uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8081`
4. Ejecutar ETL: `uv run python -m src.main etl`
5. Ejecutar análisis: `uv run python -m src.main analyze --limit 100`
6. Ejecutar alertas: `uv run python -m src.main alerts`
7. Generar reporte: `uv run python -m src.main report`

## EN - Daily operation
1. Apply migrations: `uv run alembic upgrade head`
2. Seed demo data: `uv run python -m src.main seed --total 220`
3. Run dummy API: `uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8081`
4. Run ETL: `uv run python -m src.main etl`
5. Run analysis: `uv run python -m src.main analyze --limit 100`
6. Run alerts: `uv run python -m src.main alerts`
7. Generate report: `uv run python -m src.main report`

## Alert rules
- `CRITICA`: any review with `urgency = 5`.
- `ALTA`: 3+ negative reviews in 24h by location.
- `MEDIA`: weekly average rating below `3.5`.

## Reliability controls
- ETL idempotency via upsert on `(source, source_review_id)`.
- Analysis idempotency via upsert on `unified_review_id`.
- Alert dedupe via unique key `(rule_code, location_id, window_start, window_end)`.
- Dead-letter events on extract/transform/analyze failures.

## Artifacts
- Report HTML: `docs/weekly_report.html`
- Report PDF: `docs/weekly_report.pdf`
- Alert fallback: `artifacts/alerts_webhook_fallback.jsonl`
