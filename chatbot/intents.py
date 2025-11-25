# chatbot/intents.py
# Clasificador de intenciones basado en reglas para español (ligero y extensible)
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

# Palabras que suelen indicar navegación/enlace
NAV_KEYWORDS = [
    "enlace","link","seccion","sección","ruta","url","acceder","ir a","llevar",
    "abrir","consultar","donde esta","dónde está","quiero ver","ver sección",
    "direccion","dirección","camino","navegar","menu","menú","apartado","subseccion","subsección",
    "donde encuentro","dónde encuentro","en que parte","en qué parte","como llegar","cómo llegar",
]

# Palabras que suelen indicar documentos/descargas
DOC_KEYWORDS = [
    "pdf","documento","formato","descargar","descarga","archivo","hoja","plantilla","circular",
    "resolución","resolucion","acuerdo","manual","acta",
]

# Palabras de pregunta detallada
SPEC_TOKENS = [
    "que","qué","cuando","cuándo","donde","dónde","como","cómo","cuanto","cuánto",
    "quien","quién","requisitos","pasos","horario","telefono","teléfono","correo","costo",
    "plazo","vigencia","fecha","lugar","procedimiento","trámite","tramite",
]

STOP_MINI = {"de","la","que","el","en","y","a","los","del","se","las","por","un","para","con","no","una","su","al","lo"}

@dataclass
class Intent:
    label: str  # one of: link, document, specific, general, other
    confidence: float
    signals: List[str]


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9\-]+", _norm(s)) if t not in STOP_MINI and len(t) > 2]


def classify_intent(text: str) -> Intent:
    q = _norm(text or "")
    if not q:
        return Intent("other", 0.0, [])

    signals: List[str] = []

    # Documento si hay keywords claras
    if any(k in q for k in DOC_KEYWORDS):
        signals.extend([k for k in DOC_KEYWORDS if k in q])
        return Intent("document", min(1.0, 0.6 + 0.05 * len(signals)), signals)

    # Link/Navegación
    nav_patterns = [
        r"\b(donde|dónde) (esta|está|encuentro)\b",
        r"\b(como|cómo) (llego|ir|acceder)\b",
        r"\b(en\s+que|en\s+qué)\s+parte\b",
        r"\b(llevar(me)?|navegar a|abrir)\b",
    ]
    if any(k in q for k in NAV_KEYWORDS) or any(re.search(p, q, re.I) for p in nav_patterns):
        signals.extend([k for k in NAV_KEYWORDS if k in q])
        return Intent("link", min(1.0, 0.55 + 0.05 * len(signals)), signals)

    # Específica si hay tokens de pregunta de detalle
    if any(re.search(rf"\b{t}\b", q) for t in SPEC_TOKENS):
        signals.extend([t for t in SPEC_TOKENS if re.search(rf"\b{t}\b", q)])
        return Intent("specific", min(1.0, 0.5 + 0.05 * len(signals)), signals)

    # General si tiene muy pocos tokens útiles
    toks = _tokens(q)
    if len(toks) <= 3:
        return Intent("general", 0.5, toks)

    return Intent("other", 0.4, _tokens(q)[:5])
