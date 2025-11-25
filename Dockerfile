# --- Base ligera con Python 3.10 (CPU) ---
FROM python:3.10-slim AS base

# Evita bytecode y buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instala dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Crea directorio de la app
WORKDIR /app

# Copia requirements e instala
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# ⚠️ PREINSTALAR NLTK DATA en ruta propia y exponerla por NLTK_DATA
RUN mkdir -p /app/nltk_data
ENV NLTK_DATA=/app/nltk_data
# Pre-descarga de tokenizers que usa LlamaIndex
RUN python -m nltk.downloader -d /app/nltk_data punkt punkt_tab stopwords

# Copia el código del proyecto
COPY . /app

# Crear usuario no-root
RUN useradd -ms /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

# Puerto por defecto en Spaces
ENV PORT=7860

# Comando de arranque (usa PORT si está definido)
CMD ["sh", "-c", "uvicorn webchat.main:app --host 0.0.0.0 --port ${PORT:-7860}"]

