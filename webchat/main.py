# webchat/main.py

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from chatbot.bot import responder_pregunta
from chatbot.indexer import crear_o_cargar_indice
import asyncio
import uvicorn

app = FastAPI()

# Servir archivos estáticos (CSS, JS)
app.mount("/static", StaticFiles(directory="webchat/static"), name="static")

# Cargar templates HTML (el widget)
templates = Jinja2Templates(directory="webchat/templates")

# Ruta principal del widget
@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    return templates.TemplateResponse("widget.html", {"request": request})

# Endpoint para preguntas desde el frontend
@app.get("/preguntar")
async def preguntar(q: str):
    try:
        respuesta = responder_pregunta(q)

        if not respuesta or len(respuesta.strip()) < 20:
            respuesta = (
                "Lo siento, no tengo información suficiente para responder a esa consulta con certeza."
            )

        return {"respuesta": respuesta}

    except Exception as e:
        print(f"❌ Error en el endpoint /preguntar: {e}")
        return JSONResponse(
            content={"respuesta": "Ocurrió un error procesando tu solicitud. Intenta más tarde."},
            status_code=500
        )

# Reindexación automática cada 24h
@app.on_event("startup")
async def reindex_periodicamente():
    async def tarea_reindexacion():
        while True:
            print("🔁 Reindexación automática iniciada...")
            try:
                crear_o_cargar_indice()
                print("✅ Reindexación completada.")
            except Exception as e:
                print(f"⚠️ Error durante la reindexación automática: {e}")
            await asyncio.sleep(60 * 60 * 24)  # Esperar 24 horas

    asyncio.create_task(tarea_reindexacion())

# Para ejecución local
if __name__ == "__main__":
    uvicorn.run("webchat.main:app", host="127.0.0.1", port=8000, reload=True)
