# chatbot/document_loader.py
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from llama_index.core import SimpleDirectoryReader

from chatbot.config import (
    BASE_URL,
    USER_AGENT,
    TMP_DOC_DIR,
    MAX_DOCUMENTOS_BUSQUEDA,
    HTTP_TIMEOUT,
)

HEADERS = {"User-Agent": USER_AGENT}
VALID_EXTS = (".pdf", ".docx", ".xlsx", ".xls")


def _es_documento(url: str) -> bool:
    return url.lower().endswith(VALID_EXTS)


def _es_enlace_interno(url: str) -> bool:
    netloc = urlparse(url).netloc
    return netloc == "" or "uesvalle.gov.co" in netloc


def _descargar_documento(url: str, destino: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        with open(destino, "wb") as f:
            f.write(r.content)
        print(f"📄 Descargado: {url}")
    except Exception as e:
        print(f"⚠️ Error al descargar {url}: {e}")


def encontrar_documentos_en_web(max_docs: int = MAX_DOCUMENTOS_BUSQUEDA):
    print("🔍 Buscando documentos en el sitio web de UESVALLE...")
    visitadas = set()
    por_visitar = [BASE_URL]
    encontrados = []

    while por_visitar and len(visitadas) < max_docs:
        url = por_visitar.pop(0)
        if url in visitadas:
            continue

        try:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"].split("#")[0])
                if _es_enlace_interno(link):
                    if _es_documento(link):
                        if link not in encontrados:
                            encontrados.append(link)
                    elif link not in visitadas:
                        por_visitar.append(link)
        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")

        visitadas.add(url)

    print(f"✅ Documentos encontrados: {len(encontrados)}")
    return encontrados


def cargar_documentos_web():
    Path(TMP_DOC_DIR).mkdir(parents=True, exist_ok=True)
    urls = encontrar_documentos_en_web()
    rutas_locales = []

    for url in urls:
        nombre_archivo = url.split("/")[-1].split("?")[0]
        ruta_local = os.path.join(TMP_DOC_DIR, nombre_archivo)
        if not os.path.exists(ruta_local):
            _descargar_documento(url, ruta_local)
        rutas_locales.append(ruta_local)

    if rutas_locales:
        print("📚 Procesando documentos descargados...")
        reader = SimpleDirectoryReader(TMP_DOC_DIR)
        return reader.load_data()

    print("ℹ️ No hay documentos nuevos para procesar.")
    return []
