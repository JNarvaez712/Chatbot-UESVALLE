# chatbot/indexer.py
import json, os, requests, time
from bs4 import BeautifulSoup
from bs4.element import Tag
from llama_index.core import VectorStoreIndex, StorageContext, load_indices_from_storage
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from chatbot.config import (
    EMBEDDING_MODEL, STORAGE_DIR, CHUNK_SIZE, CHUNK_OVERLAP,
    URL_MANIFEST_PATH, DOC_CATALOG_PATH, HTTP_TIMEOUT,
    HF_CACHE_DIR, LEXICAL_INDEX_PATH, SECTIONS_CATALOG_PATH
)
from chatbot.site_map import build_map_and_catalog

# Estado global del índice para endpoints de salud / cobertura
INDEX_STATUS = {
    "mode": None,              # "vector" | "lexical" | "unknown"
    "last_started": None,      # timestamp epoch
    "last_finished": None,     # timestamp epoch
    "doc_count": 0,            # total documentos (secciones + fichas)
    "sections_count": 0,       # número de secciones HTML
    "urls_count": 0,           # número de URLs en manifiesto
}

def get_index_status() -> dict:
    """Devuelve copia del estado del índice (para /health)."""
    return INDEX_STATUS.copy()

def get_coverage_summary() -> dict:
    """Calcula métricas de cobertura simples: URLs sin secciones, porcentaje de cobertura.
    No intenta ser perfecto; sirve como indicador rápido de calidad del mapeo.
    """
    urls = []
    sections = []
    try:
        if os.path.exists(URL_MANIFEST_PATH):
            with open(URL_MANIFEST_PATH, "r", encoding="utf-8") as f:
                urls = json.load(f).get("urls", [])
        if os.path.exists(SECTIONS_CATALOG_PATH):
            with open(SECTIONS_CATALOG_PATH, "r", encoding="utf-8") as f:
                sections = [it.get("url") for it in json.load(f).get("items", [])]
    except Exception:
        pass
    urls_set = set(urls)
    sections_set = set(sections)
    without_sections = sorted(u for u in urls_set if u not in sections_set)
    coverage_pct = (100.0 * (len(urls_set) - len(without_sections)) / len(urls_set)) if urls_set else 0.0
    return {
        "urls_total": len(urls_set),
        "sections_total": len(sections_set),
        "urls_without_sections": without_sections[:40],  # limitar lista
        "urls_without_sections_count": len(without_sections),
        "coverage_pct": round(coverage_pct, 2),
    }

# ---------- Utilidad: asegurar carpeta padre antes de escribir ----------
def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _configure():
    # Forzar variables de entorno (por si el import se hizo antes)
    os.environ.setdefault("HF_HOME", HF_CACHE_DIR)
    os.environ.setdefault("TRANSFORMERS_CACHE", HF_CACHE_DIR)
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", HF_CACHE_DIR)
    # Modelo de embeddings con cache_folder explícito
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBEDDING_MODEL,
        cache_folder=HF_CACHE_DIR,
    )
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]): 
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)

# ------------------ División de página por secciones (h1-h3) -----------------

_BLOCK_TAGS = {
    "p","li","ul","ol","div","section","article","table","thead","tbody","tr","td","th",
    "dl","dt","dd","blockquote"
}

def _page_title_and_h1(soup: BeautifulSoup) -> tuple[str, str]:
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    h1 = ""
    h1_tag = soup.find("h1")
    if h1_tag:
        h1 = " ".join(h1_tag.get_text(" ", strip=True).split())
    return title, h1

def _collect_section_text(start_heading: Tag, level: int) -> str:
    parts: list[str] = []
    # Recorremos en orden del documento después del heading
    for el in start_heading.next_elements:
        if isinstance(el, Tag):
            name = el.name.lower()
            if name in ("h1","h2","h3"):
                next_level = int(name[1]) if len(name) == 2 and name[1].isdigit() else 6
                if next_level <= level:
                    break
            if name in _BLOCK_TAGS:
                txt = el.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
    text = " ".join(parts)
    return text

def _remove_boilerplate(soup: BeautifulSoup) -> None:
    """Elimina elementos de interfaz y avisos que contaminan el contenido (cookies, banners)."""
    # Preferir <main> si existe: trabajaremos sobre él; removemos lo demás
    main = soup.find("main")
    if main:
        # quita navegación/bordes generales
        for tag in soup.find_all(["header","footer","nav","aside"]):
            tag.decompose()
    # eliminar avisos de cookies/consentimiento por atributos típicos
    candidates = []
    for el in soup.find_all(True):
        attrs = " ".join([
            el.get("id", ""),
            " ".join(el.get("class", []) if isinstance(el.get("class"), list) else []),
            el.get("role", ""),
            el.get("aria-label", ""),
        ]).lower()
        if any(k in attrs for k in ("cookie","cookies","gdpr","consent","consentimiento","aviso","privacy","privacidad")):
            candidates.append(el)
    for el in candidates:
        try:
            el.decompose()
        except Exception:
            pass

def _split_into_sections(html: str, url: str) -> list[Document]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    _remove_boilerplate(soup)
    page_title, h1 = _page_title_and_h1(soup)

    # Si hay <main>, tomar headings de dentro; sino, de todo el documento
    scope = soup.find("main") or soup
    headings = scope.find_all(["h1","h2","h3"]) or []
    docs: list[Document] = []
    if not headings:
        # Sin headings claros: devolvemos una sola sección con todo el texto (limpio)
        txt = soup.get_text("\n", strip=True)
        if txt.strip():
            docs.append(Document(
                text=txt,
                metadata={"source": url, "kind": "page_full", "page_title": page_title or h1, "h1": h1}
            ))
        return docs

    for h in headings:
        title = " ".join(h.get_text(" ", strip=True).split())
        if not title:
            continue
        level = int(h.name[1])
        body = _collect_section_text(h, level)
        section_text = (title + "\n" + body).strip() if body else title
        # descartar fragmentos de aviso de cookies o muy pequeños
        if any(w in section_text.lower() for w in ("cookie","cookies","gdpr","consentimiento","privacidad","estadística","marketing")):
            continue
        if len(section_text) < 40:
            continue
        anchor = h.get("id") or h.get("name")
        source_with_anchor = f"{url}#{anchor}" if anchor else url
        docs.append(Document(
            text=section_text,
            metadata={
                "source": source_with_anchor,
                "kind": "section",
                "page_title": page_title or h1,
                "h1": h1,
                "section_title": title,
                "section_level": level,
            }
        ))
    # Agregar documento completo como contexto adicional (page_full) para RAG
    full_txt = soup.get_text("\n", strip=True)
    if full_txt and len(full_txt) > 200:
        docs.append(Document(
            text=full_txt,
            metadata={
                "source": url,
                "kind": "page_full",
                "page_title": page_title or h1,
                "h1": h1,
            }
        ))
    return docs

def _load_all_html_from_manifest() -> list[Document]:
    try:
        with open(URL_MANIFEST_PATH, "r", encoding="utf-8") as f:
            urls = json.load(f).get("urls", [])
        print(f"🔎 Manifiesto: {len(urls)} URLs.")
    except Exception:
        urls, _, _ = build_map_and_catalog()

    docs: list[Document] = []
    for u in urls:
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            if "text/html" in r.headers.get("Content-Type", "").lower():
                secs = _split_into_sections(r.text, u)
                if secs:
                    docs.extend(secs)
        except Exception as e:
            print(f"⚠️ Error HTML {u}: {e}")

    if not docs and urls:
        try:
            r = requests.get(urls[0], headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
            if "text/html" in r.headers.get("Content-Type", "").lower():
                secs = _split_into_sections(r.text, urls[0])
                if secs:
                    docs.extend(secs)
                    print("ℹ️ Fallback: se indexó la home por secciones.")
        except Exception:
            pass

    print(f"🌐 Secciones HTML indexadas: {len(docs)}")
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
    try:
        _configure()
        _ensure_dir(STORAGE_DIR)  # ⬅️ asegurar carpeta de persistencia
        index = VectorStoreIndex.from_documents(docs, embed_model=Settings.embed_model)
        index.storage_context.persist(STORAGE_DIR)
        print("✅ Índice vectorial guardado en", STORAGE_DIR)
        INDEX_STATUS["mode"] = "vector"
        return index
    except Exception as e:
        # Fallback: guardar un índice léxico básico (lista de documentos con metadata)
        print(f"⚠️ Falló creación índice vectorial: {e}\n➡️ Creando fallback léxico simple.")
        payload = []
        for d in docs:
            payload.append({"text": d.text, "metadata": getattr(d, "metadata", {})})
        with open(LEXICAL_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"count": len(payload), "docs": payload}, f, ensure_ascii=False)
        print("✅ Fallback léxico guardado en", LEXICAL_INDEX_PATH)
        INDEX_STATUS["mode"] = "lexical"
        return None

def crear_o_cargar_indice():
    # Marca inicio
    INDEX_STATUS["last_started"] = time.time()

    # Siempre (re)construir manifiestos/catalogos desde routes.txt o crawler
    urls, docs_catalog, sections_catalog = build_map_and_catalog() or ([], [], [])
    INDEX_STATUS["urls_count"] = len(urls)
    INDEX_STATUS["sections_count"] = len(sections_catalog)

    if not os.path.exists(STORAGE_DIR) or not os.listdir(STORAGE_DIR):
        _ensure_dir(STORAGE_DIR)

        docs_pages = _load_all_html_from_manifest()
        docs_cards = _load_doc_cards_from_catalog()
        documentos = docs_pages + docs_cards

        if not documentos:
            documentos = [Document(text="Contenido básico del sitio UESVALLE.", metadata={"source": "placeholder"})]

        print(f"🧠 Generando índice con {len(documentos)} documentos…")
        INDEX_STATUS["doc_count"] = len(documentos)
        idx = _build_index(documentos)
        INDEX_STATUS["last_finished"] = time.time()
        return idx

    print("📚 Cargando índice existente…")
    try:
        _configure()
        storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        index_list = load_indices_from_storage(storage, embed_model=Settings.embed_model)
        # Recalcular doc_count aproximado leyendo storage (número de nodes)
        try:
            INDEX_STATUS["doc_count"] = len(index_list[0].docstore.docs)
        except Exception:
            pass
        INDEX_STATUS["mode"] = "vector"
        INDEX_STATUS["last_finished"] = time.time()
        return index_list[0]
    except Exception as e:
        print(f"⚠️ No se pudo cargar índice vectorial: {e}")
        if os.path.exists(LEXICAL_INDEX_PATH):
            print("➡️ Usando fallback léxico.")
            INDEX_STATUS["mode"] = "lexical"
            # Aproximar doc_count desde lexical_index.json
            try:
                with open(LEXICAL_INDEX_PATH, "r", encoding="utf-8") as f:
                    INDEX_STATUS["doc_count"] = json.load(f).get("count", 0)
            except Exception:
                pass
            INDEX_STATUS["last_finished"] = time.time()
            return None
        raise

if __name__ == "__main__":
    _ = crear_o_cargar_indice()
    print("🎉 ¡Índice listo!")



