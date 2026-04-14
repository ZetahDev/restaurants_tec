# Technical Evaluation Checklist (Evaluator-facing)

## Current status vs challenge rubric

- Challenge 1 (ETL): Implemented and validated (idempotent upsert, dual source extract, UTC normalization).
- Challenge 2 (LLM analysis): Implemented with structured output + retries + schema validation.
- Challenge 3 (Alerts): Implemented with dedupe rules and readable Slack digest.
- Challenge 4 (Report): Implemented (HTML + PDF) with dynamic HTML rendering from real payload.

## What the evaluator should see when running the project

### Option A: PostgreSQL (official path)
1. `cp .env.example .env`
2. `uv sync --extra dev`
3. `docker compose up -d postgres reviews_api`
4. `./scripts/start_demo.sh --sync --no-sqlite-fallback`

Expected outcome:
- `prep-demo` prints final JSON with `final_pending_analysis`.
- `docs/weekly_report.html` and `docs/weekly_report.pdf` are regenerated.
- Slack digest notification appears if `SLACK_WEBHOOK_URL` is set.
- If Slack is missing/failing, fallback JSONL is written.

### Option B: Local fallback (no PostgreSQL available)
1. `cp .env.example .env`
2. `uv sync --extra dev`
3. `./scripts/start_demo.sh --sync`

Expected outcome:
- Script warns PostgreSQL is unreachable, then switches to SQLite.
- Full flow still runs and reaches READY state.

## How evaluator can test correctness quickly

1. Reliability gate:
- `uv run pytest -q` should pass.

2. ETL idempotency gate:
- Run ETL twice and verify no duplicate growth in `unified_reviews`.

3. Alert dedupe gate:
- Run alerts twice and verify no duplicate alert rows for same rule/location/window.

4. End-to-end gate:
- Use `prep-demo` and verify target fields:
  - `final_pending_analysis=0`
  - `dead_letters_after=0` (if cleanup enabled)

## LLM usage and token consumption validation

### Where consumption is recorded
- File: `artifacts/llm_usage.jsonl`
- One JSON event per successful LLM analysis call.
- Includes prompt/completion/total tokens and model.

### How to inspect usage
- Full summary:
  - `uv run python -m src.main llm-usage`
- Last 24h:
  - `uv run python -m src.main llm-usage --since-hours 24`

### What to evaluate from usage output
- `events`: number of LLM calls.
- `total_prompt_tokens`, `total_completion_tokens`, `total_tokens`: total consumption.
- `avg_total_tokens_per_event`: per-review average usage.
- `models`: distribution by model.
- `top_token_events`: most expensive requests (for optimization opportunities).

## Critical reviewer notes (senior-level)

1. Strengths
- Strong idempotency guarantees at DB level.
- Structured output contract avoids fragile text parsing.
- Alert dedupe and fallback channels are production-minded.
- Deterministic demo workflow (`prep-demo`) reduces presentation risk.

2. Remaining risks
- Real API cost/rate variability: addressed by retries and token observability, but still external dependency.
- Secrets hygiene: never commit real `.env`; rotate tokens if ever exposed.
- For very high volume, analysis should be moved to async queue workers.

3. Recommended next iteration
- Add CI stage that runs `prep-demo` on ephemeral DB and publishes artifacts.
- Add dashboard for token/cost trend by day/model.
- Add optional hard budget guardrail (abort analysis batch if token budget exceeded).
