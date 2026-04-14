FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN uv pip install --system .

CMD ["python", "-m", "src.main", "run-all"]
