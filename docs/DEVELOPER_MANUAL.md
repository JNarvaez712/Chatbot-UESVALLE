# Manual del Desarrollador – Chatbot UESVALLE

> Versión: 1.0.0  
> Última actualización: 2025-11-24  
> Responsable inicial: Equipo de desarrollo UESVALLE Bot

## 1. Resumen Ejecutivo
El proyecto "Chatbot UESVALLE" implementa un asistente conversacional enfocado en responder en español de forma **basada 100% en evidencia del sitio oficial** `https://www.uesvalle.gov.co`. Combina extracción y recuperación semántica (RAG) sobre un índice persistente, mapeo exhaustivo de URLs, clasificación de intenciones y normalización lingüística para devolver:
1. Enlaces oficiales de secciones.
2. Fragmentos literales o sintetizados controladamente de misión, visión, funciones y otras consultas institucionales.
3. Fallback pedagógico cuando no existe evidencia suficiente.

Su despliegue está preparado para:  
• Entornos Docker (imagen ligera Python 3.10).  
• Render (mediante `render.yaml`).  
• Hugging Face Spaces (usando `app.py` como entrypoint).  

## 2. Objetivos Técnicos
- Garantizar respuestas sin alucinaciones (modo extractivo por defecto: `EXACT_MODE=1`).
- Minimizar latencia (SLA por defecto ≤ 2.5s `MAX_QUERY_SECONDS`).
- Facilitar incorporación de nuevas URLs / documentos vía `routes.txt` o crawler incremental.
- Mantener un fallback léxico si falla la construcción vectorial (`lexical_index.json`).
- Exponer métricas y salud vía endpoints `/health`, `/metrics`, `/ready`.
- Permitir actualización modular (sin romper contratos públicos de la API).

## 3. Arquitectura General
```
	   Usuario (Web / Integraciones)
		    │
	    FastAPI (webchat/main.py)
		    │
	    ┌──────────────────────────────┐
	    │   Motor Conversacional       │
	    │  chatbot/bot.py              │
	    │  - Clasificación intención   │
	    │  - Resolución de enlaces     │
	    │  - RAG / extracción literal  │
	    └──────────────────────────────┘
		    │
	┌────────────────────────────┐
	│   Índice Persistente       │
	│  (Vector + Fallback léxico)│
	│  chatbot/indexer.py        │
	└────────────────────────────┘
		    │
	┌────────────────────────────┐
	│ Catalogación del Sitio     │
	│ site_map.py / crawler.py   │
	│ - routes.txt (preferente)  │
	│ - sitemap + BFS fallback   │
	└────────────────────────────┘
		    │
	Archivos / Data (`data/` persistido)
```

### Componentes Clave
- `chatbot/config.py`: Selección y validación de directorios escribibles, parámetros de indexación y flags de comportamiento.
- `chatbot/site_map.py`: Construcción de manifiestos (`url_manifest.json`, `sections_catalog.json`, `doc_catalog.json`) desde `routes.txt` o crawler + sitemap.
- `chatbot/indexer.py`: Segmentación HTML → secciones; creación del índice vectorial (LlamaIndex + sentence-transformers) o fallback léxico.
- `chatbot/bot.py`: Núcleo de respuesta. Sinónimos, normalización, dynamic link map, extracción literal, clasificación de intentos, cache, PII guard, métricas.
- `chatbot/intents.py`: Clasificador liviano basado en reglas (link, document, specific, general, other).
- `webchat/main.py`: API FastAPI y endpoints públicos.
- `data/storage/*`: Persistencia de índice vectorial (pre-construido en despliegues sin auto-build).
- `tests/`: Pruebas Pytest para misión/visión, intención y comportamiento base.

## 4. Flujo de Datos
1. (Inicio) `startup` de FastAPI invoca `crear_o_cargar_indice()` si `AUTO_BUILD_INDEX=1`.
2. `site_map.build_map_and_catalog()` genera o reusa manifiestos: URLs → secciones → fichas de documentos.
3. `indexer._load_all_html_from_manifest()` obtiene HTML y lo divide por headings (h1–h3) en documentos semánticos + documento completo.
4. Indexación: embeddings HuggingFace (`sentence-transformers/all-MiniLM-L6-v2`) → almacenamiento persistente. Fallback: JSON léxico.
5. Consulta: `responder_pregunta()`
   - Small talk → respuesta inmediata.
   - Intent link/document → resolución directa.
   - Misión/visión/funciones → extracción especializada (snapshot + fetch en vivo) antes de RAG.
   - RAG: dos pasadas (recuperación primaria + recall ampliado) + exact match.
6. Respuesta: literal estructurada o síntesis controlada (`STYLE_SUMMARIZE`).
7. Métricas registradas (latencia, fallbacks, distribución de intenciones).

## 5. Estructura del Repositorio
```
app.py                  # Entrypoint para Spaces
Dockerfile              # Imagen productiva
render.yaml             # Config despliegue Render
requirements.txt        # Dependencias
chatbot/                # Lógica principal
webchat/                # Interfaz y API FastAPI
data/                   # Manifiestos, índices persistidos
tests/                  # Pytest suite
tools/                  # Scripts auxiliares (cobertura de enlaces, etc.)
docs/                   # Documentación
scripts/                # Ejecuciones rápidas/locales
```

## 6. Configuración y Variables de Entorno
| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `EMBEDDING_MODEL` | Modelo embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| `TOP_K` | Resultados primarios | 5 |
| `TOP_K_FALLBACK` | Recall ampliado | 12 |
| `CONFIDENCE_THRESHOLD` | Umbral base | 0.30 |
| `EXACT_MODE` | Modo extractivo (1/0) | 1 |
| `ANSWER_MODE` | `llama` / `extractive` / `gpt` | `llama` |
| `MAX_QUERY_SECONDS` | SLA consulta | 2.5 |
| `AUTO_BUILD_INDEX` | Construcción en runtime | 1 |
| `AUGMENT_CRAWL` | Crawler extra además de routes.txt | 0 |
| `STYLE_SUMMARIZE` | Parafraseo controlado | 1 |
| `STYLE_HYBRID` | Combinar extracto + resumen | 1 |
| `OPENAI_API_KEY` | Activar modo `gpt` controlado | (vacío) |
| `BASE_URL` | Sitio objetivo | `https://www.uesvalle.gov.co` |
| `DATA_DIR` | Directorio escribible runtime | Autodetección |
| `PORT` | Puerto API | 8000 / Spaces 7860 |

### Recomendaciones
- En entornos sin acceso de red (build frío) pre-construir `data/storage` y fijar `AUTO_BUILD_INDEX=0`.
- Para reducir tiempo de arranque en plataformas gratis: desactivar `AUGMENT_CRAWL` y proveer `routes.txt` completo.
- Separar credenciales (si se usa OpenAI) en un gestor de secretos.

## 7. Instalación Local
Requisitos: Python 3.10+ (ideal 3.10 / 3.11), espacio en disco para embeddings (~300MB).
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python -m nltk.downloader punkt stopwords
```
Inicio del servicio:
```powershell
uvicorn webchat.main:app --host 0.0.0.0 --port 8000
```
Verificar salud:
```powershell
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## 8. Construcción y Mantenimiento del Índice
### Estrategias
1. **Online (auto-build)**: `AUTO_BUILD_INDEX=1` → en cada arranque construye si falta `data/storage`. Útil para desarrollo.
2. **Offline (pre-build)**: Ejecutar localmente:
   ```powershell
   python -m webchat.main  # disparará startup
   # Tras crear data/storage, commitear la carpeta
   ```
   Luego desplegar con `AUTO_BUILD_INDEX=0`.

### Actualización de Rutas
1. Editar/actualizar `data/routes.txt` (una URL por línea).  
2. Borrar `data/storage` si se desea reconstrucción limpia.  
3. Reiniciar servicio con `AUTO_BUILD_INDEX=1` (o ejecutar `indexer.crear_o_cargar_indice()` manual).

### Reindexación Periódica
La tarea asíncrona en `startup` programa reindexación cada 24 horas cuando `AUTO_BUILD_INDEX=1`. Ajustar intervalo modificando coroutine.

### Cambio de Modelo Embeddings
1. Establecer `EMBEDDING_MODEL` en entorno (ej.: `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`).
2. Eliminar carpeta `data/storage`.
3. Reconstruir índice. Validar semántica con pruebas específicas.

## 9. Motor Conversacional (Detalles Internos)
### Clasificación de Intención
Reglas en `intents.py`. Labels: `link`, `document`, `specific`, `general`, `other`. Se prioriza:
1. Palabras clave documento → `document`.
2. Patrones navegación → `link`.
3. Tokens interrogativos / requisitos → `specific`.
4. Pocos tokens → `general`. Fallback → `other`.

### Resolución de Enlaces
- Mapa manual + dinámico (`KEYWORD_LINK_MAP` + `DYNAMIC_LINK_MAP`): genera variantes a partir de segmentos de la URL.
- Normalización: tildes, sinónimos (diccionario `SYNONYMS`), plural/singular.
- Prioriza coincidencia directa antes de recuperación semántica.

### Recuperación y Respuesta
1. Pase 1: vector retrieve `TOP_K`.
2. Pase 2: variantes con sinónimos y tokens → `TOP_K_FALLBACK`.
3. Extracción literal: selección de oraciones puntuadas por presencia de tokens y heurísticas anti-boilerplate.
4. Misión/visión/funciones: flujo especializado (snapshot + fetch + headings) antes de RAG.
5. Fallback: sugerencia de secciones relacionadas o mensaje estándar de evidencia insuficiente.

### Mitigaciones de Ruido / Seguridad
- PII guard (detección de correos, teléfonos, identificaciones) → mensaje de advertencia.
- Rate limiting por IP (`/preguntar`): 30 req / 60s.
- Filtrado de bloques de navegación, cookies, marketing, redes sociales.

## 10. Endpoints API (FastAPI)
| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/widget` | GET | HTML del widget embebible. |
| `/preguntar?q=...` | GET | Realiza consulta textual. Respuesta JSON `{respuesta: str}`. |
| `/health` | GET | Estado índice + métricas + cobertura. |
| `/ready` | GET | Texto plano: `ready` o `initializing`. |
| `/metrics` | GET | Métricas formato Prometheus (latencias y contadores). |
| `/version` | GET | Versión actual del servicio. |

## 11. Pruebas Automatizadas
Ejecutar:
```powershell
pytest -q
```
Cobertura mínima esperada:
- Respuestas misión/visión contienen prefijo validado.
- Intenciones clasificadas correctamente (`test_intents.py`).
- Fallback activado para términos inventados.

### Añadir Nuevas Pruebas
1. Crear archivo en `tests/` con prefijo `test_`.
2. Importar funciones de alto nivel (`responder_pregunta`, `classify_intent`).
3. Evitar dependencias de red: si la prueba requiere índice, asegúrate de que `data/storage` exista o simular respuesta con monkeypatch.

## 12. Despliegue
### Docker
Construcción local:
```powershell
docker build -t uesvalle-bot:latest .
docker run -p 8000:7860 -e PORT=7860 uesvalle-bot:latest
```
Buenas prácticas:
- Pre-descargar NLTK y embeddings para evitar timeouts en plataformas sin caché.
- Usar `EXACT_MODE=1` en producción para preservar evidencia literal.

### Render
Gestión en `render.yaml`. Recomendado fijar:
- `AUTO_BUILD_INDEX=0` si se pre-construye índice (reduce tiempo de arranque en plan gratuito).
- Ajustar `PYTHON_VERSION` según compatibilidad de dependencias.

### Hugging Face Spaces
- Entry: `app.py` (reexporta `webchat.main:app`).
- Configurar Secrets: `AUTO_BUILD_INDEX=0` y subir `data/storage` completo.
- Limitar tiempo de respuesta reduciendo `TOP_K_FALLBACK` si recursos son escasos.

## 13. Actualización y Mantenimiento
| Tarea | Procedimiento | Frecuencia |
|-------|---------------|------------|
| Añadir nuevas URLs | Editar `data/routes.txt` y reconstruir índice | Según cambios del sitio |
| Ampliar sinónimos | Actualizar `SYNONYMS` en `bot.py`; añadir pruebas de intención | Trimestral |
| Rotar modelo embeddings | Cambiar `EMBEDDING_MODEL`, reconstruir índice | Según calidad |
| Limpieza de almacenamiento | Revisar tamaños de `hf_cache` y `storage` | Mensual |
| Verificar cobertura | `GET /health` → `coverage_pct` > 85% | Mensual |
| Revisar dependencias | Ejecutar `pip list --outdated` | Mensual |
| Auditoría PII | Revisar patrones de `_PII_PATTERNS` | Semestral |

### Estrategia de Branching (Sugerida)
- `main`: estable producción.
- `develop`: integración continua.
- `feature/*`: nuevas capacidades (ej. nuevo extractor misión/visión).
- `hotfix/*`: correcciones urgentes.
Mantener PRs pequeños y adjuntar resultados de `/metrics` en descripción si impacta rendimiento.

## 14. Observabilidad y Métricas
- `/health`: incluye `index.mode`, `coverage` y contador de documentos.
- `/metrics`: formato Prometheus. Ejemplo de scraping:
  ```text
  bot_total_requests 120
  bot_fallbacks 7
  bot_avg_latency_seconds 0.8421
  bot_intent_total{intent="link"} 35
  ```
Integrar con Grafana / Prometheus en despliegues avanzados.

## 15. Seguridad y Privacidad
- No almacenar preguntas de usuario con PII (solo logs genéricos limitados).
- Sanitizar entradas (normalización y filtrado de scripts ya manejado por BeautifulSoup).
- Revisar periódicamente librerías críticas (`requests`, `llama-index`, `sentence-transformers`).
- Limitar `allow_origins` en CORS para producción al dominio institucional.

## 16. Extensibilidad
### Añadir Nuevo Tipo de Intención
1. Definir patrón en `intents.py` (lista nueva y regla).  
2. Ajustar `bot._detect_intent()` si se requiere priorización.  
3. Agregar rama de lógica en `responder_pregunta()`.  
4. Crear pruebas en `tests/` validando comportamiento.

### Integrar Nuevo Modo de Respuesta
1. Crear función en `openai_client.py` (o módulo nuevo) con limitaciones estrictas.  
2. Añadir valor permitido en `ANSWER_MODE`.  
3. Implementar rama adicional donde se usa `ANSWER_MODE` en `bot.py`.

### Sustituir LlamaIndex
1. Encapsular acceso en funciones `_get_index()`, `_get_engine()`.  
2. Implementar adaptador nuevo retornando objetos equivalentes con `.retrieve()` y `.node.text`.  
3. Mantener interfaz de `responder_pregunta()` sin cambios.

## 17. Troubleshooting
| Síntoma | Causa Probable | Acción |
|---------|----------------|--------|
| Respuestas vacías | Índice no construido | Verificar `data/storage` y `AUTO_BUILD_INDEX` |
| Alta latencia > SLA | Modelo muy pesado / red lenta | Reducir `TOP_K_FALLBACK`, evaluar embeddings más livianos |
| Fallback excesivo | Rutas incompletas | Ampliar `routes.txt`, revisar `coverage_pct` |
| Errores OpenAI | API Key ausente | Establecer `OPENAI_API_KEY` o usar modo extractivo |
| Docker build lento | Instala Torch desde fuente | Fijar versión CPU precompilada en `requirements.txt` |
| Pérdida de misión/visión | Snapshot desactualizado | Actualizar archivo `README_mision_vision.txt` o permitir fetch en vivo |
| Respuestas con datos contacto no deseados | Ajuste heurísticas | Revisar filtros `_CONTACT_TERMS` / `_NAV_NOISE` en `bot.py` |

## 18. Rendimiento y Optimización
- Ajustar chunking: `CHUNK_SIZE=900`, `CHUNK_OVERLAP=120` (balance precisión / tamaño índice).  
- Persistir índices para evitar recomputar embeddings.  
- Reducir `MAX_QUERY_SECONDS` según CPU disponible; si se dispara, priorizar extracción antes que síntesis.

## 19. Estándares de Código
- Idioma: Español en mensajes al usuario; código y comentarios técnicos coherentes.  
- Evitar hardcode de contenido institucional (solo patrones estructurales).  
- Modularidad: ninguna función debe hacer despliegue + negocio al mismo tiempo.  
- Nombrado descriptivo; sin variables de una letra excepto bucles triviales.

## 20. Roadmap Sugerido
| Feature | Beneficio | Estado |
|---------|-----------|--------|
| Cache de vectores incremental | Índices más rápidos en rebuild parcial | Pendiente |
| Integración Prometheus nativa | Observabilidad avanzada | Pendiente |
| Endpoint batch preguntas | Optimizar UX | Pendiente |
| Persistencia de métricas históricas | Análisis de evolución | Pendiente |
| Modelo embeddings multilingüe | Soporte a consultas en inglés | Evaluación |

## 21. Glosario
- **RAG**: Retrieval Augmented Generation, recuperación + síntesis basada en contexto embebido.
- **Fallback Léxico**: Búsqueda simple por aparición de tokens en ausencia de embeddings.
- **Manifiesto**: Lista de todas las URLs rastreadas o declaradas (archivo `url_manifest.json`).
- **Sección**: Fragmento de página derivado de headings h1–h3.
- **Fichas de documentos**: Metadata de enlaces a documentos (PDF, DOC) sin descargar contenido.
- **Exact Mode**: Respuesta compuesta por frases literales recuperadas.
- **Synonyms Mapping**: Diccionario para normalizar variantes lingüísticas del usuario.

## 22. Licenciamiento y Cumplimiento
Verificar que el contenido indexado se limite al dominio institucional autorizado. El bot no redistribuye documentos; sólo cataloga enlaces y fragmentos HTML públicos.

## 23. Checklist Pre-Release
1. `pytest -q` sin fallos.  
2. Cobertura de secciones > 80%.  
3. `data/storage` presente (si `AUTO_BUILD_INDEX=0`).  
4. Latencia promedio (`/metrics`) < 1.2s bajo carga de prueba.  
5. Sin claves expuestas en commit.  
6. Docker image < 1.2GB.  
7. Revisar dependencias críticas para CVEs conocidas.

## 24. Contacto y Escalamiento
- Primer nivel: Mantenimiento interno (revisión rutas, índice).  
- Segundo nivel: Ajuste heurísticas de extracción y rendimiento.  
- Tercer nivel: Cambios estructurales de arquitectura / nuevos modelos.

---
## 25. Proceso de Release y Versionado
- Esquema recomendado: `MAJOR.MINOR.PATCH` (ej. 1.2.3).  
- Incrementar `MAJOR` al cambiar contratos públicos (endpoints o formato de respuesta).  
- Incrementar `MINOR` al añadir funcionalidades backward-compatible (nuevas intenciones, métricas).  
- Incrementar `PATCH` para correcciones y mejoras internas sin cambiar API.  
- Tag de Git: `git tag v1.2.3 && git push --tags`.  
- Mantener changelog en sección inicial del manual o archivo `CHANGELOG.md` (no creado aún).  

## 26. Gestión de Dependencias y Escaneo de Vulnerabilidades
1. Actualizar paquetes: `pip list --outdated` → seleccionar sólo los críticos.  
2. Escaneo CVE: usar servicios como `pip-audit` (añadir opcionalmente a `requirements-dev.txt`).  
3. SBOM: generar con `pip freeze > sbom.txt` para auditoría externa.  
4. Criterios de actualización: seguridad, soporte LTS, mejoras de rendimiento. Evitar saltos mayores simultáneos (Torch + LlamaIndex en el mismo release).  

## 27. Backup y Restore de Datos
Contenido a salvaguardar:  
- `data/storage/` (índice embebido).  
- `data/url_manifest.json`, `data/sections_catalog.json`, `data/doc_catalog.json`.  
- Snapshots manuales (ej. `data/manual/`).  
Procedimiento backup: comprimir `data/` excluyendo `hf_cache` si se puede regenerar:  
```powershell
tar -czf backup-data-$(Get-Date -Format yyyyMMdd).tgz data --exclude "data/hf_cache"
```
Restore: descomprimir sobre nueva instancia antes de arrancar con `AUTO_BUILD_INDEX=0`. Validar `/health` cobertura.  

## 28. Escalabilidad y Pruebas de Carga
- Objetivo inicial: ≤ 1.5s p95 de latencia con 25 RPS.  
- Herramientas sugeridas: `locust`, `k6`.  
Escenario base (k6 JS ejemplo): medir `/preguntar?q=Transparencia` con concurrencia.  
Optimización: reducir `TOP_K_FALLBACK`, activar cache de respuestas frecuentes (`_ANSWER_CACHE`).  
Sharding: separar servicio de indexación si el corpus crece (microservicio dedicado).  

## 29. Logging y Monitoreo Avanzado
- Nivel actual: `INFO` por defecto (`logging.basicConfig(level=logging.INFO)`).  
- Ampliar: estructurar JSON logs (`event`, `latency_ms`, `intent`).  
- En producción: integrar con ELK/Datadog vía stdout.  
- Evitar log de texto completo de páginas para no incrementar tamaño ni exponer datos.  

## 30. Respuesta a Incidentes (Runbook)
| Incidente | Acción Inmediata | Escalamiento |
|-----------|------------------|--------------|
| Índice corrupto | Borrar `data/storage` y reconstruir | Dev Lead |
| Latencia elevada | Revisar métricas `/metrics`; bajar `TOP_K_FALLBACK` | Infra Ops |
| Fallback masivo | Verificar `coverage_pct`; actualizar `routes.txt` | Equipo Contenido |
| Error 500 persistente | Revisar trazas, revertir último release | Dev Lead |
| Respuestas con PII | Ajustar `_PII_PATTERNS`, depurar logs | Seguridad |

Checklist post incidente: documentar causa raíz, acción correctiva y prevención futura en `DECISION_LOG.md` (sugerido).  

## 31. Gestión de Secretos
- Variables sensibles: `OPENAI_API_KEY`.  
- Nunca commitear `.env` con secretos.  
- Uso recomendado: gestor de secretos de plataforma (Render, HF Spaces, GitHub Actions).  
- Rotación: cada 90 días o tras eventos de seguridad.  

## 32. Guía de Integración del Widget
Para incrustar el widget en otro sitio institucional existen dos modalidades principales:

1. **Integración directa por iframe del backend** (cuando se expone el endpoint `/widget` desde un dominio propio).  
2. **Integración por iframe a un despliegue en Hugging Face Spaces** (caso portal UESVALLE actual).

### 32.1 Integración clásica vía `/widget`
Cuando el chatbot se expone desde un dominio propio, el widget puede incrustarse con:

1. Incluir `<iframe src="https://<dominio>/widget" ...>` con altura dinámica.  
2. Configurar CORS si se necesitaran llamadas directas a `/preguntar` desde JS externo (restringir dominio).  
3. Añadir mensaje de accesibilidad (ver sección accesibilidad).  
4. Si se requiere personalización visual, extender `webchat/static/widget.css` manteniendo clases base.  

### 32.2 Integración UESVALLE por iframe (Hugging Face Space)
En el portal institucional de la UESVALLE el chatbot se integra actualmente consumiendo directamente el Space de Hugging Face, posicionando el iframe como widget flotante fijo en la esquina inferior izquierda. Esto es útil cuando el CMS no permite modificar el CSS global.

Snippet utilizado en producción:

```html
<style>
	#uesvalle-chatbot-widget {
		position: fixed !important;
		bottom: 20px !important;
		left: 20px !important;
		z-index: 999999 !important;
		width: 350px !important;
		height: 500px !important;
		border-radius: 10px !important;
		overflow: hidden !important;
		box-shadow: 0 4px 12px rgba(0,0,0,0.25) !important;
		background: transparent !important;
	}

	#uesvalle-chatbot-widget iframe {
		width: 100% !important;
		height: 100% !important;
		border: none !important;
		display: block !important;
	}
</style>

<div id="uesvalle-chatbot-widget">
	<iframe
		src="https://jnarvaez712-uesvalle-chatbot.hf.space"
		frameborder="0"
		title="Chatbot UESVALLE"
		loading="lazy"
	></iframe>
</div>
```

Notas:
- Este bloque debe insertarse lo más cercano posible al cierre de `</body>` del portal que lo consume.
- El uso de `position: fixed` y `z-index` alto garantiza que el widget permanezca visible al hacer scroll y quede por encima del contenido principal.
- `background: transparent` y la ausencia de estilos en contenedores padres evitan paneles blancos o fondos traslúcidos no deseados generados por el CMS.

## 33. Accesibilidad (A11y)
- WCAG 2.1 AA objetivos: contraste, navegación por teclado, etiquetas ARIA en el widget (revisar `widget.html`).  
- Recomendación: añadir `aria-live="polite"` para respuestas del bot.  
- Validar con herramientas: Lighthouse / axe CLI.  

## 34. Internacionalización (i18n)
Actualmente el bot fuerza español. Estrategia futura:  
1. Añadir capa de detección de idioma (langdetect).  
2. Mantener indexación sólo en español inicialmente; para multilingüe, duplicar embeddings con modelo multilingüe (ej. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`).  
3. Clave de configuración `LANG_MODE` (no implementada) para activar traducción controlada.  

## 35. Retención y Eliminación de Datos
- El sistema no almacena historiales persistentes de usuarios (solo memoria ligera en `_CONV_HISTORY`).  
- Política sugerida: no guardar logs de preguntas completas > 60 días; anonimizar IP (hash truncado).  
- Eliminación: script periódico que trunque logs por fecha.  

## 36. Pautas de Contribución (Ampliadas)
1. Abrir issue describiendo motivación y alcance.  
2. Crear rama `feature/<descripcion-corta>`.  
3. Mantener cambios < 500 líneas por PR cuando sea posible.  
4. Incluir pruebas asociadas (nuevas intenciones, nuevos sinónimos).  
5. Actualizar manual si muda parámetros o añade componentes.  
6. Pasar checklist de calidad (lint, pruebas, cobertura mínima).  

## 37. Ruta de Upgrade (Python / Framework / Librerías)
| Componente | Estrategia | Riesgos |
|------------|-----------|---------|
| Python 3.10→3.11 | Probar compatibilidad LlamaIndex y Torch antes | Cambios en ABI de extensiones |
| LlamaIndex | Incrementos menores consecutivos; revisar release notes | Roturas en APIs internas |
| sentence-transformers | Verificar embeddings equivalentes (cosine similarity muestra) | Cambios en normalización |
| Torch | Usar solo CPU build estable; evitar nightly | Tamaño imagen & performance |
| FastAPI | Revisar cambios de dependencias (Starlette) | Middlewares obsoletos |

## 38. Workflow para Incorporar Nuevo Contenido Institucional
1. Obtener nuevas URLs oficiales.  
2. Añadirlas a `data/routes.txt`.  
3. Ejecutar reconstrucción de índice en entorno staging.  
4. Validar cobertura `/health` (`coverage_pct` aumentó).  
5. Escribir pruebas de contenido si aplica (ej.: nueva sección funciones especiales).  
6. Promover cambios a producción tras aprobación.  

## 39. Matriz de Entornos
| Entorno | AUTO_BUILD_INDEX | Datos Persistidos | Objetivo |
|---------|------------------|-------------------|----------|
| Dev local | 1 | Opcional (recreable) | Iteración rápida |
| Staging | 1 | Sí (validar rebuilds) | Validación pre-release |
| Producción | 0 | Sí (pre-construido) | Arranque veloz |
| DR (recuperación) | 0 | Réplica cifrada | Continuidad operativa |

## 40. Metodología de Pruebas de Rendimiento
1. Definir escenario representativo (preguntas mezcla: enlaces + misión + contenido).  
2. Ejecutar 3 corridas de carga (warm, medida, confirmación).  
3. Registrar p50, p95, tasa de fallbacks.  
4. Umbrales: p95 < 2s, fallbacks < 15%, errores 5xx < 1%.  

## 41. Quality Gates (CI/CD)
- Ejecutar `pytest`.  
- Escaneo CVE (opcional).  
- Verificar tamaño imagen Docker < umbral definido.  
- Validar que manual cambió si versiones subieron.  
- Despliegue condicional si p95 latencia en staging aceptable.  

## 42. Endurecimiento de Seguridad (Hardening Checklist)
| Ítem | Estado |
|------|--------|
| CORS restringido a dominio oficial | Pendiente producción |
| Headers seguros (X-Frame-Options, X-Content-Type-Options) | Añadir en middleware |
| Rate limit activo | Sí |
| Validación entrada (normalización) | Sí |
| Escaneo dependencias | Manual (automatizar) |
| Logs sin PII | Sí (guard de PII) |

## 43. Registro de Riesgos y Decisiones (Risk & Decision Log)
Mantener archivo `DECISION_LOG.md` (sugerido) con formato:  
`YYYY-MM-DD | Tema | Decisión | Alternativas consideradas | Riesgo | Mitigación`.  
Riesgos actuales: dependencia fuerte de disponibilidad del sitio para fetch en vivo; tamaño creciente de índice → plan de partición.  

## 44. Apéndice: Scripts Útiles
| Script | Propósito |
|--------|-----------|
| `scripts/quick_test_bot.py` | Prueba rápida de `responder_pregunta`. |
| (Sugerido) `tools/rebuild_index.py` | Forzar reconstrucción limpia (no implementado). |
| `tools/verify_link_coverage.py` | Validar cobertura de enlaces respecto a catálogo. |

Ejemplo (script rebuild sugerido):
```python
# tools/rebuild_index.py
from chatbot.indexer import crear_o_cargar_indice
if __name__ == "__main__":
	crear_o_cargar_indice()
	print("Índice reconstruido")
```

## 45. Próximos Pasos de Madurez
- Implementar CI completo (GitHub Actions) con jobs: lint, test, build, scan.  
- Añadir almacenamiento de métricas históricas (Prometheus + Grafana).  
- Integrar monitoreo sintético (cada 5 min consulta clave).  
- Automatizar rotación de snapshots misión/visión.  

---
Fin del Manual del Desarrollador. Mantén este documento versionado y actualiza el encabezado de versión y fecha en cada cambio relevante.

## Anexo A. Política de Push Limpio (Hugging Face / Producción)
Para evitar rechazos en el push (ej. por archivos binarios como `*.pyc`), se adopta la siguiente política:
- Nunca versionar bytecode Python ni directorios `__pycache__/`.
- Validar antes de cada push: `python tools/verify_clean_push.py` (retorna código != 0 si algo falla).
- Forzar reconstrucción del índice sin binarios si se reescribió historia (usar `git filter-repo` preferido; si no, `git filter-branch` cuidadosamente).

Checklist rápido previo a `git push`:
1. `git status` sin archivos compilados.
2. `python tools/verify_clean_push.py` → `[OK]`.
3. Tamaño de archivos individuales < 7MB (ajustable con `--max-size`).
4. `.gitignore` contiene patrones `__pycache__/` y `*.pyc`.

Hook pre-commit sugerido (no versionado, colocar en `.git/hooks/pre-commit`):
```bash
#!/usr/bin/env bash
python tools/verify_clean_push.py || exit 1
echo "Pre-commit verificación limpia OK"
```

Si Hugging Face rechaza el push por binarios rastreados históricamente:
1. Instalar `git-filter-repo` (recomendado) o usar `git filter-branch` solo si no hay alternativa.
2. Reescribir historia eliminando `*.pyc`.
3. `git push <remote> <branch>:main --force-with-lease`.
4. Notificar al equipo y documentar en `DECISION_LOG.md`.

Script disponible: `tools/verify_clean_push.py` (ver comentarios internos para ampliar reglas).


