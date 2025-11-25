"""
Pequeño wrapper para respuestas con OpenAI limitadas al CONTEXTO recuperado.
No usa conocimiento externo: el prompt prohíbe añadir información que no esté en el contexto.
"""
from __future__ import annotations
import os
from typing import List

from chatbot.config import OPENAI_API_KEY, OPENAI_MODEL

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "El paquete 'openai' no está instalado. Agrega 'openai' a requirements.txt e instala las dependencias.") from e
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY no está configurada.")
        os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY)
        _client = OpenAI()
    return _client


def answer_with_openai(context_blocks: List[str], question: str, model: str | None = None) -> str:
    """Construye un prompt de sistema + usuario con el CONTEXTO y la pregunta.
    Respuesta en español, profesional, SIN enlaces y SIN información fuera del contexto.
    """
    model = model or OPENAI_MODEL or "gpt-4o-mini"
    ctx_joined = "\n\n---\n\n".join(block.strip() for block in context_blocks if block and block.strip())
    if not ctx_joined:
        return "No tengo evidencia suficiente en el sitio oficial para responder con precisión."

    system = (
        "Eres un asistente de la UESVALLE. Debes responder en español, "
        "con precisión y de forma breve. SOLO puedes usar la información del CONTEXTO dado. "
        "Si algo no está en el contexto, di literalmente: 'No tengo evidencia suficiente en el sitio oficial para responder con precisión.' "
        "No inventes, no supongas, no cites ni enlaces a menos que el usuario lo pida explícitamente."
    )

    user = (
        f"CONTEXTO (fragmentos textuales del sitio oficial):\n\n{ctx_joined}\n\n"
        f"PREGUNTA: {question}\n\n"
        "Responde SOLAMENTE con la información del CONTEXTO. Sin enlaces, sin citas externas."
    )

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception:
        # No filtramos detalles de error al usuario
        return "Ocurrió un error generando la respuesta. Intenta de nuevo más tarde."
