# chatbot/indexer.py
import os

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_indices_from_storage,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.settings import Settings
from llama_index.core.schema import Document

from chatbot.config import EMBEDDING_MODEL, DOCS_DIR, STORAGE_DIR
from chatbot.web_loader import cargar_documentos_web
from chatbot.document_loader import cargar_documentos_web as cargar_docs_archivos


def _build_index_from_documents(docs):
    embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embed_model
    index = VectorStoreIndex.from_documents(docs, embed_model=embed_model)
    index.storage_context.persist(STORAGE_DIR)
    print("✅ Índice persistido en", STORAGE_DIR)
    return index


def crear_o_cargar_indice():
    """
    - Si no existe almacenamiento: crea índice desde fuentes (local + web + archivos web).
    - Si existe: lo carga.
    """
    if not os.path.exists(STORAGE_DIR) or not os.listdir(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

        # 1) Documentos locales
        documentos_locales = []
        if os.path.exists(DOCS_DIR):
            print("📁 Cargando documentos locales...")
            documentos_locales = SimpleDirectoryReader(DOCS_DIR).load_data()
        else:
            print(f"ℹ️ Directorio local no encontrado: {DOCS_DIR}")

        # 2) Contenido textual web
        print("🌐 Cargando contenido textual (web)...")
        documentos_web_texto = cargar_documentos_web()

        # 3) Archivos enlazados en la web (PDF/DOCX/XLSX…)
        print("📎 Cargando documentos enlazados (web)...")
        documentos_web_archivos = cargar_docs_archivos()

        todos_los_docs = documentos_locales + documentos_web_texto + documentos_web_archivos

        if not todos_los_docs:
            print("⚠️ No se encontraron documentos. Creando índice placeholder.")
            todos_los_docs = [
                Document(
                    text=(
                        "No hay documentos indexados aún. "
                        "Una vez se agreguen o detecten documentos, el índice se actualizará automáticamente."
                    ),
                    metadata={"source": "placeholder"},
                )
            ]

        print(f"🧠 Generando índice a partir de {len(todos_los_docs)} documentos...")
        return _build_index_from_documents(todos_los_docs)

    # Cargar existente
    print("📚 Cargando índice existente...")
    storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.embed_model = embed_model
    index_list = load_indices_from_storage(storage_context, embed_model=embed_model)
    return index_list[0]


if __name__ == "__main__":
    print("🚀 Creando o cargando índice...")
    _ = crear_o_cargar_indice()
    print("🎉 ¡Índice listo!")



