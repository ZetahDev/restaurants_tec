# Learning Summary (Public)

1. Idempotency is non-negotiable in ETL pipelines.
- Using `UNIQUE(source, source_review_id)` plus upsert keeps ingestion deterministic across reruns.

2. Structured LLM outputs drastically reduce downstream parsing risk.
- JSON schema + strict validation is safer than parsing free text.

3. Dead-letter persistence is essential for operational traceability.
- Failed records are not lost; they can be audited and replayed later.

4. Alert deduplication must include a time window.
- Rule + location + window prevents noisy re-alerting.

5. Notification readability matters as much as detection correctness.
- A digest grouped by severity is more actionable than raw JSON per event.

6. Demo automation improves evaluator confidence.
- `prep-demo` creates a reproducible state and prints readiness counters.

7. Tests should validate behavior guarantees, not only happy paths.
- UTC normalization, upsert idempotency, schema strictness, and dedupe are explicitly covered.

8. Separate private learning from public deliverables.
- `.private/` supports personal growth while public docs stay clean and evaluator-focused.
