# chatbot/web_loader.py
import hashlib
import os
from pathlib import Path
from llama_index.core.schema import Document
from chatbot.crawler import rastrear_sitio
from chatbot.config import SNAPSHOT_DIR

# Asegurar snapshot dir ESCRIBIBLE
Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)

def _snap_path(url: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{hashlib.md5(url.encode()).hexdigest()}.txt")

def _changed(url: str, new_text: str) -> bool:
    p = _snap_path(url)
    if not os.path.exists(p):
        return True
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip() != new_text.strip()
    except Exception:
        return True

def _save(url: str, text: str):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)  # ⬅️ asegurar carpeta
    with open(_snap_path(url), "w", encoding="utf-8") as f:
        f.write(text)

def cargar_documentos_web():
    print("🔍 Rastreando sitio UESVALLE…")
    paginas = rastrear_sitio()
    docs = []
    for p in paginas:
        u, t = p["url"], p["text"]
        if _changed(u, t):
            print(f"🔄 Cambios: {u}")
            _save(u, t)
            docs.append(Document(text=t, metadata={"source": u}))
        else:
            print(f"✅ Sin cambios: {u}")
    return docs

