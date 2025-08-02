# webchat/main.py

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from chatbot.bot import responder_pregunta
from chatbot.indexer import crear_o_cargar_indice
import asyncio
import uvicorn

app = FastAPI()

# Archivos estáticos (CSS, JS del widget)
app.mount("/static", StaticFiles(directory="webchat/static"), name="static")

# Cargar plantillas HTML
templates = Jinja2Templates(directory="webchat/templates")

# Ruta del widget visual
@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    return templates.TemplateResponse("widget.html", {"request": request})

# Endpoint de preguntas
@app.get("/preguntar")
async def preguntar(q: str):
    respuesta = responder_pregunta(q)
    return {"respuesta": respuesta}

# 🚀 Tarea automática: Reindexar cada 24 horas
@app.on_event("startup")
async def reindex_periodicamente():
    async def tarea_reindexacion():
        while True:
            print("🔁 Reindexación automática iniciada...")
            crear_o_cargar_indice()
            print("✅ Reindexación completada. Próxima en 24h.")
            await asyncio.sleep(60 * 60 * 24)  # 24 horas

    asyncio.create_task(tarea_reindexacion())

# Para ejecutar localmente
if __name__ == "__main__":
    uvicorn.run("webchat.main:app", host="127.0.0.1", port=8000, reload=True)

