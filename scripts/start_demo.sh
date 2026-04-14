#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

API_HOST="127.0.0.1"
API_PORT="8081"
REPORT_PORT="8090"
SEED_TOTAL="220"
BATCH_SIZE="100"
MAX_BATCHES="20"
RUN_SEED="true"
CLEAN_DEAD_LETTERS="true"
OPEN_BROWSER="true"
RUN_SYNC="false"
HOLD_SERVICES="true"
AUTO_SQLITE_FALLBACK="true"

API_PID=""
DOCS_PID=""

usage() {
  cat <<'USAGE'
Usage: ./scripts/start_demo.sh [options]

Options:
  --api-port <port>              API port (default: 8081)
  --report-port <port>           HTML report server port (default: 8090)
  --seed-total <n>               Number of seeded surveys (default: 220)
  --batch-size <n>               prep-demo analyze batch size (default: 100)
  --max-batches <n>              prep-demo max batches (default: 20)
  --no-seed                      Skip seed step
  --no-clean-dead-letters        Keep dead_letter_events after snapshot
  --no-open-browser              Do not auto-open the HTML report
  --sync                         Run `uv sync --extra dev` before execution
  --exit-after-ready             Exit after pipeline/report are ready (no long-running hold)
  --no-sqlite-fallback           Fail if PostgreSQL URL is unreachable (do not fallback to SQLite)
  --help                         Show this help

Notes:
  - Works on macOS and Windows when executed from Git Bash.
  - If DATABASE_URL is not set, it defaults to local SQLite for portability.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --report-port)
      REPORT_PORT="$2"
      shift 2
      ;;
    --seed-total)
      SEED_TOTAL="$2"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="$2"
      shift 2
      ;;
    --max-batches)
      MAX_BATCHES="$2"
      shift 2
      ;;
    --no-seed)
      RUN_SEED="false"
      shift
      ;;
    --no-clean-dead-letters)
      CLEAN_DEAD_LETTERS="false"
      shift
      ;;
    --no-open-browser)
      OPEN_BROWSER="false"
      shift
      ;;
    --sync)
      RUN_SYNC="true"
      shift
      ;;
    --exit-after-ready)
      HOLD_SERVICES="false"
      shift
      ;;
    --no-sqlite-fallback)
      AUTO_SQLITE_FALLBACK="false"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

cleanup() {
  local exit_code=$?
  if [[ -n "${DOCS_PID}" ]] && kill -0 "${DOCS_PID}" >/dev/null 2>&1; then
    kill "${DOCS_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" >/dev/null 2>&1; then
    kill "${API_PID}" >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv is not installed. Install uv first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

preloaded_database_url="${DATABASE_URL:-}"

if [[ -f ".env" ]]; then
  # Export .env values to current shell.
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ -n "${preloaded_database_url}" ]]; then
  export DATABASE_URL="${preloaded_database_url}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="sqlite:///./feedbackiq.db"
  echo "[INFO] DATABASE_URL not found. Using SQLite: ${DATABASE_URL}"
fi

if [[ "${DATABASE_URL}" == postgresql* ]]; then
  if ! DATABASE_URL="${DATABASE_URL}" uv run python - <<'PY'
import os
import socket
import sys
from urllib.parse import urlparse

raw_url = os.environ["DATABASE_URL"]
normalized = raw_url.replace("+psycopg", "")
parsed = urlparse(normalized)
host = parsed.hostname or "localhost"
port = parsed.port or 5432

try:
    socket.create_connection((host, port), timeout=1.5).close()
except OSError:
    sys.exit(1)
PY
  then
    if [[ "${AUTO_SQLITE_FALLBACK}" == "true" ]]; then
      echo "[WARN] PostgreSQL is configured but unreachable at ${DATABASE_URL}."
      echo "[WARN] Falling back to SQLite for local execution."
      export DATABASE_URL="sqlite:///./feedbackiq.db"
    else
      echo "[ERROR] PostgreSQL is unreachable and fallback is disabled." >&2
      echo "[ERROR] Start PostgreSQL (e.g. docker compose up -d postgres) or remove --no-sqlite-fallback." >&2
      exit 1
    fi
  fi
fi

export API_BASE_URL="http://${API_HOST}:${API_PORT}"
mkdir -p artifacts

if [[ "${RUN_SYNC}" == "true" ]]; then
  echo "[STEP] Syncing dependencies..."
  uv sync --extra dev
fi

echo "[STEP] Running migrations..."
uv run alembic upgrade head

if curl -fsS "${API_BASE_URL}/openapi.json" >/dev/null 2>&1; then
  echo "[INFO] API already running at ${API_BASE_URL}"
else
  echo "[STEP] Starting API service on ${API_BASE_URL}..."
  uv run uvicorn src.api.app:app --host "${API_HOST}" --port "${API_PORT}" > artifacts/api_server.log 2>&1 &
  API_PID="$!"

  for _ in {1..30}; do
    if curl -fsS "${API_BASE_URL}/openapi.json" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! curl -fsS "${API_BASE_URL}/openapi.json" >/dev/null 2>&1; then
    echo "[ERROR] API did not start correctly. Check artifacts/api_server.log" >&2
    exit 1
  fi
fi

if [[ "${RUN_SEED}" == "true" ]]; then
  echo "[STEP] Seeding data..."
  uv run python -m src.main seed --total "${SEED_TOTAL}"
else
  echo "[INFO] Seed skipped."
fi

echo "[STEP] Preparing demo state (etl + analysis + alerts + report)..."
uv run python -m src.main prep-demo \
  --batch-size "${BATCH_SIZE}" \
  --max-batches "${MAX_BATCHES}" \
  --clean-dead-letters "${CLEAN_DEAD_LETTERS}"

REPORT_HTML="${ROOT_DIR}/docs/weekly_report.html"
if [[ ! -f "${REPORT_HTML}" ]]; then
  echo "[ERROR] Report HTML was not generated at ${REPORT_HTML}" >&2
  exit 1
fi

REPORT_URL="http://${API_HOST}:${REPORT_PORT}/weekly_report.html"

if curl -fsS "http://${API_HOST}:${REPORT_PORT}" >/dev/null 2>&1; then
  echo "[INFO] HTML server already running on port ${REPORT_PORT}"
else
  echo "[STEP] Starting HTML server on http://${API_HOST}:${REPORT_PORT}..."
  uv run python -m http.server "${REPORT_PORT}" --bind "${API_HOST}" --directory docs > artifacts/html_server.log 2>&1 &
  DOCS_PID="$!"
fi

if [[ "${OPEN_BROWSER}" == "true" ]]; then
  case "$(uname -s)" in
    Darwin)
      open "${REPORT_URL}" >/dev/null 2>&1 || true
      ;;
    MINGW*|MSYS*|CYGWIN*)
      cmd.exe /c start "" "${REPORT_URL}" >/dev/null 2>&1 || true
      ;;
    *)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${REPORT_URL}" >/dev/null 2>&1 || true
      fi
      ;;
  esac
fi

echo
echo "[READY] API: ${API_BASE_URL}"
echo "[READY] Report: ${REPORT_URL}"
echo "[READY] Logs: artifacts/api_server.log, artifacts/html_server.log"
echo
echo "Press Ctrl+C to stop started services."

if [[ "${HOLD_SERVICES}" == "true" ]] && ([[ -n "${API_PID}" ]] || [[ -n "${DOCS_PID}" ]]); then
  wait
fi
