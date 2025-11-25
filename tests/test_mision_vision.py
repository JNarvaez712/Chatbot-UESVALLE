import pytest
from chatbot.bot import responder_pregunta


@pytest.mark.parametrize("query,expect_substr", [
    ("Cuál es la misión de la UESVALLE?", "La misión de la UESVALLE es"),
    ("Cuál es la visión de la UESVALLE?", "La visión de la UESVALLE es"),
    ("Misión y visión de la entidad", "La visión de la UESVALLE es"),
])
def test_mision_vision_respuestas(query, expect_substr):
    ans = responder_pregunta(query)
    assert expect_substr in ans
    # Debe contener al menos una frase significativa del texto institucional
    assert len(ans) > 50

def test_mision_y_vision_ambas():
    ans = responder_pregunta("Necesito la mision y vision")
    assert "La misión de la UESVALLE es" in ans
    assert "La visión de la UESVALLE es" in ans