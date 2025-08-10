# chatbot/indexer.py
import json
import os

import requests
from bs4 import BeautifulSoup
from llama_index.core import (
    VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_indices_from_storage
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from chatbot.config import (
    EMBEDDING_MODEL, DOCS_DIR, STORAGE_DIR, CHUNK_SIZE, CHUNK_OVERLAP,
    URL_MANIFEST_PATH, HTTP_TIMEOUT
)
from chatbot.site_map import build_url_manifest
from chatbot.document_loader import cargar_documentos_web as cargar_docs_archivos

def _configure_llama_settings():
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)

def _load_web_pages_from_manifest() -> list[Document]:
    # Asegura que el manifiesto esté actualizado SIEMPRE antes de leer
    urls = build_url_manifest()  # <-- mapeo automático en cada reindexación

    docs = []
    for u in urls:
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            if "text/html" in r.headers.get("Content-Type", "").lower():
                txt = _html_to_text(r.text)
                if txt.strip():
                    docs.append(Document(text=txt, metadata={"source": u}))
        except Exception:
            continue
    print(f"🌐 Páginas HTML cargadas: {len(docs)}")
    # Guarda un snapshot simple del recuento
    try:
        with open(URL_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"🔎 Manifiesto: {data.get('count')} rutas totales")
    except Exception:
        pass
    return docs

def _build_index(docs):
    _configure_llama_settings()
    index = VectorStoreIndex.from_documents(docs, embed_model=Settings.embed_model)
    index.storage_context.persist(STORAGE_DIR)
    print("✅ Índice guardado en", STORAGE_DIR)
    return index

def crear_o_cargar_indice():
    if not os.path.exists(STORAGE_DIR) or not os.listdir(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

        docs_local = SimpleDirectoryReader(DOCS_DIR).load_data() if os.path.exists(DOCS_DIR) else []
        docs_web = _load_web_pages_from_manifest()      # ← TODAS las rutas HTML
        docs_arch = cargar_docs_archivos()              # ← documentos adjuntos

        documentos = docs_local + docs_web + docs_arch
        if not documentos:
            documentos = [Document(text="Sin documentos aún.", metadata={"source": "placeholder"})]

        print(f"🧠 Generando índice con {len(documentos)} documentos…")
        return _build_index(documentos)

    print("📚 Cargando índice existente…")
    _configure_llama_settings()
    storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index_list = load_indices_from_storage(storage, embed_model=Settings.embed_model)
    return index_list[0]

if __name__ == "__main__":
    _ = crear_o_cargar_indice()
    print("🎉 ¡Índice listo!")



