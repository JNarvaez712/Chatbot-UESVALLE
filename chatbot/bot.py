# chatbot/bot.py
from functools import lru_cache
from llama_index.core import load_indices_from_storage, StorageContext
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.settings import Settings
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from chatbot.config import EMBEDDING_MODEL, STORAGE_DIR, TOP_K


@lru_cache(maxsize=1)
def _get_index():
    """Carga el índice desde disco una sola vez (cacheado)."""
    embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embed_model
    storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index_list = load_indices_from_storage(storage_context, embed_model=embed_model)
    return index_list[0]


@lru_cache(maxsize=1)
def cargar_motor_preguntas():
    """Prepara un motor de recuperación+síntesis eficiente y compacto."""
    index = _get_index()
    retriever = VectorIndexRetriever(index=index, similarity_top_k=TOP_K)
    synthesizer = get_response_synthesizer(response_mode="compact")
    return RetrieverQueryEngine(retriever=retriever, response_synthesizer=synthesizer)


def responder_pregunta(pregunta: str) -> str:
    engine = cargar_motor_preguntas()
    resp = engine.query(pregunta)
    return str(resp)


if __name__ == "__main__":
    # Modo consola para pruebas locales
    print("Chatbot UESVALLE (escribe 'salir' para terminar)")
    while True:
        pregunta = input("> ")
        if pregunta.strip().lower() in {"salir", "exit", "quit"}:
            break
        print(responder_pregunta(pregunta), "\n")


