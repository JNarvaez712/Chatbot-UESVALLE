# chatbot/document_loader.py

import os
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document
from bs4 import BeautifulSoup

BASE_URL = "https://www.uesvalle.gov.co"
TMP_DOC_DIR = "data/tmp_docs"
VALID_EXTS = [".pdf", ".docx", ".xlsx", ".xls"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UESVALLEBot/1.0; +https://www.uesvalle.gov.co/)"
}

def _es_documento(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in VALID_EXTS)

def _es_enlace_interno(url: str):
    netloc = urlparse(url).netloc
    return netloc == "" or "uesvalle.gov.co" in netloc

def _descargar_documento(url: str, destino: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        with open(destino, "wb") as f:
            f.write(r.content)
        print(f"📄 Descargado: {url}")
    except Exception as e:
        print(f"⚠️ Error al descargar {url}: {e}")

def encontrar_documentos_en_web():
    print("🔍 Buscando documentos en el sitio web de UESVALLE...")
    visitadas = set()
    por_visitar = [BASE_URL]
    encontrados = []

    while por_visitar and len(visitadas) < 50:
        url = por_visitar.pop(0)
        if url in visitadas:
            continue

        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Buscar enlaces
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"].split("#")[0])
                if _es_enlace_interno(link):
                    if _es_documento(link):
                        if link not in encontrados:
                            encontrados.append(link)
                    elif link not in visitadas:
                        por_visitar.append(link)
        except Exception as e:
            print(f"⚠️ Error al acceder a {url}: {e}")

        visitadas.add(url)

    print(f"✅ Se encontraron {len(encontrados)} documentos.")
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

    # Leer todos los archivos descargados con SimpleDirectoryReader
    if rutas_locales:
        print("📚 Procesando documentos descargados...")
        reader = SimpleDirectoryReader(TMP_DOC_DIR)
        docs = reader.load_data()
        return docs
    else:
        print("ℹ️ No hay documentos nuevos para procesar.")
        return []
