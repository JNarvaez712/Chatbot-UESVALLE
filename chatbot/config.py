# chatbot/config.py

# ===== NLP / Indexación =====
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# ===== Rutas de datos =====
DOCS_DIR = "data/documentos"
STORAGE_DIR = "data/storage"
TMP_DOC_DIR = "data/tmp_docs"
SNAPSHOT_DIR = "data/web_snapshot"
URL_MANIFEST_PATH = "data/url_manifest.json"

# ===== Sitio objetivo =====
BASE_URL = "https://www.uesvalle.gov.co"
ALLOWED_DOMAINS = ["uesvalle.gov.co", "www.uesvalle.gov.co"]

# ===== Crawler / Red =====
USER_AGENT = "Mozilla/5.0 (compatible; UESVALLEBot/1.2; +https://www.uesvalle.gov.co/)"
HTTP_TIMEOUT = 12
RESPECT_ROBOTS = True
CRAWL_MAX_DEPTH = 6
MAX_PAGINAS_RASTREO = 5000     # límite superior (HTML)
MAX_DOCUMENTOS_BUSQUEDA = 800  # documentos enlazados
MAX_DOC_BYTES = 25 * 1024 * 1024  # 25MB
