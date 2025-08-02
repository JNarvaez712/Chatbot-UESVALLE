# chatbot/web_loader.py

import os
import hashlib
from pathlib import Path
from llama_index.core.schema import Document
from chatbot.crawler import rastrear_sitio

# Directorio donde se guardan las versiones previas (snapshots)
SNAPSHOT_DIR = "data/web_snapshot"
Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)

def _get_snapshot_path(url: str) -> str:
    # Usamos un hash del URL como nombre de archivo
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(SNAPSHOT_DIR, f"{url_hash}.txt")

def _content_has_changed(url: str, new_text: str) -> bool:
    snapshot_path = _get_snapshot_path(url)
    if not os.path.exists(snapshot_path):
        return True
    with open(snapshot_path, "r", encoding="utf-8") as f:
        old_text = f.read()
    return old_text.strip() != new_text.strip()

def _save_snapshot(url: str, text: str):
    with open(_get_snapshot_path(url), "w", encoding="utf-8") as f:
        f.write(text)

def cargar_documentos_web():
    """
    Ejecuta el crawler para indexar automáticamente toda la web de UESVALLE.
    Solo devuelve contenido nuevo o actualizado.
    """
    print("🔍 Rastreando sitio UESVALLE...")
    paginas = rastrear_sitio()

    nuevos_documentos = []

    for pagina in paginas:
        url = pagina["url"]
        texto = pagina["text"]

        if _content_has_changed(url, texto):
            print(f"🔄 Se detectaron cambios en: {url}")
            _save_snapshot(url, texto)

            # Creamos un documento compatible con llama-index
            doc = Document(text=texto, metadata={"source": url})
            nuevos_documentos.append(doc)
        else:
            print(f"✅ Sin cambios: {url}")

    return nuevos_documentos
