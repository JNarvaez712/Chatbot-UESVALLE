# chatbot/bot.py
from functools import lru_cache

from llama_index.core import load_indices_from_storage, StorageContext
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.settings import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from chatbot.config import EMBEDDING_MODEL, STORAGE_DIR, TOP_K

# Ajusta la estrictitud: más alto = más exigente con la evidencia
CONFIDENCE_THRESHOLD = 0.35

@lru_cache(maxsize=1)
def _get_index():
    embed = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embed
    storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    return load_indices_from_storage(storage, embed_model=embed)[0]

@lru_cache(maxsize=1)
def _get_retriever():
    return VectorIndexRetriever(index=_get_index(), similarity_top_k=TOP_K)

@lru_cache(maxsize=1)
def _get_engine():
    return RetrieverQueryEngine(
        retriever=_get_retriever(),
        response_synthesizer=get_response_synthesizer(response_mode="compact")
    )

def responder_pregunta(pregunta: str) -> str:
    # 1) Verifica evidencia con puntajes de similitud
    nodes = [n for n in _get_retriever().retrieve(pregunta) if getattr(n, "score", None) is not None]
    nodes.sort(key=lambda n: n.score, reverse=True)

    if not nodes or nodes[0].score < CONFIDENCE_THRESHOLD:
        return ("No tengo evidencia suficiente para responder con certeza. "
                "Intenta con más contexto o revisa Atención al Ciudadano.")

    # 2) Genera respuesta compacta (SIN mostrar enlaces)
    resp = _get_engine().query(pregunta)
    return str(resp).strip()

if __name__ == "__main__":
    print("Chatbot UESVALLE (salir/exit/quit para terminar)")
    while True:
        q = input("> ").strip()
        if q.lower() in {"salir", "exit", "quit"}:
            break
        print(responder_pregunta(q), "\n")


