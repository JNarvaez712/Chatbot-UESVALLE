import pytest
from chatbot.intents import classify_intent

@pytest.mark.parametrize("text,expected", [
    ("Necesito el enlace de transparencia", "link"),
    ("PDF del PAA", "document"),
    ("Requisitos para el trámite de PQRSD", "specific"),
    ("Transparencia", "general"),
])
def test_basic_intents(text, expected):
    intent = classify_intent(text)
    assert intent.label == expected
    assert intent.confidence >= 0.4

def test_other_intent():
    intent = classify_intent("palabras sin contexto XZY")
    assert intent.label in {"other","general"}
