# chatbot/web_loader.py
import hashlib
import os
from pathlib import Path

from llama_index.core.schema import Document

from chatbot.crawler import rastrear_sitio
from chatbot.config import SNAPSHOT_DIR

Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)


def _snapshot_path(url: str) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(SNAPSHOT_DIR, f"{url_hash}.txt")


def _content_has_changed(url: str, new_text: str) -> bool:
    path = _snapshot_path(url)
    if not os.path.exists(path):
        return True
    with open(path, "r", encoding="utf-8") as f:
        old_text = f.read()
    return old_text.strip() != new_text.strip()


def _save_snapshot(url: str, text: str):
    with open(_snapshot_path(url), "w", encoding="utf-8") as f:
        f.write(text)


def cargar_documentos_web():
    """
    Rastrear sitio y devolver Document() solo para páginas nuevas o modificadas.
    """
    print("🔍 Rastreando sitio UESVALLE...")
    paginas = rastrear_sitio()
    nuevos_documentos = []

    for pagina in paginas:
        url = pagina["url"]
        texto = pagina["text"]
        if _content_has_changed(url, texto):
            print(f"🔄 Cambios detectados: {url}")
            _save_snapshot(url, texto)
            nuevos_documentos.append(Document(text=texto, metadata={"source": url}))
        else:
            print(f"✅ Sin cambios: {url}")

    return nuevos_documentos

