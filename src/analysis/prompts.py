from __future__ import annotations

SYSTEM_PROMPT = """
You analyze coffee shop feedback. Output valid JSON only.
Schema: {sentiment, categories[], summary, urgency}
Rules:
- sentiment: positive|negative|neutral
- categories: producto|servicio|ambiente|precio|limpieza|otro (array)
- summary: 1 sentence Spanish, max 100 chars
- urgency: 1-5 (5=immediate issue, 4=urgent, 3=moderate, 2=minor, 1=positive)
- No extra keys.
""".strip()


def build_analysis_user_prompt(review_text: str, rating: int) -> str:
    return (
        "Analyze this customer review and produce structured output.\n"
        f"Rating: {rating}\n"
        f"Text: {review_text}"
    )
