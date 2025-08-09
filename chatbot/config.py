# chatbot/config.py

# Modelo de embeddings (open‑source, rápido y liviano)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Directorios de datos
DOCS_DIR = "data/documentos"
STORAGE_DIR = "data/storage"

# Crawler
BASE_URL = "https://www.uesvalle.gov.co"
USER_AGENT = "Mozilla/5.0 (compatible; UESVALLEBot/1.0; +https://www.uesvalle.gov.co/)"

# Descarga temporal de archivos de la web (PDF/DOCX/XLSX…)
TMP_DOC_DIR = "data/tmp_docs"

# Snapshot del contenido HTML para detectar cambios
SNAPSHOT_DIR = "data/web_snapshot"

# Límites y tiempos
MAX_PAGINAS_RASTREO = 30       # páginas HTML a rastrear por pasada
MAX_DOCUMENTOS_BUSQUEDA = 50   # documentos enlazados a descubrir
HTTP_TIMEOUT = 10              # segundos

# Recuperación semántica
TOP_K = 4                      # documentos similares a recuperar por pregunta

