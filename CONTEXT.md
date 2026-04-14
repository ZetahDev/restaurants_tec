PRUEBA TÉCNICA DESARROLLADOR IA

Instrucciones para el Candidato

FeedbackIQ — Sistema Inteligente de Análisis de Reseñas
Duración: 3–5 horas | Plazo: 5 días | Nivel: Junior – Mid
CONFIDENCIAL – Solo para el candidato asignado

Bienvenido/a
Gracias por participar en nuestro proceso de selección. Esta prueba evalúa tu
capacidad para diseñar e implementar soluciones que integren pipelines de datos con
inteligencia artificial.

El Problema
Una cadena de cafeterías llamada "BrewMaster" tiene 15 locales en la ciudad.
Actualmente reciben reseñas de clientes a través de dos fuentes definidas para esta
prueba:
• Fuente A: API local de reseñas (FastAPI en Python)
• Fuente B: Base de datos de encuestas de satisfacción post-compra (motor de base de
datos a elección)
El gerente regional pasa horas cada semana leyendo reseñas manualmente para
detectar problemas. Quiere un sistema automatizado que:
1. Consolide las reseñas de ambas fuentes
2. Analice automáticamente el sentimiento y los temas mencionados
3. Genere alertas cuando hay problemas que requieren atención
4. Produzca un resumen ejecutivo semanal

Arquitectura Esperada
El sistema debe seguir este flujo:

┌───────────────────────────┐
┌───────────────────────────┐
│ API Reseñas (FastAPI) │ │ DB Encuestas (a elección)│
│ http://localhost:8081 │ │ (PostgreSQL/MySQL/SQLite)│
└─────────────┬─────────────┘
└─────────────┬─────────────┘
│ │
└───────────────┬───────────────────┘
│
┌──────▼──────┐
│ ETL │
│ (Extract, │
│ Transform, │
│ Load) │
└──────┬──────┘
│
┌──────▼──────┐
│ Análisis │
│ con LLM │
└──────┬──────┘
│
┌───────────────┼───────────────┐
│ │ │
┌────▼────┐ ┌────▼────┐ ┌────▼────┐
│ Alertas │ │ Resumen │ │ Base │
│ (Email/ │ │ Semanal │ │ Datos │
│ Slack) │ │ (PDF/ │ │Análisis │
│ │ │ HTML) │ │ │
└─────────┘ └─────────┘ └─────────┘

Los 4 Desafíos
Desafío Puntos Obligatorio Nivel
1. Pipeline ETL 25 ✅ Sí Junior+
2. Análisis con LLM 30 ✅ Sí Junior+
3. Sistema de
Alertas

25 ✅ Sí Mid

4. Reporte
Automatizado

20 Opcional Mid

Detalle de los Desafíos
1. Pipeline ETL (25 pts) — Obligatorio
Implementa un pipeline que extraiga y consolide datos de ambas fuentes:
Fuente A — API de Reseñas (local, Python):
• Servicio: FastAPI (o equivalente en Python) escuchando en http://localhost:8081
• Endpoint: GET /api/reviews?location_id={id}&since={iso8601}
• Respuesta (200): lista JSON de objetos con este modelo:
- review_id: string (identificador estable; puede repetirse en llamadas distintas)
- location_id: int (1..15)
- rating: int (1..5)
- text: string
- author: string | null
- created_at: string ISO-8601 (UTC)
• Debes incluir en tu entrega una implementación mínima de esta API (y datos/seed)
para que el evaluador pueda ejecutarla.
Fuente B — Base de Datos de Encuestas (motor a elección):
• Motor permitido: PostgreSQL, MySQL o SQLite (elige uno)
• Tabla requerida: customer_surveys con el siguiente modelo lógico:
- id: integer (PK)
- location_id: int (1..15)
- rating: int (1..5)
- comments: text
- created_at: datetime (UTC)
- customer_email: text | null
• Debes incluir un script de seed que cree la tabla y cargue datos de ejemplo.
Modelo de datos (a replicar en tu base de datos, independientemente del motor):
• Tabla unified_reviews (consolidación):
- id: integer/uuid (PK)
- source: text ("api" | "survey")
- source_review_id: text (review_id del API o id de survey)
- location_id: int
- rating: int (1..5)
- text: text
- author: text | null
- created_at: datetime (UTC)
- ingested_at: datetime (UTC)
- UNIQUE(source, source_review_id) ← clave para idempotencia
• Tabla review_analysis (resultado del LLM):
- id: integer/uuid (PK)

- unified_review_id: FK a unified_reviews.id (UNIQUE)
- sentiment: text (positive|negative|neutral)
- categories: text/json (lista de categorías)
- summary: text (<= 100 caracteres)
- urgency: int (1..5)
- created_at: datetime (UTC)
• Tabla alerts:
- id: integer/uuid (PK)
- severity: text (CRITICA|ALTA|MEDIA)
- location_id: int
- message: text
- rule_code: text
- created_at: datetime (UTC)
Tu pipeline debe:
• Extraer datos de ambas fuentes (últimos 7 días)
• Normalizar el formato (mismo schema para ambas fuentes)
• Deduplicar (por la clave source + source_review_id)
• Cargar en unified_reviews
• Ser idempotente (ejecutar múltiples veces no duplica datos)
Entregables: src/etl/pipeline.py, src/etl/extractors.py, src/etl/transformers.py
2. Análisis con LLM (30 pts) — Obligatorio
Implementa un servicio que analice las reseñas usando un LLM:
Para cada reseña, el sistema debe extraer:
• Sentimiento: positivo, negativo, neutral
• Categorías mencionadas: producto, servicio, ambiente, precio, limpieza, otro
• Resumen: una frase que capture lo esencial (máx 100 caracteres)
• Urgencia: 1-5 (5 = requiere acción inmediata)
Requerimientos:
• Usa la API de OpenAI (gpt-4o-mini está bien, no necesitas el más caro)
• Diseña un prompt que extraiga esta información de forma estructurada
• Parsea la respuesta del LLM a un objeto/diccionario validado
• Maneja errores de la API (timeouts, rate limits)
• Guarda los resultados en la tabla: review_analysis
Entregables: src/analysis/llm_analyzer.py, src/analysis/prompts.py

3. Sistema de Alertas (25 pts) — Obligatorio
Implementa un sistema que genere alertas automáticas:
Reglas de alerta:
• CRÍTICA: Reseña con urgencia 5 (acción inmediata)
• ALTA: 3+ reseñas negativas del mismo local en 24 horas
• MEDIA: Rating promedio de un local cae por debajo de 3.5 en la semana
Acciones:
• Las alertas deben guardarse en tabla: alerts (tipo, local, mensaje, created_at)
• Implementa UN mecanismo de notificación (elige uno):
- Email (puedes usar mailtrap.io o similar para testing)
- Slack webhook
- Log estructurado a archivo JSON
• Las alertas no deben duplicarse (si ya se alertó sobre algo, no re-alertar)
Entregables: src/alerts/detector.py, src/alerts/notifier.py
4. Reporte Automatizado (20 pts) — Opcional
Implementa la generación de un resumen semanal:
El reporte debe incluir:
• Total de reseñas procesadas
• Distribución de sentimiento (% positivo/negativo/neutral)
• Top 3 locales mejor valorados
• Top 3 locales con más problemas
• Temas más mencionados (categorías)
• Un párrafo de resumen ejecutivo generado por el LLM
Formato:
• Genera el reporte como PDF o HTML
• Usa el LLM para escribir el resumen ejecutivo en lenguaje natural
Entregables: src/reports/weekly_report.py, ejemplo de reporte generado en docs/

Datos de Prueba
Debes incluir datos de prueba reproducibles (seed/fixtures) para que el evaluador pueda
ejecutar el sistema en local.
Mínimos sugeridos (puedes superarlos):
• 15 locales (location_id 1..15)
• ~200 encuestas históricas en customer_surveys
• La API debe devolver reseñas para varios locales y fechas (incluye algunos duplicados

intencionales y algunos casos “problemáticos” para disparar alertas)
Puedes agregar más datos de prueba si lo necesitas.

Formato de Entrega
• Crea un repositorio nuevo
• Trabaja con commits descriptivos
• Incluye un README.md con pasos exactos para ejecutar (instalación, seed, run)
• La solución debe poder ejecutarse en local de forma reproducible (por ejemplo: docker
compose up --build && python main.py, o equivalente)
• Incluye al menos tests básicos para el ETL y el análisis
• Entrega: link al repositorio o un .zip con el código fuente

Lo que Evaluamos
Sí evaluamos No evaluamos
Pipeline ETL robusto y bien estructurado Que uses un framework específico
Prompts claros que extraigan información
correcta

Optimización extrema de costos

Código limpio y fácil de entender Interfaz gráfica bonita
Manejo de errores y casos edge Que completes el desafío opcional
Documentación que explique tu solución Performance extrema

Tecnologías Sugeridas (no obligatorias)
• Python 3.10+
• SQLAlchemy o psycopg2 para PostgreSQL
• Requests o httpx para APIs
• OpenAI SDK para el LLM
• Pytest para tests
• Pydantic para validación de datos
Puedes usar otras tecnologías si las prefieres — lo importante es que funcione.