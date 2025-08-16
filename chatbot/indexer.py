# chatbot/indexer.py
import json, os, requests
from bs4 import BeautifulSoup
from llama_index.core import VectorStoreIndex, StorageContext, load_indices_from_storage
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from chatbot.config import (
    EMBEDDING_MODEL, STORAGE_DIR, CHUNK_SIZE, CHUNK_OVERLAP,
    URL_MANIFEST_PATH, DOC_CATALOG_PATH, HTTP_TIMEOUT
)
from chatbot.site_map import build_map_and_catalog

def _configure():
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]): tag.decompose()
    return soup.get_text(separator="\n", strip=True)

def _load_all_html_from_manifest() -> list[Document]:
    try:
        with open(URL_MANIFEST_PATH, "r", encoding="utf-8") as f:
            urls = json.load(f).get("urls", [])
        print(f"🔎 Manifiesto: {len(urls)} URLs.")
    except Exception:
        urls, _, _ = build_map_and_catalog()

    docs = []
    for u in urls:
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            if "text/html" in r.headers.get("Content-Type", "").lower():
                soup = BeautifulSoup(r.text, "html.parser")
                title = (soup.title.string.strip() if soup.title and soup.title.string else "")
                h1 = ""
                h1_tag = soup.find("h1")
                if h1_tag:
                    h1 = " ".join(h1_tag.get_text(" ", strip=True).split())
                txt = _html_to_text(r.text)
                if txt.strip():
                    docs.append(Document(
                        text=txt,
                        metadata={"source": u, "kind": "page", "page_title": title or h1, "h1": h1}
                    ))
        except Exception as e:
            print(f"⚠️ Error HTML {u}: {e}")

    if not docs and urls:
        try:
            r = requests.get(urls[0], headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            if "text/html" in r.headers.get("Content-Type", "").lower():
                txt = _html_to_text(r.text)
                if txt.strip():
                    docs.append(Document(text=txt, metadata={"source": urls[0], "kind": "page"}))
                    print("ℹ️ Fallback: se indexó la home.")
        except Exception:
            pass

    print(f"🌐 Páginas HTML indexadas: {len(docs)}")
    return docs

def _load_doc_cards_from_catalog() -> list[Document]:
    try:
        with open(DOC_CATALOG_PATH, "r", encoding="utf-8") as f:
            items = json.load(f).get("items", [])
        print(f"🔎 Catálogo de documentos: {len(items)} entradas.")
    except Exception:
        _, items, _ = build_map_and_catalog()

    docs = []
    for it in items:
        txt = (
            f"Título de la página: {it.get('page_title','')}\n"
            f"H1: {it.get('h1','')}\n"
            f"Sección: {it.get('section','')}\n"
            f"Descripción/Contexto: {it.get('context','')}\n"
            f"Texto del enlace: {it.get('link_text','')}\n"
            f"Ubicación del documento: {it.get('doc_url','')}\n"
            f"Página donde está publicado: {it.get('from_page','')}\n"
        )
        docs.append(Document(
            text=txt,
            metadata={
                "source": it.get("doc_url",""),
                "kind": "doc_card",
                "from_page": it.get("from_page",""),
                "section": it.get("section",""),
                "link_text": it.get("link_text",""),
                "page_title": it.get("page_title",""),
            },
        ))
    print(f"📎 Fichas de documentos creadas: {len(docs)}")
    return docs

def _build_index(docs):
    _configure()
    index = VectorStoreIndex.from_documents(docs, embed_model=Settings.embed_model)
    index.storage_context.persist(STORAGE_DIR)
    print("✅ Índice guardado en", STORAGE_DIR)
    return index

def crear_o_cargar_indice():
    # Siempre (re)construir manifiestos/catalogos desde routes.txt o crawler
    build_map_and_catalog()

    if not os.path.exists(STORAGE_DIR) or not os.listdir(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

        docs_pages = _load_all_html_from_manifest()
        docs_cards = _load_doc_cards_from_catalog()
        documentos = docs_pages + docs_cards

        if not documentos:
            documentos = [Document(text="Contenido básico del sitio UESVALLE.", metadata={"source": "placeholder"})]

        print(f"🧠 Generando índice con {len(documentos)} documentos…")
        return _build_index(documentos)

    print("📚 Cargando índice existente…")
    _configure()
    storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index_list = load_indices_from_storage(storage, embed_model=Settings.embed_model)
    return index_list[0]

if __name__ == "__main__":
    _ = crear_o_cargar_indice()
    print("🎉 ¡Índice listo!")



