# app.py (Hugging Face Spaces entrypoint)
# Reexpone el FastAPI existente sin costo de indexado adicional.
from webchat.main import app  # HF Spaces detecta variable 'app'

# Nota: Establecer en Secrets o Variables del Space:
#   AUTO_BUILD_INDEX=0  (para evitar crawl/index en tiempo de arranque)
# Pre-comitear carpeta data/storage con índice construido offline.
