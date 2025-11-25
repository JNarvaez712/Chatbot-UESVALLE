# chatbot/config.py
# ================== Configuración general del chatbot UESVALLE ==================
import os
import tempfile
from pathlib import Path

# ---------- Utilidad: elegir un directorio de datos ESCRIBIBLE ----------
def _pick_writable_data_dir() -> str:
    """
    Intenta en este orden:
      1) DATA_DIR (si se pasó por entorno)
      2) ./data (si es escribible)
      3) ~/.cache/uesvalle-bot
      4) /tmp/uesvalle-bot
      5) Un tmp aleatorio del sistema
    Devuelve la primera ruta donde podamos escribir.
    """
    candidates = [
        os.environ.get("DATA_DIR"),
        os.path.join(os.getcwd(), "data"),
        os.path.join(Path.home(), ".cache", "uesvalle-bot"),
        "/tmp/uesvalle-bot",
    ]
    for cand in candidates:
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            test_file = os.path.join(cand, ".write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
            return cand
        except Exception:
            continue
    # Último recurso: un tmp aleatorio
    return tempfile.mkdtemp(prefix="uesvalle-")

# Directorio ESCRIBIBLE para runtime (manifiestos, snapshots, storage…)
DATA_DIR = _pick_writable_data_dir()

# Directorio SOLO-LECTURA del repo (donde suele estar data/routes.txt)
REPO_DATA_DIR = str((Path(__file__).resolve().parents[1] / "data").resolve())

# ===== NLP / Indexación =====
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K = int(os.environ.get("TOP_K", 5))
TOP_K_FALLBACK = int(os.environ.get("TOP_K_FALLBACK", 12))
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# ===== Rutas de datos =====
DOCS_DIR = ""  # ⛔ No indexar documentos locales
STORAGE_DIR = os.path.join(DATA_DIR, "storage")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "web_snapshot")
URL_MANIFEST_PATH = os.path.join(DATA_DIR, "url_manifest.json")
DOC_CATALOG_PATH = os.path.join(DATA_DIR, "doc_catalog.json")           # Catálogo de documentos (PDF/DOC…)
SECTIONS_CATALOG_PATH = os.path.join(DATA_DIR, "sections_catalog.json") # Catálogo de secciones HTML
LEXICAL_INDEX_PATH = os.path.join(DATA_DIR, "lexical_index.json")       # Fallback léxico simple

# Archivo con TODAS las rutas (una URL por línea)
# Se intentará primero aquí (por si el usuario lo sube en runtime),
# y si no existe, se buscará en REPO_DATA_DIR/routes.txt
ROUTES_FILE_PATH = os.path.join(DATA_DIR, "routes.txt")
ROUTES_FILE_REPO_FALLBACK = os.path.join(REPO_DATA_DIR, "routes.txt")
USE_EXTERNAL_ROUTES = True

# ===== Cache de modelos HF/Transformers =====
HF_CACHE_DIR = os.path.join(DATA_DIR, "hf_cache")
os.makedirs(HF_CACHE_DIR, exist_ok=True)
# Variables de entorno estándar para forzar el cache
os.environ.setdefault("HF_HOME", HF_CACHE_DIR)
os.environ.setdefault("TRANSFORMERS_CACHE", HF_CACHE_DIR)
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", HF_CACHE_DIR)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

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
RESPECT_ROBOTS = False  # puedes volverlo True si lo requieres

# Cobertura del mapeo (si se usa crawler tradicional)
CRAWL_MAX_DEPTH = 6
MAX_PAGINAS_RASTREO = 2000

# Extensiones tratadas como “documentos” (no se descargan; sólo se catalogan)
DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")

# Umbral de confianza para respuestas semánticas
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", 0.30))

# Modo de respuestas exactas (extractivas). Por defecto DESACTIVADO
# (el bot vuelve a responder de forma generativa basada en el índice).
# Modo extractivo activado por defecto (por requerimiento de respuestas 100% basadas en evidencia del sitio)
EXACT_MODE = os.environ.get("EXACT_MODE", "1").lower() in {"1","true","on","yes"}

# Selección del modo de respuesta para contenido: 'llama' (generativo clásico),
# 'extractive' (literal) o 'gpt'. Por defecto 'llama'.
ANSWER_MODE = os.environ.get("ANSWER_MODE", "llama").strip().lower()
MAX_QUERY_SECONDS = float(os.environ.get("MAX_QUERY_SECONDS", 2.5))  # SLA objetivo de respuesta

# Control de construcción automática del índice en runtime. En entornos como
# Hugging Face Spaces conviene desactivar (AUTO_BUILD_INDEX=0) y pre-comitear
# la carpeta `data/storage` para evitar timeouts de inicio.
AUTO_BUILD_INDEX = os.environ.get("AUTO_BUILD_INDEX", "1").lower() in {"1","true","on","yes"}

# Crawling extendido: si existe routes.txt pero se desea añadir automáticamente
# páginas nuevas no listadas, establece AUGMENT_CRAWL=1. Hará un crawler BFS
# para descubrir URLs adicionales y fusionarlas.
AUGMENT_CRAWL = os.environ.get("AUGMENT_CRAWL", "0").lower() in {"1","true","on","yes"}

# Estilo mejorado: si STYLE_SUMMARIZE=1 el bot intenta redactar mejor
# (paráfrasis controlada) usando solo las oraciones recuperadas como evidencia.
STYLE_SUMMARIZE = os.environ.get("STYLE_SUMMARIZE", "1").lower() in {"1","true","on","yes"}
# Estilo híbrido (resumen + extracto literal + fuentes). Si false devuelve sólo
# el extracto (con posible estilización si STYLE_SUMMARIZE=1).
STYLE_HYBRID = os.environ.get("STYLE_HYBRID", "1").lower() in {"1","true","on","yes"}

# OpenAI (opcional)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

# ===== (Valores usados por document_loader si llegas a activarlo) =====
TMP_DOC_DIR = os.path.join(DATA_DIR, "tmp_docs")
MAX_DOCUMENTOS_BUSQUEDA = 500
MAX_DOC_BYTES = 8 * 1024 * 1024  # 8 MiB


