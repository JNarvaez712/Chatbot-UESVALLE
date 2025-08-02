# chatbot/indexer.py

import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from chatbot.config import EMBEDDING_MODEL, DOCS_DIR, STORAGE_DIR
from chatbot.web_loader import cargar_documentos_web
from chatbot.document_loader import cargar_documentos_web as cargar_documentos_desde_web

def crear_o_cargar_indice():
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

        # Documentos locales (PDF, Excel, Word)
        print("📁 Cargando documentos locales...")
        reader = SimpleDirectoryReader(DOCS_DIR)
        documentos_locales = reader.load_data()

        # Contenido web textual (páginas HTML)
        print("🌐 Cargando contenido textual de la web...")
        documentos_web_texto = cargar_documentos_web()

        # Documentos enlazados en la web (PDFs, DOCX, XLSX...)
        print("📎 Cargando documentos desde la web...")
        documentos_web_archivos = cargar_documentos_desde_web()

        # Combinar todos los documentos
        todos_los_docs = documentos_locales + documentos_web_texto + documentos_web_archivos

        # Crear modelo de embeddings
        embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)

        # Crear e indexar
        print("🧠 Generando índice...")
        index = VectorStoreIndex.from_documents(todos_los_docs, embed_model=embed_model)

        # Guardar
        index.storage_context.persist(STORAGE_DIR)
        print("✅ Índice guardado.")
        return index
    else:
        print("📚 Cargando índice existente...")
        storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
        index = load_index_from_storage(storage_context, embed_model=embed_model)
        return index

if __name__ == "__main__":
    print("🚀 Creando o cargando índice...")
    index = crear_o_cargar_indice()
    print("🎉 ¡Índice listo!")


