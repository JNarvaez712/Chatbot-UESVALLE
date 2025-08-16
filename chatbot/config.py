# chatbot/config.py
# ================== Configuración general del chatbot UESVALLE ==================

# ===== NLP / Indexación =====
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5
TOP_K_FALLBACK = 12
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# ===== Rutas de datos =====
DOCS_DIR = ""                                # ⛔ No indexar documentos locales
STORAGE_DIR = "data/storage"
SNAPSHOT_DIR = "data/web_snapshot"
URL_MANIFEST_PATH = "data/url_manifest.json"
DOC_CATALOG_PATH = "data/doc_catalog.json"           # Catálogo de documentos (PDF/DOC…)
SECTIONS_CATALOG_PATH = "data/sections_catalog.json" # Catálogo de secciones HTML

# Archivo con TODAS las rutas (una URL por línea)
ROUTES_FILE_PATH = "data/routes.txt"                 # <— coloca aquí tu .txt
USE_EXTERNAL_ROUTES = True                           # usar routes.txt si existe

# ===== Sitio objetivo =====
BASE_URL = "https://www.uesvalle.gov.co"
ALLOWED_DOMAINS = ["uesvalle.gov.co", "www.uesvalle.gov.co"]

# ===== Crawler / Red =====
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 20
RESPECT_ROBOTS = False         # puedes volverlo True si lo requieres

# Cobertura del mapeo (si se usa crawler tradicional)
CRAWL_MAX_DEPTH = 6
MAX_PAGINAS_RASTREO = 2000

# Extensiones tratadas como “documentos” (no se descargan; sólo se catalogan)
DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")

# Umbral de confianza para respuestas semánticas
CONFIDENCE_THRESHOLD = 0.30


