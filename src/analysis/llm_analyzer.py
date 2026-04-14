from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.analysis.prompts import SYSTEM_PROMPT
from src.analysis.schemas import ReviewAnalysisOutput
from src.analysis.usage_tracker import LLMUsageEvent, write_usage_event
from src.core.config import get_settings
from src.core.db import session_scope
from src.db.models import ReviewAnalysis, UnifiedReview
from src.etl.loader import write_dead_letter


@dataclass
class AnalysisStats:
    pending: int = 0
    analyzed: int = 0
    stored: int = 0
    dead_letters: int = 0
    errors: list[str] = field(default_factory=list)


def _analysis_insert_statement(dialect: str):
    if dialect == "postgresql":
        return pg_insert(ReviewAnalysis)
    if dialect == "sqlite":
        return sqlite_insert(ReviewAnalysis)
    raise ValueError(f"Unsupported dialect for analysis upsert: {dialect}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError, APIStatusError)),
    reraise=True,
)
def _request_analysis(client: OpenAI, model: str, review_text: str, rating: int) -> tuple[ReviewAnalysisOutput, dict[str, int | str]]:
    schema = ReviewAnalysisOutput.model_json_schema()
    user_prompt = (
        "Analyze this customer review and produce structured output.\n"
        f"Rating: {rating}\n"
        f"Text: {review_text}"
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "review_analysis",
                "strict": True,
                "schema": schema,
            },
        },
    )

    content = response.choices[0].message.content or "{}"
    data = json.loads(content)
    output = ReviewAnalysisOutput.model_validate(data)
    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or (prompt_tokens + completion_tokens))

    return output, {
        "model": str(response.model or model),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _upsert_review_analysis(session, unified_review_id: int, analysis: ReviewAnalysisOutput) -> None:
    dialect = session.bind.dialect.name if session.bind is not None else ""
    insert_stmt = _analysis_insert_statement(dialect).values(
        {
            "unified_review_id": unified_review_id,
            "sentiment": analysis.sentiment,
            "categories": analysis.categories,
            "summary": analysis.summary,
            "urgency": analysis.urgency,
            "created_at": datetime.now(timezone.utc),
        }
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["unified_review_id"],
        set_={
            "sentiment": insert_stmt.excluded.sentiment,
            "categories": insert_stmt.excluded.categories,
            "summary": insert_stmt.excluded.summary,
            "urgency": insert_stmt.excluded.urgency,
            "created_at": insert_stmt.excluded.created_at,
        },
    )
    session.execute(stmt)


def analyze_pending_reviews(limit: int = 100) -> AnalysisStats:
    settings = get_settings()
    stats = AnalysisStats()

    with session_scope() as session:
        stmt = (
            select(UnifiedReview)
            .outerjoin(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
            .where(ReviewAnalysis.id.is_(None))
            .order_by(UnifiedReview.id.asc())
            .limit(limit)
        )
        pending = session.scalars(stmt).all()
        stats.pending = len(pending)

        if not settings.openai_api_key:
            stats.errors.append("OPENAI_API_KEY is not set. Skipping analysis stage.")
            return stats

        client = OpenAI(api_key=settings.openai_api_key)

        for review in pending:
            try:
                analysis = _request_analysis(
                    client=client,
                    model=settings.openai_model,
                    review_text=review.text,
                    rating=review.rating,
                )
                parsed_analysis, usage = analysis
                stats.analyzed += 1
                _upsert_review_analysis(session=session, unified_review_id=review.id, analysis=parsed_analysis)
                stats.stored += 1
                write_usage_event(
                    LLMUsageEvent(
                        created_at=datetime.now(timezone.utc).isoformat(),
                        stage="analysis",
                        model=usage["model"],
                        prompt_tokens=int(usage["prompt_tokens"]),
                        completion_tokens=int(usage["completion_tokens"]),
                        total_tokens=int(usage["total_tokens"]),
                        unified_review_id=int(review.id),
                        source=str(review.source),
                        source_review_id=str(review.source_review_id),
                        location_id=int(review.location_id),
                        rating=int(review.rating),
                        text_length=len(review.text),
                    )
                )
            except (ValidationError, json.JSONDecodeError, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError, Exception) as exc:
                write_dead_letter(
                    session=session,
                    stage="analysis",
                    source=review.source,
                    payload={
                        "unified_review_id": review.id,
                        "source_review_id": review.source_review_id,
                        "text": review.text,
                        "rating": review.rating,
                    },
                    error=str(exc),
                )
                stats.dead_letters += 1
                stats.errors.append(f"analysis failed for review {review.id}: {exc}")

    return stats
