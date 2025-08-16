# chatbot/bot.py
# -----------------------------------------------------------------------------
# Motor de QA + Resolución determinista de enlaces a secciones del sitio
# -----------------------------------------------------------------------------
# - Para preguntas de ENLACES (link/ruta/sección), busca únicamente en
#   data/sections_catalog.json (catálogo generado por el crawler).
#   => Devuelve la URL EXACTA de la página (sin inventar).
# - Para preguntas de CONTENIDO, usa un índice semántico con recall de 2 pasos.
# -----------------------------------------------------------------------------

from functools import lru_cache
import json
import os
import re
import unicodedata
import difflib
from urllib.parse import urlparse

from llama_index.core import load_indices_from_storage, StorageContext
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from chatbot.config import (
    EMBEDDING_MODEL,
    STORAGE_DIR,
    TOP_K,
    TOP_K_FALLBACK,
    CONFIDENCE_THRESHOLD,
    SECTIONS_CATALOG_PATH,
)

# ============================ utilidades de texto ============================

STOPWORDS_ES = {
    "de","la","que","el","en","y","a","los","del","se","las","por","un","para","con","no","una","su","al",
    "lo","como","mas","más","pero","sus","le","ya","o","este","si","sí","porque","esta","entre","cuando",
    "muy","sin","sobre","tambien","también","me","hasta","hay","donde","dónde","quien","quién","desde",
    "todo","nos","durante","todos","uno","les","ni","contra","otros","ese","eso","ante","ellos","e","esto",
    "mi","mí","antes","algunos","que","qué","unos","yo","otro","otras","otra","ir","seccion","sección",
    "enlace","link","ruta","url","acceder","pagina","página","al","la","el"
}

def _norm(s: str) -> str:
    """Normaliza: sin tildes, minúsculas, espacios compactados."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()

def _tokens(s: str) -> set[str]:
    """Tokens sin stopwords, útiles para coincidencia."""
    return {t for t in re.findall(r"[a-z0-9\-]+", _norm(s)) if t not in STOPWORDS_ES and len(t) > 2}

def _path_tokens(u: str) -> set[str]:
    """Tokens de la ruta /path/de/la/url (útil para detectar secciones)."""
    p = urlparse(u).path.strip("/")
    toks = set()
    for part in p.split("/"):
        if not part:
            continue
        toks |= set(re.findall(r"[a-z0-9]+", part.replace("-", " ")))
    return toks

def _path_depth(u: str) -> int:
    p = urlparse(u).path.strip("/")
    return 0 if not p else len([x for x in p.split("/") if x])

def _similarity(a: str, b: str) -> float:
    """Score combinado: similitud difusa + jaccard de tokens."""
    ta, tb = _tokens(a), _tokens(b)
    jacc = (len(ta & tb) / len(ta | tb)) if (ta and tb) else 0.0
    fuzzy = difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    return 0.6 * fuzzy + 0.4 * jacc

# ============================ índice semántico ===============================

@lru_cache(maxsize=1)
def _get_index():
    """Carga el índice persistido (contenido del sitio)."""
    embed = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embed
    storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    return load_indices_from_storage(storage, embed_model=embed)[0]

@lru_cache(maxsize=8)
def _get_engine(top_k: int):
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=top_k)
    return RetrieverQueryEngine(
        retriever=retriever,
        response_synthesizer=get_response_synthesizer(response_mode="compact"),
    )

def _first_pass(q: str):
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=TOP_K)
    xs = [n for n in retriever.retrieve(q) if getattr(n, "score", None) is not None]
    xs.sort(key=lambda n: n.score, reverse=True)
    return xs

def _second_pass(q: str):
    """Recall ampliado: normaliza y usa solo keywords como variantes."""
    base = _norm(q)
    kws = " ".join(_tokens(base))
    variants = [q, base] + ([kws] if kws else [])
    seen, merged = set(), []
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=TOP_K_FALLBACK)
    for v in variants:
        for n in retriever.retrieve(v):
            nid = getattr(n.node, "node_id", None) or id(n.node)
            if nid in seen:
                continue
            seen.add(nid)
            if getattr(n, "score", None) is not None:
                merged.append(n)
    merged.sort(key=lambda n: n.score, reverse=True)
    return merged

# ===================== catálogo de secciones (enlaces) =======================

@lru_cache(maxsize=1)
def _sections():
    """Carga el catálogo de secciones HTML (generado por el crawler)."""
    if os.path.exists(SECTIONS_CATALOG_PATH):
        with open(SECTIONS_CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    return []

def _is_link_intent(q: str) -> bool:
    ql = _norm(q)
    return any(t in ql for t in ["enlace", "link", "seccion", "sección", "ruta", "url", "acceder", "ir a"])

def _resolve_section_url(q: str) -> str | None:
    """Devuelve la URL más probable de la sección pedida, de forma determinista."""
    items = _sections()
    if not items:
        return None

    q_toks = _tokens(q)
    best, best_score = None, 0.0

    for it in items:
        cand_text = " ".join([
            it.get("text", ""),
            it.get("page_title", ""),
            it.get("h1", ""),
            it.get("section", ""),
        ]).strip()

        s = _similarity(q, cand_text)

        # bonus si palabras de la consulta aparecen en el TEXTO del enlace
        txt_toks = _tokens(it.get("text", ""))
        if q_toks and q_toks.issubset(txt_toks):
            s += 0.20

        # bonus si tokens del PATH coinciden con la consulta
        path_toks = _path_tokens(it.get("url", ""))
        if q_toks and len(q_toks & path_toks) > 0:
            s += 0.15

        # preferir rutas internas (y penalizar fuerte la home)
        depth = _path_depth(it.get("url", ""))
        s += min(depth, 6) * 0.05
        if depth == 0:
            s -= 0.25

        if s > best_score:
            best_score, best = s, it

    # Umbral exigente para evitar falsos positivos
    return best["url"] if best and best_score >= 0.55 else None

# ============================== interfaz QA =================================

def responder_pregunta(pregunta: str) -> str:
    """
    - Si la pregunta pide un ENLACE/RUTA/SECCIÓN → devuelve SOLO la URL exacta.
    - Si es de CONTENIDO → usa el índice semántico (dos pasos).
    """
    # 1) ¿Es intención de enlace?
    if _is_link_intent(pregunta):
        url = _resolve_section_url(pregunta)
        if url:
            # Devuelve solo la URL (simple para el frontend).
            return url
        # si no encontramos sección clara, seguimos con contenido

    # 2) Contenido — Pase 1 (preciso)
    nodes = _first_pass(pregunta)
    if nodes and nodes[0].score >= CONFIDENCE_THRESHOLD:
        resp = _get_engine(TOP_K).query(pregunta)
        return str(resp).strip()

    # 3) Contenido — Pase 2 (recall ampliado)
    nodes2 = _second_pass(pregunta)
    if nodes2 and nodes2[0].score >= (CONFIDENCE_THRESHOLD * 0.85):
        resp = _get_engine(TOP_K_FALLBACK).query(pregunta)
        return str(resp).strip()

    # 4) Fallback
    return ("No encontré un enlace o contenido específico con suficiente certeza. "
            "Intenta con el nombre exacto de la sección como aparece en el menú, "
            "o formula la pregunta con más contexto.")
    

if __name__ == "__main__":
    # Modo consola para pruebas locales
    print("Chatbot UESVALLE (escribe salir/exit/quit para terminar)")
    while True:
        q = input("> ").strip()
        if q.lower() in {"salir", "exit", "quit"}:
            break
        print(responder_pregunta(q), "\n")

