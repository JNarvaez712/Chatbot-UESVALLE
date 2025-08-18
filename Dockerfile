# Imagen base estable (CPU) con Python 3.10
FROM python:3.10-slim

# Evitar cachés y mejorar logs
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias de sistema mínimas (certificados + libstdc++ por si alguna wheel lo requiere)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalarlos
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar todo el proyecto
COPY . .

# Puerto que usará el Space (Hugging Face usa 7860 por defecto)
ENV PORT=7860
EXPOSE 7860

# Comando de arranque (tu app FastAPI)
# Si tu app lee $PORT, perfecto; si no, se fija explícitamente aquí:
CMD ["uvicorn", "webchat.main:app", "--host", "0.0.0.0", "--port", "7860"]
