Plan 23h — FeedbackIQ (Entrega 100 pts, enfoque senior)
Resumen
Construiremos un proyecto Python 3.11 con uv, PostgreSQL en Docker y una arquitectura por capas (extractor -> transformer -> loader) con idempotencia fuerte, análisis LLM estructurado, alertas deduplicadas y reporte semanal en HTML + PDF.
La ejecución será por CLI con subcomandos para correr cada fase de forma aislada o end-to-end, y README bilingüe para evaluación rápida.

Cambios de implementación (decisión completa)
Infraestructura y base del proyecto
Estructura base en src/ con módulos por dominio (etl, analysis, alerts, reports, core).
docker-compose.yml con servicios:
postgres (persistencia local con volumen).
reviews_api (FastAPI dummy en :8081).
app (runner/CLI para ETL, análisis, alertas y reporte).
Dependencias principales: fastapi, uvicorn, sqlalchemy, alembic, psycopg[binary], pydantic, httpx, openai, tenacity, pytest, pytest-asyncio, jinja2, reportlab, python-dateutil.
Configuración por ENV con defaults seguros (DATABASE_URL, OPENAI_API_KEY, OPENAI_MODEL=gpt-4o-mini, SLACK_WEBHOOK_URL, TIMEZONE=UTC).
Modelo de datos, migraciones y seeds
Migraciones con Alembic para tablas:
customer_surveys
unified_reviews con UNIQUE(source, source_review_id)
review_analysis con UNIQUE(unified_review_id)
alerts con UNIQUE(rule_code, location_id, window_start, window_end) para no duplicar.
dead_letter_events (payload, etapa, error, created_at) para registros inválidos.
Índices operativos:
unified_reviews(created_at, location_id)
review_analysis(sentiment, urgency, created_at)
alerts(created_at, severity)
Seed reproducible:
15 locales.
200+ customer_surveys.
API dummy con reseñas de 7+ días, duplicados intencionales y casos negativos para disparar reglas.
ETL idempotente (Desafío 1)
Extractores:
API: GET /api/reviews?location_id={id}&since={iso8601} para location_id 1..15.
DB: SELECT de customer_surveys por ventana de 7 días.
Transformación:
Unificación a UnifiedReview (Pydantic).
Normalización estricta de fecha a UTC ISO-8601.
Limpieza de texto/author y validaciones fuertes de rating/location.
Carga:
INSERT ... ON CONFLICT (source, source_review_id) DO UPDATE para mantener idempotencia + correcciones tardías.
Lotes transaccionales por fuente.
Fail-fast controlado:
Error de red/fuente: se marca fallo del lote y se continúa con la otra fuente.
Error de registro: se envía a dead_letter_events sin romper todo el job.
CLI:
python -m src.main etl --since <iso8601>.
Análisis LLM estructurado (Desafío 2)
Selección de pendientes: reseñas en unified_reviews sin fila en review_analysis.
Prompting:
Reglas cerradas para sentiment (positive|negative|neutral), categorías permitidas (producto|servicio|ambiente|precio|limpieza|otro), urgency entero 1..5, summary <= 100.
OpenAI:
Modelo por defecto gpt-4o-mini.
Salida estructurada con JSON Schema + validación Pydantic posterior.
Resiliencia:
tenacity con backoff exponencial (2s, 4s, 8s, límite de intentos).
Manejo explícito de timeout, 429 y 5xx.
Persistencia:
Upsert en review_analysis por unified_review_id.
Fallos no recuperables -> dead_letter_events.
CLI:
python -m src.main analyze --limit N.
Alertas + notificación (Desafío 3)
Reglas implementadas:
CRITICA: cualquier análisis con urgency=5.
ALTA: >=3 negativas por local en 24h.
MEDIA: promedio rating semanal < 3.5 por local.
Dedupe temporal:
Unicidad por rule_code + location_id + window_start + window_end.
Notificación:
Primario: Slack webhook con payload estructurado.
Fallback obligatorio: archivo JSONL (artifacts/alerts_webhook_fallback.jsonl) cuando no haya webhook o falle envío.
CLI:
python -m src.main alerts --now <iso8601>.
Reporte semanal (Desafío 4, opcional para 100 pts)
Generación de métricas semanales:
Total reseñas.
Distribución de sentimiento.
Top 3 mejores locales.
Top 3 con más problemas.
Categorías más mencionadas.
Resumen ejecutivo LLM (1 párrafo) con salida validada.
Salidas:
HTML en docs/weekly_report.html.
PDF en docs/weekly_report.pdf (misma data base).
CLI:
python -m src.main report --week-start YYYY-MM-DD.
Interfaces públicas y contratos
API dummy Fuente A
GET /api/reviews?location_id={id}&since={iso8601}
Contrato exacto del enunciado (review_id, location_id, rating, text, author, created_at UTC).
Modelos de intercambio internos
UnifiedReview (input normalizado ETL).
ReviewAnalysis (salida estructurada LLM).
AlertEvent (mensaje + severidad + ventana + regla).
CLI única
etl, analyze, alerts, report, run-all.
run-all ejecuta secuencia: ETL -> análisis -> alertas -> reporte.
Plan de pruebas (aceptación)
Unitarias
Normalización de fechas a UTC y formato ISO-8601.
Transformación API/survey a UnifiedReview.
Validación estricta de salida LLM (rechazo de categorías/sentimiento inválidos).
Integración DB
Upsert ETL no duplica al correr 2+ veces.
review_analysis no duplica por unified_review_id.
Dedupe de alertas por ventana/regla/local.
Integración flujo
Pipeline completo con datos seed genera:
reseñas unificadas,
análisis LLM persistido,
alertas esperadas,
reporte HTML y PDF.
Fallback webhook: sin SLACK_WEBHOOK_URL se genera archivo JSONL y se guarda alerta en DB.
Cronograma operativo (23h)
Horas 1-4: Docker + Alembic + seeds + API dummy.
Horas 5-10: ETL completo idempotente + validaciones + dead letters.
Horas 11-15: módulo LLM con structured output + retries + persistencia.
Horas 16-18: reglas de alerta + dedupe + Slack/fallback JSONL.
Horas 19-20: pruebas unitarias/integración clave.
Horas 21-22: refactor final, typing completo, logging estructurado.
Hora 23: README bilingüe (quickstart 5 pasos + arquitectura + troubleshooting).
Supuestos y defaults cerrados
Python 3.11 con uv.
PostgreSQL como motor único.
Modelo OpenAI default: gpt-4o-mini.
Canal principal de notificación: Slack webhook, con fallback a JSONL.
No duplicación de alertas por regla + local + ventana.
Entrega incluye obligatorio + opcional (100 pts).
README y documentación clave en formato bilingüe (ES/EN).