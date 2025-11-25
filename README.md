---
title: Chatbot UESVALLE
emoji: 💬
colorFrom: blue
colorTo: green
sdk: docker
app_file: Dockerfile
pinned: false
---

## Logo/Avatar del chatbot

Para mostrar el personaje (UESLY) en la interfaz web:

1. Copia la imagen proporcionada a `webchat/static/img/uesly.png`.
	- Recomendado: PNG 320×320 con fondo transparente.
2. Inicia/recarga la app. Verás el logo en el encabezado del chat y como avatar en los mensajes del bot.

Si quieres usar otro nombre de archivo o ruta, actualiza las referencias en:

- `webchat/templates/widget.html` (id `chatLogo`)
- `webchat/static/widget.js` (función `createBotRow`)

## Cómo funciona (resumen)

- Mapeo del sitio: construye `data/url_manifest.json`, `data/sections_catalog.json` y `data/doc_catalog.json` a partir de `data/routes.txt` (preferido) o crawler (fallback).
- Indexación semántica: genera un índice vectorial mezclando páginas HTML y "fichas" de documentos.
- Motor de respuestas: 
	- Intención "link": devuelve UN único enlace oficial a la sección solicitada.
	- Intención "document": devuelve documentos relacionados (PDF/formatos) por similitud de texto.
		- Intención "specific/general": modo EXTRACTIVO: devuelve fragmentos literales del sitio (sin parafrasear, sin enlaces y sin "Fuente oficial").
	- Fallback: sugiere secciones relacionadas cuando no hay evidencia suficiente.

	## Cobertura de enlaces (100%)

	El chatbot logra cobertura completa (100% de las URLs en `data/routes.txt`) mediante dos capas de mapeo de palabras clave a enlaces:

	1. `KEYWORD_LINK_MAP` (manual): claves críticas y frecuentes (misión, visión, PQR, presupuesto, inicio, etc.). Siempre tiene prioridad: si una palabra está aquí no se sobrescribe con dinámicos.
	2. `DYNAMIC_LINK_MAP` (automático): se genera al importar `chatbot.bot` leyendo `data/routes.txt`.

	### Algoritmo dinámico
	Para cada URL:
	- Se valida dominio (`uesvalle.gov.co` o `sites.google.com/uesvalle.gov.co`).
	- Se extraen segmentos del path decodificados (se ignoran vacíos y puramente numéricos).
	- Se normalizan (minúsculas) y se filtran segmentos genéricos usando `_DYN_STOP` (categorías contenedoras como `publicaciones`, `documentos`, `procesos`, artículos, preposiciones, etc.).
	- Se generan variantes:
		- Último segmento significativo.
		- Últimos dos segmentos.
		- Cadena completa de todos los segmentos significativos.
		- Cada segmento individual significativo.
		- Expansiones para prefijos `plan-`, `manual-` (se agregan variantes con prefijo separado: `plan X`, `manual X`).
		- Expansión ligera de sinónimos (reemplazos definidos en `SYNONYMS`).
	- Se añaden variantes compuestas padre + hoja cuando el último segmento es genérico y fue filtrado (`formatos`, `instructivos`, `manuales`, `procedimientos`, `guías`, `listas`, `listados`). Ej.: `direccionamiento estrategico formatos`, `gestion de calidad procedimientos`.
	- Fallback: si tras el filtrado una URL queda sin ninguna variante, se crea una clave de cadena completa con todos los segmentos (incluyendo genéricos) para garantizar cobertura.
	- Se evita colisión: no se añade una variante si ya existe en `KEYWORD_LINK_MAP` o fue usada antes para otra URL.
	- Página principal: keywords explícitos (`inicio`, `portal uesvalle`, `sitio uesvalle`, etc.).

	### Verificación de cobertura
	Script de verificación: `tools/verify_link_coverage.py`.

	Ejecutar:
	```bash
	python tools/verify_link_coverage.py
	```

	Salida esperada (ejemplo):
	```
	Total rutas: 302
	Rutas cubiertas: 302
	Rutas sin keywords: 0
	```

	### Mantenibilidad
	- Añadir nuevas rutas: editar `data/routes.txt` y reiniciar el servicio (se reconstruye `DYNAMIC_LINK_MAP` en el arranque).
	- Ajustar filtros: modificar `_DYN_STOP` en `chatbot/bot.py` si se quieren incluir o excluir categorías.
	- Forzar nueva palabra clave manual: añadirla directamente a `KEYWORD_LINK_MAP` para priorizarla.

	### Uso en la respuesta
	Cuando la intención detecta que la consulta coincide con una clave (manual o dinámica), el bot devuelve el enlace único asociado. Si varias claves apuntaran a la misma URL (sinónimo/variantes), se mantiene una sola respuesta.

## Endpoints

- `GET /widget` UI del chat
- `GET /preguntar?q=...` respuesta del bot (con rate limit por IP)
- `GET /health` vivo
- `GET /ready` listo (índice cargado)
- `GET /version` versión
- `GET /metrics` métricas simples (estilo Prometheus)

## Variables de entorno útiles

- `EMBEDDING_MODEL` (por defecto `sentence-transformers/all-MiniLM-L6-v2`)
- `TOP_K`, `TOP_K_FALLBACK` (por defecto 5 y 12)
- `CONFIDENCE_THRESHOLD` (por defecto 0.30)
- `EXACT_MODE` (por defecto `1`): si está activo, respuestas `specific/general` son extractivas y sólo contienen texto literal recuperado.
- `ANSWER_MODE` (`llama`|`extractive`|`gpt`, por defecto `llama`):
	- `llama`: respuesta generativa clásica usando el índice (comportamiento por defecto).
	- `extractive`: respuesta literal desde el texto recuperado.
	- `gpt`: síntesis con OpenAI siguiendo el contexto (RAG).
- `OPENAI_API_KEY`: clave para usar el modo `gpt`.
- `OPENAI_MODEL` (por defecto `gpt-4o-mini`).
- `DATA_DIR` (directorio escribible para catálogos e índice)

## Seguridad y privacidad

El bot filtra números de identificación, teléfonos y correos en la entrada para desalentar el envío de datos personales. Evita compartir PII. El bot responde únicamente con información del sitio oficial de la UESVALLE.

## Ejecutar localmente

1. Instala dependencias:
	```bash
	pip install -r requirements.txt
	```
2. Ejecuta la API:
	```bash
	uvicorn webchat.main:app --host 0.0.0.0 --port 8000
	```
3. Abre `http://localhost:8000/widget`.

### Indexación y estilo de respuestas

1. Prepara `data/routes.txt` con una URL por línea (HTTPS, sin parámetros). Ejemplo:
	```
	https://www.uesvalle.gov.co/
	https://www.uesvalle.gov.co/publicaciones/2/mision-y-vision/
	https://www.uesvalle.gov.co/publicaciones/1561/plan-anual-de-adquisiciones/
	```
2. (Opcional) Activa descubrimiento adicional: `set AUGMENT_CRAWL=1` (Windows PowerShell: `$env:AUGMENT_CRAWL="1"`).
3. Construye / actualiza el índice:
	```bash
	python -m chatbot.indexer
	```
4. Variables de estilo disponibles:
	- `EXACT_MODE=1`: respuestas basadas en evidencia literal primero.
	- `STYLE_SUMMARIZE=1`: reescritura formal clara usando SOLO evidencia recuperada.
	- `STYLE_HYBRID=1`: combina resumen + extracto literal + fuentes (URLs) del sitio.
	- Para respuestas estrictamente literales (sin reescritura), usa `STYLE_SUMMARIZE=0 STYLE_HYBRID=0 ANSWER_MODE=extractive`.
5. Prueba rápida en consola:
	```bash
	python - <<'PY'
from chatbot.bot import responder_pregunta
for q in ["que es la uesvalle?","mision y vision","plan anual de adquisiciones","PQRSD"]:
	 print(q, "->\n", responder_pregunta(q), "\n---")
PY
	```

## Pruebas

```bash
pytest -q
```

## Despliegue (Docker)

El Dockerfile crea un contenedor con usuario no-root y respeta `PORT` en tiempo de ejecución:

```bash
docker build -t uesvalle-bot .
docker run -p 8000:8000 -e PORT=8000 uesvalle-bot

# Modo GPT opcional
# docker run -p 8000:8000 -e PORT=8000 -e ANSWER_MODE=gpt -e OPENAI_API_KEY=tu_api_key uesvalle-bot
```

## Despliegue en Hugging Face Spaces

Para evitar el error de timeout de arranque ("Launch timed out, workload was not healthy") sigue estos pasos:

1. Pre-construye el índice localmente y commitea `data/storage`:
	```bash
	python -m chatbot.indexer  # genera data/storage
	git add data/storage
	git commit -m "prebuild index"
	git push
	```
2. Desactiva el auto-build en el Space añadiendo variable: `AUTO_BUILD_INDEX=0`.
3. El Space detectará `app.py` que reexporta el FastAPI existente (`webchat.main.app`).
4. Verifica que no haya archivos `.incomplete` dentro de `data/hf_cache`; si existen, elimina y reconstruye local para asegurar caché limpia.
5. Mantén el modelo ligero (`sentence-transformers/all-MiniLM-L6-v2`). Evita cambiar a modelos grandes que retrasen la instalación.
6. Si necesitas regenerar el índice, hazlo offline y vuelve a commitear la carpeta `data/storage`; mantén `AUTO_BUILD_INDEX=0` para arranque rápido.
7. Opcional: si el Space tarda instalando `torch`, puedes quitar el pin de versión en `requirements.txt` para usar la versión preinstalada.

En modo degradado (sin índice y con `AUTO_BUILD_INDEX=0`), el bot sólo devolverá enlaces y mensajes básicos; pre-construye el índice para funcionalidad completa.

### Nota sobre caches y pesos grandes

No subas al repositorio los pesos de modelos ni el cache de Hugging Face (`data/hf_cache/`). Mantenerlos versionados provoca rechazos del push (>10 MiB) y aumenta el tiempo de clonación en el Space. Mantén en `.gitignore`:

```
data/hf_cache/
venv/
```

Si accidentalmente se commiteó `data/hf_cache/`, se debe purgar del historial (ej. `git filter-repo` o `git filter-branch`) antes de volver a hacer push; eliminar sólo del working tree no elimina los blobs grandes ya registrados en commits previos.

Para usar otro modelo embedding más pesado, preferiblemente:
- Añade la descarga dinámica al arranque (sin commitear pesos).
- Considera Git LFS si realmente necesitas versionar archivos grandes (>10 MiB), aunque para Spaces normalmente es mejor descargar en runtime.