# chatbot/bot.py

from llama_index.core import load_indices_from_storage, StorageContext
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from chatbot.config import EMBEDDING_MODEL, STORAGE_DIR

def cargar_motor_preguntas():
    # Usa el mismo modelo de embeddings con el que fue creado el índice
    embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)

    # Carga el índice desde disco con los embeddings correctos
    storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index_list = load_indices_from_storage(storage_context, embed_model=embed_model)
    index = index_list[0]  # usa el primer índice (asumiendo que solo tienes uno)


    # Crea el motor de consulta
    query_engine = index.as_query_engine()
    return query_engine

def responder_pregunta(pregunta: str) -> str:
    # Ejecuta la pregunta usando el motor cargado
    engine = cargar_motor_preguntas()
    respuesta = engine.query(pregunta)
    return str(respuesta)

# Si el archivo se ejecuta directamente, entra en modo interactivo por consola
if __name__ == "__main__":
    while True:
        pregunta = input("¿Qué deseas preguntar? ")
        if pregunta.lower() in ["salir", "exit", "quit"]:
            break
        respuesta = responder_pregunta(pregunta)
        print(f"\n🧠 Respuesta:\n{respuesta}\n")

