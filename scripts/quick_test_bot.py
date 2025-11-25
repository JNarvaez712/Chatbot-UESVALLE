import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from chatbot.bot import responder_pregunta

tests = [
    "mision y vision",
    "mision de la entidad",
    "vision de la entidad",
    "horarios",
    "funciones de la uesvalle",
    "peti",
    "paa",
    "presupuesto general",
    "formulario pqr",
    "directorio funcionarios",
    "rendicion de cuentas",
    "quiero el enlace del plan anual de adquisiciones",
    "donde está el peti",
]

for q in tests:
    try:
        ans = responder_pregunta(q)
    except Exception as e:
        ans = f"<error: {e}>"
    print("\n==== Q:", q)
    print("A:", ans)
