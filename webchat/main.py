# webchat/main.py
import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,   # ⬅️ para redirigir "/"
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chatbot.bot import responder_pregunta, get_metrics   # ⬅️ quitamos _get_index/_get_engine/_get_retriever
from chatbot.indexer import crear_o_cargar_indice, get_index_status, get_coverage_summary
from chatbot.config import AUTO_BUILD_INDEX
from chatbot.bot import get_metrics

app = FastAPI(title="Chatbot UESVALLE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restringe al dominio en prod si quieres
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="webchat/static"), name="static")
templates = Jinja2Templates(directory="webchat/templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uesvalle-bot")

# -------- NUEVO: Home que redirige al widget --------
@app.get("/", include_in_schema=False)
async def home():
    # Redirige la raíz a la UI del widget
    return RedirectResponse(url="/widget")

_READY = {"index": False}

@app.get("/health")
async def health():
    status = get_index_status()
    metrics = get_metrics()
    coverage = get_coverage_summary()
    return {
        "status": "ok",
        "index": status,
        "metrics": metrics,
        "coverage": coverage,
    }

@app.get("/ready", response_class=PlainTextResponse)
async def ready():
    return "ready" if _READY["index"] else "initializing"

@app.get("/version", response_class=PlainTextResponse)
async def version():
    return "uesvalle-bot 1.0.0"

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    m = get_metrics()
    lines = [
        f"bot_total_requests {m.get('total',0)}",
        f"bot_fallbacks {m.get('fallbacks',0)}",
        f"bot_avg_latency_seconds {m.get('avg_latency',0):.4f}",
    ]
    for intent, cnt in m.get("intent", {}).items():
        lines.append(f"bot_intent_total{{intent=\"{intent}\"}} {cnt}")
    return "\n".join(lines)

@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    return templates.TemplateResponse("widget.html", {"request": request})

_RATE: dict[str, list[float]] = {}
_RATE_LIMIT = 30  # reqs / 60s por IP

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.get("/preguntar")
async def preguntar(q: str, request: Request):
    try:
        if not q or not q.strip():
            return {"respuesta": "Por favor, escribe tu pregunta."}
        # Rate limiting básico por IP
        now = asyncio.get_event_loop().time()
        ip = _client_ip(request)
        wins = _RATE.setdefault(ip, [])
        cutoff = now - 60
        # limpia ventana
        _RATE[ip] = [t for t in wins if t >= cutoff]
        if len(_RATE[ip]) >= _RATE_LIMIT:
            return JSONResponse(content={"respuesta": "Has superado el límite de consultas. Intenta de nuevo en un minuto."}, status_code=429)
        _RATE[ip].append(now)
        respuesta = responder_pregunta(q)
        if not respuesta or len(respuesta.strip()) < 12:
            respuesta = ("No tengo evidencia suficiente para responder con certeza. "
                         "Intenta con más contexto o revisa Atención al Ciudadano.")
        logger.info("{\"event\":\"ask\",\"ip\":%r,\"q\":%r}", ip, q[:160])
        return {"respuesta": respuesta}
    except Exception:
        logger.exception("Error en /preguntar")
        return JSONResponse(
            content={"respuesta": "Ocurrió un error procesando tu solicitud. Intenta más tarde."},
            status_code=500,
        )

@app.on_event("startup")
async def startup():
    if AUTO_BUILD_INDEX:
        logger.info("Inicializando índice (mapeo automático de rutas + catálogo)…")
        try:
            crear_o_cargar_indice()
            _READY["index"] = True
            logger.info("Índice listo.")
        except Exception:
            logger.exception("Fallo inicializando índice; el bot funcionará en modo degradado.")
    else:
        # Modo degradado: requiere que la carpeta data/storage ya exista (pre-comiteada)
        exists = os.path.exists("data/storage") and os.listdir("data/storage")
        _READY["index"] = bool(exists)
        if _READY["index"]:
            logger.info("Inicio rápido: índice pre-existente cargado (AUTO_BUILD_INDEX desactivado).")
        else:
            logger.warning("Inicio rápido sin índice: responde solo con enlaces y mensajes básicos. Pre-construye el índice offline.")

    # Reindexación automática solo si se permite auto-build
    if AUTO_BUILD_INDEX:
        async def tarea_reindexacion():
            while True:
                try:
                    logger.info("🔁 Reindexación automática iniciada (map + index)…")
                    crear_o_cargar_indice()
                    logger.info("✅ Reindexación completada.")
                except Exception:
                    logger.exception("⚠️ Error durante la reindexación automática")
                await asyncio.sleep(60 * 60 * 24)
        asyncio.create_task(tarea_reindexacion())

if __name__ == "__main__":
    # Hugging Face Spaces expone $PORT; si corres local, usa 8000.
    import os
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("webchat.main:app", host="0.0.0.0", port=port, reload=False)
