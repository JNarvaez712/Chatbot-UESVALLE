# webchat/main.py
import asyncio
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chatbot.bot import responder_pregunta, _get_index, _get_engine, _get_retriever
from chatbot.indexer import crear_o_cargar_indice

app = FastAPI(title="Chatbot UESVALLE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringe luego al dominio oficial
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="webchat/static"), name="static")
templates = Jinja2Templates(directory="webchat/templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uesvalle-bot")

@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"

@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    return templates.TemplateResponse("widget.html", {"request": request})

@app.get("/preguntar")
async def preguntar(q: str):
    try:
        if not q or not q.strip():
            return {"respuesta": "Por favor, escribe tu pregunta."}
        respuesta = responder_pregunta(q)
        if not respuesta or len(respuesta.strip()) < 20:
            respuesta = ("Lo siento, no tengo información suficiente para responder con certeza. "
                         "Intenta formular la pregunta con más detalle o revisa la sección de Atención al Ciudadano.")
        logger.info("Q: %s | ok", q[:160])
        return {"respuesta": respuesta}
    except Exception:
        logger.exception("Error en /preguntar")
        return JSONResponse(
            content={"respuesta": "Ocurrió un error procesando tu solicitud. Intenta más tarde."},
            status_code=500,
        )

@app.on_event("startup")
async def startup():
    logger.info("Inicializando índice (con mapeo automático de rutas)…")
    crear_o_cargar_indice()   # <- esto dispara build_url_manifest internamente
    # precalentar
    _get_index(); _get_retriever(); _get_engine()
    logger.info("Índice y motor listos.")

    async def tarea_reindexacion():
        while True:
            try:
                logger.info("🔁 Reindexación automática iniciada (map + index)…")
                crear_o_cargar_indice()  # <- vuelve a mapear TODAS las rutas y reindexa
                # limpiar caches para tomar el nuevo índice
                _get_index.cache_clear()
                _get_retriever.cache_clear()
                _get_engine.cache_clear()
                _get_index(); _get_retriever(); _get_engine()
                logger.info("✅ Reindexación completada.")
            except Exception:
                logger.exception("⚠️ Error durante la reindexación automática")
            await asyncio.sleep(60 * 60 * 24)  # cada 24h

if __name__ == "__main__":
    uvicorn.run("webchat.main:app", host="127.0.0.1", port=8000, reload=True)
