# chatbot/document_loader.py
# (Este módulo es opcional en tu flujo actual; lo dejamos compatible y seguro)
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from llama_index.core import SimpleDirectoryReader

from chatbot.config import (
    BASE_URL, USER_AGENT, TMP_DOC_DIR, MAX_DOCUMENTOS_BUSQUEDA,
    HTTP_TIMEOUT, MAX_DOC_BYTES, ALLOWED_DOMAINS
)

HEADERS = {"User-Agent": USER_AGENT}
VALID_CT = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument",
    "application/msword",
    "application/vnd.ms-excel",
)

def _is_internal(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "" or any(host.endswith(d) for d in ALLOWED_DOMAINS)

def _looks_doc_by_ext(url: str) -> bool:
    u = url.lower()
    return u.endswith((".pdf", ".docx", ".xlsx", ".xls", ".doc"))

def _head_ok(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if int(r.headers.get("Content-Length", "0")) > MAX_DOC_BYTES:
            return False
        ctype = r.headers.get("Content-Type", "").lower()
        return any(ct in ctype for ct in VALID_CT)
    except Exception:
        return False

def _download(url: str, destino: str):
    r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    if int(r.headers.get("Content-Length", "0")) > MAX_DOC_BYTES:
        raise RuntimeError("archivo demasiado grande")
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)  # ⬅️ asegurar carpeta
    with open(destino, "wb") as f:
        f.write(r.content)
    print(f"📄 Descargado: {url}")

def _discover_docs(max_docs: int = MAX_DOCUMENTOS_BUSQUEDA):
    print("🔍 Descubriendo documentos enlazados…")
    encontrados, visitadas, por_visitar = set(), set(), [BASE_URL]

    while por_visitar and len(encontrados) < max_docs:
        url = por_visitar.pop(0)
        if url in visitadas:
            continue
        visitadas.add(url)
        try:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"].split("#")[0])
                if not _is_internal(link):
                    continue
                if _looks_doc_by_ext(link) and _head_ok(link):
                    encontrados.add(link)
                else:
                    if link not in visitadas:
                        por_visitar.append(link)
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")

    print(f"✅ Documentos candidatos: {len(encontrados)}")
    return sorted(encontrados)

def cargar_documentos_web():
    Path(TMP_DOC_DIR).mkdir(parents=True, exist_ok=True)
    urls = _discover_docs()
    rutas = []

    for url in urls:
        nombre = url.split("/")[-1].split("?")[0]
        ruta = os.path.join(TMP_DOC_DIR, nombre)
        if not os.path.exists(ruta):
            try:
                _download(url, ruta)
            except Exception as e:
                print(f"⚠️ No se pudo descargar {url}: {e}")
                continue
        rutas.append(ruta)

    if rutas:
        print("📚 Procesando documentos descargados…")
        return SimpleDirectoryReader(TMP_DOC_DIR).load_data()

    print("ℹ️ No hay documentos para procesar.")
    return []
