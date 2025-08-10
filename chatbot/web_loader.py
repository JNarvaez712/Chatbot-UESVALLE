# chatbot/web_loader.py
import hashlib
import os
from pathlib import Path
from llama_index.core.schema import Document
from chatbot.crawler import rastrear_sitio
from chatbot.config import SNAPSHOT_DIR

Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)

def _snap_path(url: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{hashlib.md5(url.encode()).hexdigest()}.txt")

def _changed(url: str, new_text: str) -> bool:
    p = _snap_path(url)
    if not os.path.exists(p):
        return True
    return open(p, "r", encoding="utf-8").read().strip() != new_text.strip()

def _save(url: str, text: str):
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

