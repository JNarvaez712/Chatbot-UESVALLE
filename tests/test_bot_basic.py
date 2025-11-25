import pytest
from chatbot.bot import responder_pregunta

@pytest.mark.parametrize("query", [
    "Hola",  # small talk
    "Enlace PAA",  # link intent
    "PDF transparencia",  # document intent
    "Requisitos para PQRSD",  # specific content
])
def test_responder_basic(query):
    ans = responder_pregunta(query)
    assert isinstance(ans, str)
    assert len(ans) > 10


def test_fallback():
    q = "xzylmnop termino inventado"  # should trigger fallback or guidance
    ans = responder_pregunta(q)
    assert "No tengo evidencia" in ans or "Sección" in ans
