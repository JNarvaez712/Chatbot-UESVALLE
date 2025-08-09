# webchat/main.py
import asyncio
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chatbot.bot import responder_pregunta, _get_index, cargar_motor_preguntas
from chatbot.indexer import crear_o_cargar_indice

app = FastAPI(title="Chatbot UESVALLE")

# CORS: restringe luego al dominio oficial de UESVALLE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos y templates
app.mount("/static", StaticFiles(directory="webchat/static"), name="static")
templates = Jinja2Templates(directory="webchat/templates")

# Logging
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
            respuesta = (
                "Lo siento, no tengo información suficiente para responder con certeza. "
                "Intenta formular la pregunta con más detalle o revisa la sección de Atención al Ciudadano."
            )

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
    # 1) construir/cargar índice (bloqueante)
    logger.info("Inicializando índice...")
    crear_o_cargar_indice()

    # 2) precalentar motor para bajar latencia del primer request
    _get_index()
    cargar_motor_preguntas()
    logger.info("Índice y motor listos.")

    # 3) reindexación cada 24 horas
    async def tarea_reindexacion():
        while True:
            try:
                logger.info("🔁 Reindexación automática iniciada...")
                crear_o_cargar_indice()
                # invalidar caches y recalentar
                _get_index.cache_clear()
                cargar_motor_preguntas.cache_clear()
                _get_index()
                cargar_motor_preguntas()
                logger.info("✅ Reindexación completada.")
            except Exception:
                logger.exception("⚠️ Error durante la reindexación automática")
            await asyncio.sleep(60 * 60 * 24)

    asyncio.create_task(tarea_reindexacion())


if __name__ == "__main__":
    uvicorn.run("webchat.main:app", host="127.0.0.1", port=8000, reload=True)
