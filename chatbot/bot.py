# chatbot/bot.py
# -----------------------------------------------------------------------------
# Motor de QA “amigable” + Resolución determinista de enlaces a secciones
# -----------------------------------------------------------------------------
# - SMALL TALK: responde saludos, despedidas, agradecimientos, etc.
# - ENLACES: si detecta intención de link/ruta/sección, usa catálogo de secciones.
# - CONTENIDO: índice semántico con dos pasadas y recall ampliado.
# - CATCH-ALL: si no hay certeza, sugiere un enlace probable.
# - NORMALIZACIÓN: usa sinónimos, tokens, similitud difusa y señales del path.
# - MEJORA: ahora siempre devuelve un enlace único + ruta de navegación.
# -----------------------------------------------------------------------------

from functools import lru_cache
import json
import os
import re
import unicodedata
import difflib
from urllib.parse import urlparse
from urllib.parse import unquote
from time import time
from typing import Optional
import requests
from bs4 import BeautifulSoup

try:  # Importación opcional para permitir funcionamiento parcial sin instalar todo
    from llama_index.core import load_indices_from_storage, StorageContext
    from llama_index.core.query_engine import RetrieverQueryEngine
    from llama_index.core.response_synthesizers import get_response_synthesizer
    from llama_index.core.retrievers import VectorIndexRetriever
    from llama_index.core.settings import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    _LLAMA_AVAILABLE = True
except Exception:  # pragma: no cover
    _LLAMA_AVAILABLE = False

from chatbot.config import (
    EMBEDDING_MODEL,
    STORAGE_DIR,
    TOP_K,
    TOP_K_FALLBACK,
    CONFIDENCE_THRESHOLD,
    SECTIONS_CATALOG_PATH,
    REPO_DATA_DIR,
    DATA_DIR,
    AUTO_BUILD_INDEX,
    EXACT_MODE,
    ANSWER_MODE,
    MAX_QUERY_SECONDS,
    STYLE_SUMMARIZE,
    STYLE_HYBRID,
)
from chatbot.openai_client import answer_with_openai  # opcional (deshabilitado al forzar modo llama)
from chatbot.intents import classify_intent, Intent
from chatbot.config import LEXICAL_INDEX_PATH
import json

# ============================ utilidades de texto ============================

STOPWORDS_ES = {
    "de","la","que","el","en","y","a","los","del","se","las","por","un","para","con","no","una","su","al",
    "lo","como","mas","más","pero","sus","le","ya","o","este","si","sí","porque","esta","entre","cuando",
    "muy","sin","sobre","tambien","también","me","hasta","hay","donde","dónde","quien","quién","desde",
    "todo","nos","durante","todos","uno","les","ni","contra","otros","ese","eso","ante","ellos","e","esto",
    "mi","mí","antes","algunos","que","qué","unos","yo","otro","otras","otra","ir","seccion","sección",
    "enlace","link","ruta","url","acceder","pagina","página","al","la","el","de la","de el","del",
    # verbos comunes que no aportan intención
    "quiero","necesito","busco","muéstrame","muestrame","mostrar","ver","abrir","consultar"
}

# Sinónimos y palabras “amigables” → palabras clave
SYNONYMS = {
    "tramite":"trámite","tramites":"trámites","turno":"cita","turnos":"citas",
    "quejas":"pqrsd","reclamos":"pqrsd","sugerencias":"pqrsd","denuncias":"pqrsd",
    "pqrs":"pqrsd","pqrsd":"pqrsd","peticiones":"pqrsd",
    "paa":"plan anual de adquisiciones",
    "peti":"plan estratégico de tecnologías de la información",
    "pti":"plan estratégico de tecnologías de la información",
    "plan tic":"plan estratégico de tecnologías de la información",
    "sgi":"sistema de gestión integral",
    "rendicion":"rendición de cuentas",
    "transparencia":"transparencia","info":"información","contacto":"directorio",
    "telefonos":"teléfonos","telefono":"teléfono","ayuda":"atención",
    "mision":"misión","vision":"visión","funcion":"función",
    "compras":"adquisiciones","correos":"correo","email":"correo",
    "mapa sitio":"mapa del sitio","politicas":"políticas","datos":"datos personales",
    # navegación
    "direccion":"dirección","ubicacion":"ubicación","ubicación":"ubicación",
    "menu":"menú","subseccion":"subsección","sub-seccion":"subsección",
}

# Mapeo directo de palabras clave a URLs canónicas para intención de enlaces.
# Se basa en rutas presentes en el dataset indexado. Ampliable.
KEYWORD_LINK_MAP = {
    # Planes y estrategias
    "peti": "https://www.uesvalle.gov.co/documentos/380/plan-estrategico-de-la-tecnologias-de-informacion/",
    "plan estrategico tic": "https://www.uesvalle.gov.co/documentos/380/plan-estrategico-de-la-tecnologias-de-informacion/",
    "plan estrategico de la tecnologias de la informacion": "https://www.uesvalle.gov.co/documentos/380/plan-estrategico-de-la-tecnologias-de-informacion/",
    "paa": "https://www.uesvalle.gov.co/documentos/23/plan-anual-de-adquisiciones/",
    "plan anual de adquisiciones": "https://www.uesvalle.gov.co/documentos/23/plan-anual-de-adquisiciones/",
    "presupuesto general": "https://www.uesvalle.gov.co/publicaciones/1864/presupuesto-general-de-ingresos-gastos-e-inversion/",
    "presupuesto general de ingresos gastos e inversion": "https://www.uesvalle.gov.co/publicaciones/1864/presupuesto-general-de-ingresos-gastos-e-inversion/",
    # Página principal
    "inicio": "https://www.uesvalle.gov.co/",
    "pagina principal": "https://www.uesvalle.gov.co/",
    "página principal": "https://www.uesvalle.gov.co/",
    "portal uesvalle": "https://www.uesvalle.gov.co/",
    "sitio uesvalle": "https://www.uesvalle.gov.co/",
    "uesvalle": "https://www.uesvalle.gov.co/",
    "sitio web uesvalle": "https://www.uesvalle.gov.co/",
    # Transparencia / PQRSD
    "pqr": "https://www.uesvalle.gov.co/publicaciones/1141/formulario-de-peticiones-quejas-reclamos-sugerencias-denuncias-y-solicitud-de-informacion-publica/",
    "pqrsd": "https://www.uesvalle.gov.co/publicaciones/1141/formulario-de-peticiones-quejas-reclamos-sugerencias-denuncias-y-solicitud-de-informacion-publica/",
    "formulario pqr": "https://www.uesvalle.gov.co/publicaciones/1141/formulario-de-peticiones-quejas-reclamos-sugerencias-denuncias-y-solicitud-de-informacion-publica/",
    # Mision Vision
    "mision vision": "https://www.uesvalle.gov.co/publicaciones/2/mision-y-vision/",
    "mision": "https://www.uesvalle.gov.co/publicaciones/2/mision-y-vision/",
    "vision": "https://www.uesvalle.gov.co/publicaciones/2/mision-y-vision/",
    # Directorio
    "directorio": "https://www.uesvalle.gov.co/publicaciones/1433/directorio-institucional-incluyendo-sedes-oficinas-sucursales-o-regionales-y-dependencias/",
    "directorio funcionarios": "https://www.uesvalle.gov.co/documentos/426/directorio-funcionarios/",
    # Datos abiertos
    "datos abiertos": "https://www.uesvalle.gov.co/publicaciones/1108/datos-abiertos/",
    # Rendicion de cuentas
    "rendicion de cuentas": "https://www.uesvalle.gov.co/publicaciones/1457/rendicion-de-cuentas/",
    # Directorios / teléfonos / horarios (se reutiliza directorio institucional si no hay URL específica de horarios)
    "directorios": "https://www.uesvalle.gov.co/publicaciones/1433/directorio-institucional-incluyendo-sedes-oficinas-sucursales-o-regionales-y-dependencias/",
    "telefonos": "https://www.uesvalle.gov.co/publicaciones/1433/directorio-institucional-incluyendo-sedes-oficinas-sucursales-o-regionales-y-dependencias/",
    "teléfonos": "https://www.uesvalle.gov.co/publicaciones/1433/directorio-institucional-incluyendo-sedes-oficinas-sucursales-o-regionales-y-dependencias/",
    "horarios": "https://www.uesvalle.gov.co/publicaciones/1433/directorio-institucional-incluyendo-sedes-oficinas-sucursales-o-regionales-y-dependencias/",
    # Funciones y deberes
    "funciones": "https://www.uesvalle.gov.co/publicaciones/169/funciones-y-deberes/",
    "funciones y deberes": "https://www.uesvalle.gov.co/publicaciones/169/funciones-y-deberes/",
}

# ------------------ Mapeo dinámico (ampliado) desde data/routes.txt ---------
# Nueva versión basada en la solicitud de ampliar a TODAS las URLs y usar
# una "etiqueta" derivada de TODOS los segmentos del path, no sólo el último.
# Estrategia:
#   1. Tomar todos los segmentos textuales (decodificados) excluyendo puramente numéricos.
#   2. Filtrar segmentos genéricos (categorías contenedoras) para formar una etiqueta compuesta.
#   3. Generar variantes de búsqueda: último segmento, combinación completa, últimos dos segmentos,
#      cada segmento individual significativo y ajuste especial para prefijos 'plan-', 'manual-', etc.
#   4. Incluir también dominios de Google Sites (sig-uesvalle) para poder devolver enlaces internos.
#   5. Normalizar (minúsculas, sin tildes se maneja luego por _norm) y evitar colisiones con KEYWORD_LINK_MAP.
_DYN_STOP = {
    'publicaciones','documentos','tramites','trámites','directorio','vigencia','resoluciones','plan','planes',
    'programa','proceso','procesos','descripcion','descripción','general','menu','menú','otros','que','qué',
    'de','del','la','el','los','las','y','para','por','en','al','yo','a','un','una','o','se','su','sus','deberes',
    'inicio','b','c','d','e','formatos','instructivos','manuales','procedimientos','guías','guias','listas','listados'
}

def _segments_from_url(u: str) -> list[str]:
    try:
        path = urlparse(u).path
        # quitar query para la etiqueta
        path = path.split('?')[0]
        segs = [unquote(s).strip('/') for s in path.strip('/').split('/') if s and s != '']
        # eliminar puramente numéricos y vacíos
        segs = [s for s in segs if not s.isdigit()]
        return segs
    except Exception:
        return []

def _clean_segment(seg: str) -> str:
    seg = seg.lower()
    seg = seg.replace('_','-')
    seg = re.sub(r'-{2,}','-', seg)
    return seg

def _segment_phrase(seg: str) -> str:
    return _clean_segment(seg).replace('-', ' ').strip()

def _all_segment_phrase(segs: list[str]) -> str:
    return " ".join(_segment_phrase(s) for s in segs).strip()

def _generate_variants_from_segments(segs: list[str]) -> set[str]:
    variants: set[str] = set()
    if not segs:
        return variants
    # Segs depurados e ignorar genéricos
    filtered = [s for s in segs if _segment_phrase(s) and _segment_phrase(s) not in _DYN_STOP]
    if not filtered:
        return variants
    last = filtered[-1]
    variants.add(_segment_phrase(last))
    # frase completa combinada (sin genéricos internos)
    full = _all_segment_phrase(filtered)
    if full:
        variants.add(full)
    # últimos dos segmentos (si aporta algo distinto a last y full)
    if len(filtered) >= 2:
        last_two = _all_segment_phrase(filtered[-2:])
        if last_two not in variants:
            variants.add(last_two)
    # cada segmento individual significativo (longitud >3 y no genérico)
    for s in filtered:
        phr = _segment_phrase(s)
        if len(phr) > 3 and phr not in _DYN_STOP:
            variants.add(phr)
        # prefijos especiales
        if s.startswith('plan-'):
            rest = _segment_phrase(s[5:])
            if rest:
                variants.add('plan ' + rest)
        if s.startswith('manual-'):
            rest = _segment_phrase(s[7:])
            if rest:
                variants.add('manual ' + rest)
    # eliminar variantes demasiado genéricas o de 1 token que sea stop
    pruned = set()
    for v in variants:
        toks = [t for t in re.split(r'[\s]+', v) if t]
        if len(toks) == 1 and toks[0] in _DYN_STOP:
            continue
        if all(t in _DYN_STOP for t in toks):
            continue
        pruned.add(v)
    # expansión ligera de sinónimos (aplicar diccionario SYNONYMS) para algunos tokens únicos
    expanded = set(pruned)
    for v in list(pruned):
        for k, syn in SYNONYMS.items():
            # si la variante contiene el valor y no contiene ya el sinónimo – evitar explosión
            if k in v and syn not in v:
                expanded.add(v.replace(k, syn))
    return expanded

@lru_cache(maxsize=1)
def _build_dynamic_link_map() -> dict:
    routes_path = os.path.join(REPO_DATA_DIR, 'routes.txt')
    if not os.path.exists(routes_path):
        alt = os.path.join(DATA_DIR, 'routes.txt')
        if os.path.exists(alt):
            routes_path = alt
        else:
            return {}
    try:
        lines = [ln.strip() for ln in open(routes_path, 'r', encoding='utf-8', errors='ignore').read().splitlines() if ln.strip()]
    except Exception:
        return {}
    mapping: dict[str,str] = {}
    for u in lines:
        # incluir tanto dominio oficial como google sites institucional
        if not any(dom in u for dom in ['uesvalle.gov.co','sites.google.com']):
            continue
        segs = _segments_from_url(u)
        if not segs:
            continue
        variants = _generate_variants_from_segments(segs)
        # añadir variantes compuestas con segmento leaf genérico si fue filtrado
        leaf_genericos = {"formatos","instructivos","manuales","procedimientos","guias","guías","listas","listados"}
        raw_last = segs[-1].lower()
        last_clean = _segment_phrase(segs[-1])
        # normalizar equivalencias sin tildes
        last_norm_plain = re.sub(r'[áÁ]', 'a', last_clean)
        if last_clean in leaf_genericos or last_norm_plain in leaf_genericos or raw_last in leaf_genericos:
            # construir cadena padre + leaf aún si leaf está en _DYN_STOP
            padres = []
            for p in segs[:-1]:
                phr = _segment_phrase(p)
                if phr and phr not in _DYN_STOP:
                    padres.append(phr)
            if padres:
                compuesta = ' '.join(padres + [last_clean])
                variants.add(compuesta)
                # también agregar variante reducida ultimo padre + leaf para desambiguar si hay profundidad >1
                if len(padres) > 1:
                    corta = ' '.join([padres[-1], last_clean])
                    variants.add(corta)
        # si tras filtrado no queda ninguna variante que apunte a esta URL, generar fallback completo
        pre_mapeables = [v for v in variants if v and v not in KEYWORD_LINK_MAP and v not in mapping]
        if not pre_mapeables:
            # usar todos los segmentos (incluyendo genéricos) para formar clave única
            full_chain = ' '.join([_segment_phrase(s) for s in segs if _segment_phrase(s)])
            if full_chain:
                variants.add(full_chain)
        for v in variants:
            if v and v not in KEYWORD_LINK_MAP and v not in mapping:
                mapping[v] = u
    return mapping

DYNAMIC_LINK_MAP = _build_dynamic_link_map()

# Unificación: incorporar todas las variantes dinámicas al mapa manual para que
# cada keyword quede explícitamente soportada en la capa prioritaria.
# Esto evita duplicar cientos de líneas arriba y mantiene mantenibilidad.
KEYWORD_LINK_MAP.update(DYNAMIC_LINK_MAP)

# ===================== Enriquecimiento adicional de palabras clave =====================
# Objetivo: añadir más formas naturales y sinónimos para que el usuario pueda
# escribir distintas variantes y obtener el mismo enlace.
# Reglas aplicadas:
#  1. Variantes sin tildes para cada clave con caracteres acentuados.
#  2. Reemplazo por sinónimos definidos en SYNONYMS (cuando no generan colisiones).
#  3. Expansiones específicas por URL (ej. SIG, información infantil, procesos misionales).
#  4. Frases compuestas "sistema de gestion de calidad" para SIG y calidad.
#  5. Variantes infantiles (niños, niñas, infancia, menores) para páginas de información para niños.

_EXTRA_URL_KEYWORDS = {
    # SIG raíz
    "https://sites.google.com/uesvalle.gov.co/sig-uesvalle/inicio": [
        "sig", "sig uesvalle", "sistema de gestion integral", "sistema de gestion de calidad",
        "sistema de calidad", "sistema integral", "sistema de gestion institucional",
        "gestion de calidad", "calidad institucional"
    ],
    # Información para niños y niñas
    "https://www.uesvalle.gov.co/publicaciones/1106/informacion-para-ninos-y-ninas/": [
        "informacion para niños", "informacion para niñas", "informacion para niños y niñas",
        "informacion infantil", "informacion para infancia", "informacion para menores",
        "informacion para ninos", "informacion para ninas", "niños y niñas", "infancia",
        "informacion menores", "informacion ninos y ninas"
    ],
}

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def _enrich_manual_map():
    # 1. Expansiones por URL explícitas
    for url, kws in _EXTRA_URL_KEYWORDS.items():
        for kw in kws:
            if kw not in KEYWORD_LINK_MAP:
                KEYWORD_LINK_MAP[kw] = url
    # 2. Variantes sin tildes
    snapshot = list(KEYWORD_LINK_MAP.items())
    for kw, url in snapshot:
        no_acc = _strip_accents(kw)
        if no_acc != kw and no_acc not in KEYWORD_LINK_MAP:
            KEYWORD_LINK_MAP[no_acc] = url
    # 3. Reemplazo por sinónimos: token completo
    for kw, url in snapshot:
        for token, syn in SYNONYMS.items():
            if token in kw and syn not in kw:
                candidate = kw.replace(token, syn)
                if candidate not in KEYWORD_LINK_MAP:
                    KEYWORD_LINK_MAP[candidate] = url
    # 4. Calidad / gestión combinaciones para SIG si aún no existen
    sig_url = "https://sites.google.com/uesvalle.gov.co/sig-uesvalle/inicio"
    calidad_variants = ["sistema de gestion de calidad", "sistema de calidad", "sistema gestion calidad", "calidad sig"]
    for v in calidad_variants:
        if v not in KEYWORD_LINK_MAP:
            KEYWORD_LINK_MAP[v] = sig_url
    # 5. Infancia: generar variantes adicionales cortas
    inf_url = "https://www.uesvalle.gov.co/publicaciones/1106/informacion-para-ninos-y-ninas/"
    infancia_extras = ["informacion infancia", "informacion niñas", "informacion niños", "info niños", "info niñas", "info infancia"]
    for v in infancia_extras:
        if v not in KEYWORD_LINK_MAP:
            KEYWORD_LINK_MAP[v] = inf_url

_enrich_manual_map()

# ===================== Enriquecimiento exhaustivo (controlado) =====================
# Genera variantes adicionales para CADA URL basado en segmentos del path.
# Reglas:
#  - Singular/plural simple (remover terminaciones 's', 'es') cuando aplica.
#  - Combinaciones padre+leaf siempre aunque leaf sea genérico.
#  - Prefijos contextuales: 'info', 'informacion', 'documentos de', 'formato de', 'procedimiento de'
#  - Evitar duplicados y palabras vacías > se salta si ya existe la clave.
#  - Limitar crecimiento con MAX_NEW_VARIANTS para evitar explosión.

MAX_NEW_VARIANTS = 12000  # límite de seguridad

def _singular_forms(token: str) -> set[str]:
    out = set()
    if token.endswith('es') and len(token) > 5:
        out.add(token[:-2])
    if token.endswith('s') and len(token) > 4:
        out.add(token[:-1])
    return out

def _exhaustive_enrich_map():
    added = 0
    # Agrupar URLs
    url_groups: dict[str,set[str]] = {}
    for kw, url in list(KEYWORD_LINK_MAP.items()):
        url_groups.setdefault(url, set()).add(kw)
    for url, kws in url_groups.items():
        # Obtener segmentos
        segs = _segments_from_url(url)
        norm_segs = [ _segment_phrase(s) for s in segs if _segment_phrase(s) ]
        if not norm_segs:
            continue
        leaf = norm_segs[-1]
        parents = norm_segs[:-1]
        base_variants = set()
        # Combinaciones padre + leaf
        if parents:
            base_variants.add(' '.join(parents + [leaf]))
            if len(parents) > 1:
                base_variants.add(parents[-1] + ' ' + leaf)
        # Singular/plural de leaf y padres
        for tok in norm_segs:
            for sing in _singular_forms(tok):
                base_variants.add(sing)
        # Prefijos contextuales
        context_prefixes = []
        if 'formato' in leaf or 'formatos' in leaf:
            context_prefixes = ['formato de','formatos de','documentos de']
        elif 'procedimiento' in leaf or 'procedimientos' in leaf:
            context_prefixes = ['procedimiento de','procedimientos de','proceso de']
        elif 'manual' in leaf or 'manuales' in leaf:
            context_prefixes = ['manual de','manuales de']
        elif 'guia' in leaf or 'guías' in leaf or 'guias' in leaf:
            context_prefixes = ['guia de','guias de','guías de']
        elif 'plan' in leaf or 'planes' in leaf:
            context_prefixes = ['plan de','planes de']
        elif 'informacion' in leaf or 'información' in leaf or 'info' in leaf:
            context_prefixes = ['informacion de','info de']
        # Aplicar prefijos sobre última palabra y sobre combinaciones padre+leaf
        for pref in context_prefixes:
            base_variants.add(pref + ' ' + leaf)
            if parents:
                base_variants.add(pref + ' ' + parents[-1] + ' ' + leaf)
        # Prefijos genéricos si hay padres
        if parents:
            base_variants.add('documentos de ' + leaf)
            base_variants.add('informacion ' + leaf)
        # Filtrar duplicados existentes
        for variant in base_variants:
            if added >= MAX_NEW_VARIANTS:
                return
            v = variant.strip()
            if not v or v in KEYWORD_LINK_MAP:
                continue
            KEYWORD_LINK_MAP[v] = url
            added += 1

_exhaustive_enrich_map()

# ===================== Fetch en vivo Misión/Visión (fallback) =====================
def _fetch_live_mision_vision(timeout: float = 6.0) -> dict:
    """Fetch directo con BeautifulSoup para extraer párrafos de Misión y Visión.
    Estrategia:
      1. Descargar HTML de la página canónica.
      2. Localizar el nodo cuyo texto sea exactamente 'Misión' (o contenga) y 'Visión'.
      3. Tomar los párrafos (p, div, span) siguientes hasta antes del encabezado de la otra sección.
      4. Limpiar navegación/contacto (teléfonos, correos, horarios) y retornar.
    No hardcodea el contenido, sólo patrones estructurales.
    """
    url = KEYWORD_LINK_MAP.get("mision")
    if not url:
        return {}
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "UESVALLEBot/1.0"})
        if resp.status_code != 200:
            return {}
        html = resp.text
    except Exception:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    # Normalizar todos los textos en nodos para facilitar búsqueda
    def normtxt(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()
    mission_head = None
    vision_head = None
    for tag in soup.find_all(["h1","h2","h3","strong","b","span"]):
        text = normtxt(tag.get_text(" "))
        if not mission_head and re.search(r"\bMis[ií]ón\b", text, re.I):
            mission_head = tag
        if not vision_head and re.search(r"\bVis[ií]ón\b", text, re.I):
            vision_head = tag
        if mission_head and vision_head:
            break
    out = {}
    phone_mail_pattern = re.compile(r"(\+?\d[\d\s().-]{6,}|@|tel[:.]?)", re.I)
    def collect_section(start_tag, stop_tag) -> str:
        if not start_tag:
            return ""
        texts = []
        for sib in start_tag.next_siblings:
            if sib == stop_tag:
                break
            if getattr(sib, 'name', None) in ["h1","h2","h3","strong","b","span"]:
                # otro encabezado sin ser el stop → terminamos
                if sib != stop_tag:
                    break
            if hasattr(sib, 'get_text'):
                raw = normtxt(sib.get_text(" "))
                if not raw:
                    continue
                if len(raw) < 25:
                    continue
                if phone_mail_pattern.search(raw):
                    continue
                if any(w in raw.lower() for w in ["horario","atencion","contacto","contratacion"]):
                    continue
                texts.append(raw)
            if len(" ".join(texts)) > 800:
                break
        # Fallback: si vacío, intentar tomar el propio encabezado + siguiente p descendente
        if not texts:
            first_p = start_tag.find_next("p")
            if first_p:
                raw = normtxt(first_p.get_text(" "))
                if raw and not phone_mail_pattern.search(raw):
                    texts.append(raw)
        return " ".join(texts).strip()
    mission_text = collect_section(mission_head, vision_head)
    vision_text = collect_section(vision_head, None)
    # Limpieza final y recorte prudente
    def trim_block(b: str) -> str:
        b = re.sub(r"\s+", " ", b).strip()
        if len(b) > 600:
            b = b[:600].rsplit(" ", 1)[0].strip()
        return b
    if mission_text:
        out["mision"] = trim_block(mission_text)
    if vision_text:
        out["vision"] = trim_block(vision_text)
    return out

def _fetch_live_funciones(timeout: float = 5.0) -> Optional[str]:
    """Fetch directo de la página de 'Funciones y deberes'.
    Procedimiento:
      1. Descargar HTML canónico.
      2. Localizar encabezado con 'Funciones' o 'Funciones y deberes'.
      3. Capturar párrafos descriptivos posteriores (p/div/span) hasta otro encabezado.
      4. Filtrar navegación/contacto/ruido y retornar bloque con viñetas.
    No hardcodea el contenido, sólo patrones estructurales.
    """
    url = KEYWORD_LINK_MAP.get("funciones") or KEYWORD_LINK_MAP.get("funciones y deberes")
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "UESVALLEBot/1.0"})
        if resp.status_code != 200:
            return None
    except Exception:
        return None
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    def normtxt(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()
    target_head = None
    for tag in soup.find_all(["h1","h2","h3","strong","b","span"]):
        text = normtxt(tag.get_text(" "))
        if re.search(r"funciones?(?:\s+y\s+deberes)?", text, re.I):
            target_head = tag
            break
    if not target_head:
        return None
    phone_mail_pattern = re.compile(r"(\+?\d[\d\s().-]{6,}|@|tel[:.]?)", re.I)
    ruido_nav = {"iniciar", "desplegar", "idiomas", "configuración", "mapa", "buscar", "facebook", "twitter", "linkedin", "whatsapp", "compartir", "contratación"}
    bloques = []
    for sib in target_head.next_siblings:
        if getattr(sib, 'name', None) in ["h1","h2","h3","strong","b","span"]:
            # fin de sección
            break
        if hasattr(sib, 'get_text'):
            raw = normtxt(sib.get_text(" "))
            if not raw:
                continue
            if len(raw) < 35:
                continue
            low = raw.lower()
            if phone_mail_pattern.search(raw):
                continue
            if any(r in low for r in ruido_nav):
                continue
            if re.search(r"visitas|publicado|última modificación|fecha de publicación", low):
                continue
            # Evitar bloques puramente de navegación
            if sum(1 for w in ["inicio","menú","menu","buscar"] if w in low) >= 2:
                continue
            bloques.append(raw)
        if len(bloques) >= 6:
            break
    if not bloques:
        return None
    # Deduplicar y filtrar sólo los que contienen 'funcion'/'funciones' o verbo representativo
    pattern_func = re.compile(r"\bfunci[oó]n(?:es)?\b", re.I)
    seleccion = []
    seen = set()
    for b in bloques:
        bl = b.lower()
        if pattern_func.search(bl) or re.search(r"(garantizar|coordinar|ejecutar|vigilar|desarrollar|implementar|realizar)", bl):
            key = bl
            if key in seen:
                continue
            seen.add(key)
            seleccion.append(b)
    if not seleccion:
        # si ningún bloque contiene la palabra función(es) descartamos para evitar ruido genérico
        return None
    # Construcción final
    bullet_block = "Funciones de la UESVALLE:\n- " + "\n- ".join(seleccion)
    return bullet_block.strip()

SMALL_TALK_PATTERNS = {
    "saludo": re.compile(r"\b(hola|buen[oa]s(?:\s+(dias|días|tardes|noches))?|saludo[s]?|hey|qué tal|que tal)\b", re.I),
    "despedida": re.compile(r"\b(ad[ií]os|gracias.*|hasta luego|nos vemos|chao)\b", re.I),
    "ayuda": re.compile(r"\b(ayuda|como te uso|que haces|para que sirves)\b", re.I),
}

def _norm(s: str) -> str:
    """Normaliza: sin tildes, minúsculas, espacios compactados."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()

def _apply_synonyms(text: str) -> str:
    t = _norm(text)
    for k, v in SYNONYMS.items():
        t = re.sub(rf"\b{k}\b", v, t)
    return t

def _tokens(s: str) -> set[str]:
    """Tokens sin stopwords, útiles para coincidencia."""
    return {t for t in re.findall(r"[a-z0-9\-]+", _norm(s)) if t not in STOPWORDS_ES and len(t) > 2}

def _path_tokens(u: str) -> set[str]:
    """Tokens de la ruta /path/de/la/url (útil para detectar secciones)."""
    p = urlparse(u).path.strip("/")
    toks = set()
    for part in p.split("/"):
        if not part:
            continue
        toks |= set(re.findall(r"[a-z0-9]+", part.replace("-", " ")))
    return toks

def _path_depth(u: str) -> int:
    p = urlparse(u).path.strip("/")
    return 0 if not p else len([x for x in p.split("/") if x])

def _similarity(a: str, b: str) -> float:
    """Score combinado: similitud difusa + jaccard de tokens."""
    a2, b2 = _apply_synonyms(a), _apply_synonyms(b)
    ta, tb = _tokens(a2), _tokens(b2)
    jacc = (len(ta & tb) / len(ta | tb)) if (ta and tb) else 0.0
    fuzzy = difflib.SequenceMatcher(None, _norm(a2), _norm(b2)).ratio()
    return 0.6 * fuzzy + 0.4 * jacc

# === Helper simple para forzar español en cualquier consulta al motor ===
def _to_es(q: str, strict: bool = True) -> str:
    """Instrucción para responder en español con el contexto recuperado.
    strict=True: exige declarar "No tengo evidencia suficiente..." si el contexto no alcanza.
    strict=False: permite sintetizar con el mejor contexto disponible sin forzar mensaje negativo.
    """
    base = (
        "Responde SIEMPRE en español, de forma clara y profesional. "
        "Usa PREFERENTEMENTE la información proporcionada en el contexto del sitio oficial de la UESVALLE. "
    )
    if strict:
        base += (
            "Si el contexto NO contiene evidencia suficiente para responder con certeza, responde: "
            "'No tengo evidencia suficiente en el sitio oficial para responder con precisión.' y sugiere la sección más relacionada. "
        )
    return base + f"Pregunta: {q}"

# ============================ índice semántico ===============================
# Política requerida: el chatbot debe responder 100% usando contenido indexado del
# sitio oficial. Se fuerza el modo LlamaIndex y se evita el uso de GPT externo.
# Además, se privilegia modo extractivo para minimizar cualquier alucinación.

# Forzar configuración independiente de variables de entorno (el requerimiento del usuario):
EXACT_MODE = True          # solo fragmentos literales / evidencia directa
ANSWER_MODE = "llama"      # nunca usar rama 'gpt'

@lru_cache(maxsize=1)
def _get_index():
    """Carga (o construye si falta) el índice persistido del sitio.
    Problema detectado: tests y llamadas directas a `responder_pregunta` ocurrían
    antes de que el evento de startup (webchat.main) construyera el índice,
    resultando en respuestas vacías/fallback. Solución: si la carpeta de
    almacenamiento está vacía intentar construir el índice automáticamente.
    """
    if not _LLAMA_AVAILABLE:
        return None
    try:
        needs_build = not (os.path.exists(STORAGE_DIR) and os.listdir(STORAGE_DIR))
        # Si está desactivado el auto-build (p.ej. en Hugging Face Spaces), no intentar crawl/index
        if needs_build and not AUTO_BUILD_INDEX:
            return None
        # Detección adicional de entorno Space (variable SPACE_ID presente) para ser conservador
        if needs_build and os.environ.get("SPACE_ID") and not AUTO_BUILD_INDEX:
            return None
        if needs_build and AUTO_BUILD_INDEX:
            try:
                from chatbot.indexer import crear_o_cargar_indice
                crear_o_cargar_indice()
            except Exception:
                pass
        embed = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
        Settings.embed_model = embed
        storage = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        indices = load_indices_from_storage(storage, embed_model=embed)
        return indices[0] if indices else None
    except Exception:
        return None

@lru_cache(maxsize=1)
def _load_lexical_fallback():
    try:
        if os.path.exists(LEXICAL_INDEX_PATH):
            with open(LEXICAL_INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("docs", [])
    except Exception:
        return []
    return []

@lru_cache(maxsize=8)
def _get_engine(top_k: int):
    if not _LLAMA_AVAILABLE:
        return None
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=top_k)
    return RetrieverQueryEngine(
        retriever=retriever,
        response_synthesizer=get_response_synthesizer(response_mode="compact"),
    )

def _first_pass(q: str):
    if not _LLAMA_AVAILABLE:
        return []
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=TOP_K)
    xs = [n for n in retriever.retrieve(q) if getattr(n, "score", None) is not None]
    xs.sort(key=lambda n: n.score, reverse=True)
    return xs

def _second_pass(q: str):
    """Recall ampliado: normaliza + sinónimos + keywords como variantes."""
    base = _apply_synonyms(q)
    kws = " ".join(_tokens(base))
    variants = [q, base] + ([kws] if kws else [])
    seen, merged = set(), []
    if not _LLAMA_AVAILABLE:
        return []
    retriever = VectorIndexRetriever(index=_get_index(), similarity_top_k=TOP_K_FALLBACK)
    for v in variants:
        for n in retriever.retrieve(v):
            nid = getattr(n.node, "node_id", None) or id(n.node)
            if nid in seen:
                continue
            seen.add(nid)
            if getattr(n, "score", None) is not None:
                merged.append(n)
    merged.sort(key=lambda n: n.score, reverse=True)
    return merged

# ============================ respuestas extractivas =========================

def _node_text(n) -> str:
    try:
        node = getattr(n, "node", n)
        if hasattr(node, "get_content"):
            return node.get_content(metadata_mode="none") or ""
        # LlamaIndex Node has .text en muchas versiones
        return getattr(node, "text", "") or str(node)
    except Exception:
        return ""

_SENT_SPLIT = re.compile(r"(?<=[\.!?])\s+(?=[A-ZÁÉÍÓÚÑ])")

def _split_sentences_es(text: str) -> list[str]:
    t = text.strip().replace("\r", "\n")
    # Preservar saltos de párrafo como límites fuertes
    parts = []
    for para in re.split(r"\n{2,}", t):
        para = " ".join(para.split())
        if not para:
            continue
        parts.extend(_SENT_SPLIT.split(para))
    # fallback simple si nada se partió
    return [p.strip() for p in parts if p.strip()] or [s.strip() for s in re.split(r"[\.!?]\s+", t) if s.strip()]

def _score_sentence(sent: str, toks: set[str]) -> float:
    if not sent:
        return 0.0
    s_norm = _norm(sent)
    hits = sum(1 for t in toks if re.search(rf"\b{re.escape(t)}\b", s_norm))
    if hits == 0:
        return 0.0
    # preferir sentencias de longitud media
    length_penalty = abs(len(sent) - 180) / 180.0  # 0 en ~180 chars
    return hits - 0.25 * length_penalty

_BOILERPLATE_TERMS = {"cookie","cookies","gdpr","consentimiento","privacidad","estadística","marketing"}
_CONTACT_TERMS = {"tel","tel.","telefono","teléfono","correo","email","dirección","horario","horarios","contacto"}
_NOISY_TERMS = {"powered","nexura","facebook","instagram","youtube","x ","twitter","mapa del sitio","política","políticas","terminos","términos","condiciones","pqrsdf","chat","iniciar sesión","desplegar navegación","idiomas","configuración por defecto"}
_NAV_NOISE = {"iniciar sesión","desplegar navegación","idiomas","configuración","alto contraste","solo texto","mapa del sitio","nuestras funciones","nuestra entidad","transparencia y acceso","atención y servicios","participa","calendario de eventos","publicaciones","compartir","buscar","facebook","twitter","linkedin","whatsapp"}

def _is_boilerplate(text: str) -> bool:
    t = text.lower()
    return any(b in t for b in _BOILERPLATE_TERMS)

def _extract_exact_answer(q: str, nodes: list, max_chars: int = 700) -> str:
    """Devuelve oraciones LITERALES de los primeros nodos relevantes.
    Ignora nodos y oraciones marcadas como boilerplate (cookies, etc.).
    """
    toks = _tokens(q)
    if not nodes:
        return ""
    cand_sents: list[tuple[float,str]] = []
    for n in nodes[:7]:  # ampliar ligeramente el pool
        text = _node_text(n)
        if not text or _is_boilerplate(text):
            continue
        for s in _split_sentences_es(text):
            if _is_boilerplate(s):
                continue
            sc = _score_sentence(s, toks)
            if sc > 0:
                # penalizar frases dominadas por contacto / ruido si consulta es conceptual
                s_norm = _norm(s)
                if any(t in s_norm for t in _NOISY_TERMS):
                    sc -= 1.2
                # Filtrado adicional para consultas que no son misión/visión: remover navegación explícita
                qnorm = _norm(q)
                if not any(w in qnorm for w in ["mision","misión","vision","visión"]):
                    if any(nav in s_norm for nav in _NAV_NOISE):
                        sc -= 1.0
                # Si la pregunta busca mision/vision/funciones/horarios, priorizar frases que contengan la palabra
                qn = _norm(q)
                if any(w in qn for w in ["mision","vision","funciones","horarios"]):
                    if any(k in s_norm for k in ["mision","visión","vision","funciones","horarios"]):
                        sc += 0.8
                    # heurística misión: párrafo puede iniciar con 'somos la entidad'
                    if "mision" in qn and "somos la entidad" in s_norm:
                        sc += 0.9
                    # degradar frases de contacto para estas categorías
                    if any(ct in s_norm for ct in _CONTACT_TERMS) and not any(k in s_norm for k in ["mision","visión","vision","funciones"]):
                        sc -= 1.0
                    # degradar teléfonos explícitos
                    if re.search(r"\+?\d[\d\s().-]{6,}", s_norm):
                        sc -= 1.0
                if sc > 0:
                    cand_sents.append((sc, s))
    cand_sents.sort(key=lambda x: x[0], reverse=True)
    if not cand_sents:
        # fallback: usar primeras oraciones del primer nodo no boilerplate
        for n in nodes:
            text = _node_text(n)
            if text and not _is_boilerplate(text):
                sents = _split_sentences_es(text)[:3]
                return " ".join(sents)[:max_chars].strip()
        return ""
    # Filtro contextual: si la consulta es sobre misión/visión, excluir bloques de contacto
    ask_mv = any(w in _norm(q) for w in ["mision","visión","vision","que es la uesvalle","qué es la uesvalle","que es la entidad","visión de la entidad","mision de la entidad"])
    out = []
    total = 0
    for _, s in cand_sents:
        if ask_mv and any(ct in _norm(s) for ct in _CONTACT_TERMS):
            continue
        if s in out:
            continue
        if total + len(s) + 1 > max_chars:
            break
        out.append(s)
        total += len(s) + 1
        if total >= max_chars:
            break
    return " ".join(out).strip()

# ===================== respuesta literal estructurada (multi campos) ========
_CATEGORY_PATTERNS = {
    "mision": re.compile(r"\bmis[ií]on\b", re.I),
    "vision": re.compile(r"\bvis[ií]on\b", re.I),
    "horarios": re.compile(r"\bhorarios?\b", re.I),
    "funciones": re.compile(r"\bfunciones?\b|\bfunci[oó]n(es)?\b|\bdeberes?\b", re.I),
}

_CATEGORY_PHRASES = {
    # Ajustado para coincidir con los tests que buscan 'La misión de la UESVALLE es'
    "mision": "La misión de la UESVALLE es:",
    "vision": "La visión de la UESVALLE es:",
    "horarios": "Los horarios de la UESVALLE son:",
    "funciones": "Las funciones de la UESVALLE son:",
}

def _structured_literals_from_nodes(q: str, nodes: list, per_cat_max_sent: int = 2) -> dict:
    q_norm = _norm(q)
    requested = {c for c, pat in _CATEGORY_PATTERNS.items() if pat.search(q_norm)}
    if "mision" in q_norm and "vision" in q_norm:
        requested |= {"mision", "vision"}
    if not requested:
        return {}
    results = {c: [] for c in requested}
    for n in nodes[:25]:
        text = _node_text(n)
        if not text or _is_boilerplate(text):
            continue
        # limpieza de bloques de navegación repetitivos antes de partir en oraciones
        cleaned_lines = []
        for line in re.split(r"[\n]+", text):
            ln = _norm(line)
            if not line.strip():
                continue
            if any(noise in ln for noise in _NAV_NOISE):
                continue
            if sum(1 for ct in _CONTACT_TERMS if ct in ln) >= 3:
                continue
            cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)
        # Recorte específico para funciones: eliminar prefijos de redes / compartir
        if "funciones" in requested:
            # Conservamos solo párrafos con 'funcion' o 'funciones' y descartamos navegación total.
            func_blocks = []
            for block in re.split(r"\n{1,}", text):
                bn = _norm(block)
                if any(noise in bn for noise in _NAV_NOISE):
                    continue
                if re.search(r"configuracion por defecto|tamaño de fuente|iniciar sesion|iniciar sesión", bn):
                    continue
                if "funcion" in bn:
                    func_blocks.append(block.strip())
            if func_blocks:
                text = "\n".join(func_blocks)
        prev_was_mission_heading = False
        for sent in _split_sentences_es(text):
            if _is_boilerplate(sent):
                continue
            s_norm = _norm(sent)
            if any(ct in s_norm for ct in _CONTACT_TERMS) and ("mision" in requested or "vision" in requested) and "horarios" not in requested:
                continue
            for cat, pat in _CATEGORY_PATTERNS.items():
                if cat in requested:
                    if pat.search(s_norm):
                        if sent not in results[cat]:
                            results[cat].append(sent.strip())
                        if cat == "mision":
                            prev_was_mission_heading = True
                        continue
                    # heurística misión: párrafo inmediatamente posterior al heading o contiene 'somos la entidad'
                    if cat == "mision" and (prev_was_mission_heading or "somos la entidad" in s_norm):
                        if sent not in results[cat]:
                            results[cat].append(sent.strip())
                        prev_was_mission_heading = False
                    # heurística funciones: preferir párrafos sustantivos (>60 chars) que contengan 'funcion'
                    if cat == "funciones" and len(sent) > 40 and re.search(r"funcion", s_norm):
                        if sent not in results[cat]:
                            results[cat].append(sent.strip())
    # Fallback específico si misión/visión siguen vacías
    for needed in ["mision","vision"]:
        if needed in requested and not results.get(needed):
            cand_blocks = []
            for n in nodes:
                txt = _node_text(n) or ""
                if not txt:
                    continue
                for block in re.split(r"\n+", txt):
                    bn = _norm(block)
                    if any(noise in bn for noise in _NAV_NOISE):
                        continue
                    if any(t in bn for t in ["configuracion","tamaño","idiomas","iniciar sesion","desplegar","mapa del sitio","facebook","twitter","linkedin","whatsapp"]):
                        continue
                    if len(block) < 40:
                        continue
                    if needed == "mision" and re.search(r"mis[ií]on", bn):
                        # Preferir párrafos sustanciales que contengan verbo y 'somos'
                        score = len(block)
                        if "somos" in bn:
                            score += 50
                        cand_blocks.append((score, block.strip()))
                    elif needed == "vision" and re.search(r"vis[ií]on", bn):
                        score = len(block)
                        cand_blocks.append((score, block.strip()))
            if cand_blocks:
                cand_blocks.sort(reverse=True)
                top_blocks = [b for _, b in cand_blocks[:per_cat_max_sent]]
                results[needed] = top_blocks
    compact = {}
    for cat, sents in results.items():
        if sents:
            filt = []
            for s in sents:
                sn = _norm(s)
                if any(nav in sn for nav in ["publicaciones","compartir","buscar","mapa del sitio","iniciar sesion","desplegar"]):
                    continue
                filt.append(s)
            if not filt:
                filt = sents
            ordered = sorted(filt, key=lambda s: len(s), reverse=True)
            compact[cat] = " ".join(ordered[:per_cat_max_sent]).strip()
    return compact

def _build_structured_answer(q: str, nodes: list) -> str:
    data = _structured_literals_from_nodes(q, nodes)
    qn = _norm(q)
    # Fallback regex profundo si falta misión/visión
    if ("mision" in qn or "visión" in qn or "vision" in qn) and ("mision" not in data or "vision" not in data):
        all_text = []
        for n in nodes[:40]:
            t = _node_text(n)
            if t:
                all_text.append(t)
        joined = "\n".join(all_text)
        low = joined
        # misión
        if "mision" not in data:
            m_match = re.search(r"(M[íi]s[ií]on[^\n]{40,600})", joined, re.I)
            if m_match:
                block = m_match.group(1).strip()
                # limpiar navegación y contactos
                bn = _norm(block)
                if not any(nav in bn for nav in _NAV_NOISE):
                    data["mision"] = re.sub(r"\s+", " ", block)
        if "vision" not in data:
            v_match = re.search(r"(V[íi]s[ií]on[^\n]{40,600})", joined, re.I)
            if v_match:
                block = v_match.group(1).strip()
                bn = _norm(block)
                if not any(nav in bn for nav in _NAV_NOISE):
                    data["vision"] = re.sub(r"\s+", " ", block)
        # Búsqueda línea exacta si aún vacías (más agresivo)
        def _clean(line: str) -> str:
            line = re.sub(r"Buscar\s+", "", line)
            line = re.sub(r"Misión, visión, funciones y deberes", "", line, flags=re.I)
            return re.sub(r"\s+", " ", line).strip()
        if "mision" not in data:
            for ln in joined.splitlines():
                if re.search(r"M[íi]s[ií]on\s+Somos", ln):
                    data["mision"] = _clean(ln)
                    break
        if "vision" not in data:
            for ln in joined.splitlines():
                if re.search(r"V[íi]s[ií]on", ln) and len(ln) > 40:
                    data["vision"] = _clean(ln)
                    break
    if not data:
        return ""
    order = ["mision", "vision", "horarios", "funciones"]
    lines = []
    for cat in order:
        if cat in data:
            header = _CATEGORY_PHRASES.get(cat, cat.capitalize() + ":")
            val = data[cat]
            if cat == "funciones":
                # Eliminar bloques de navegación, contacto y métricas.
                val = re.sub(r"Número de visitas a esta página.*", "", val, flags=re.I)
                val = re.sub(r"Fecha de publicación.*", "", val, flags=re.I)
                val = re.sub(r"Última modificación.*", "", val, flags=re.I)
                # Cortar en primer bloque extenso para evitar cola de contacto.
                parts = re.split(r"Horarios de atención|Contáctenos|Redes sociales|Imprimir|Volver arriba", val)
                if parts:
                    val = parts[0]
            lines.append(f"{header} {val.strip()}")
    return "\n".join(lines).strip()

# ===================== contenido canónico directo ===========================
def _canonical_page_text(url: str) -> str:
    """Extrae texto concatenado de todas las secciones cuyo URL coincide exactamente con la página canónica.
    Filtra bloques de contacto y ruido."""
    items = _sections()
    acc = []
    for it in items:
        if it.get("url") != url:
            continue
        raw = " ".join(filter(None, [it.get("text"), it.get("section")]))
        raw = raw.strip()
        if not raw:
            continue
        # dividir por saltos para filtrar navegación
        kept = []
        for line in re.split(r"[\n]+", raw):
            ln = _norm(line)
            if not line.strip():
                continue
            if any(noise in ln for noise in _NAV_NOISE):
                continue
            if any(t in ln for t in _NOISY_TERMS):
                continue
            kept.append(line)
        if not kept:
            continue
        cleaned = " \n".join(kept)
        # evitar bloques dominados por contacto
        nrm = _norm(cleaned)
        if sum(1 for t in _CONTACT_TERMS if t in nrm) >= 3:
            continue
        acc.append(cleaned)
    return "\n".join(acc).strip()

class _DummyNode:
    def __init__(self, text: str, url: str):
        self.text = text
        self.metadata = {"source": url, "url": url}
    def get_content(self, metadata_mode: str = "none"):
        return self.text

def _make_canonical_nodes(query: str) -> list:
    qn = _norm(query)
    # reutilizar KEYWORD_LINK_MAP para contenido directo (no solo link)
    live_mv = None
    if any(w in qn for w in ["mision","vision","mision vision","misión","visión"]):
        live_mv = _fetch_live_mision_vision()
        if not live_mv:
            # Fallback snapshot local
            snap = _load_snapshot_mision_vision()
            if snap:
                live_mv = snap
    for key, url in KEYWORD_LINK_MAP.items():
        if key in qn:
            page_text = _canonical_page_text(url)
            # Intentar usar snapshot si se trata de misión/visión y el page_text está vacío o no contiene misión
            if any(w in qn for w in ["mision","vision","misión","visión"]) and live_mv:
                mission_par = live_mv.get("mision")
                vision_par = live_mv.get("vision")
                parts = []
                if mission_par:
                    # Separar encabezado y párrafo para no unir "Misión Somos" como una sola oración.
                    parts.append("Misión\n" + mission_par.strip())
                if vision_par:
                    parts.append("Visión\n" + vision_par.strip())
                if parts:
                    page_text = "\n" + "\n".join(parts)
            if page_text:
                if any(w in qn for w in ["mision","visión","vision"]):
                    # Segmentar nuevamente; si snapshot ya prefijó encabezados se mantendrá
                    mission_par = None
                    vision_par = None
                    for block in re.split(r"\n+", page_text):
                        bn = _norm(block)
                        # evitar capturar líneas del README (formato esperado, etc.)
                        if "formato esperado" in bn or "el chatbot parseara" in bn:
                            continue
                        if ("mision" in bn or "misión" in bn) and mission_par is None:
                            mission_par = block.strip()
                            continue
                        if ("vision" in bn or "visión" in bn) and vision_par is None:
                            vision_par = block.strip()
                            continue
                    if live_mv:
                        # Construir solo una vez misión y visión y no repetir encabezados múltiples
                        if live_mv.get("mision"):
                            mission_par = "Misión " + live_mv.get("mision").strip()
                        if live_mv.get("vision"):
                            vision_par = "Visión " + live_mv.get("vision").strip()
                    combined = []
                    if mission_par:
                        combined.append(mission_par)
                    if vision_par:
                        combined.append(vision_par)
                    if combined:
                        page_text = "\n".join(combined)
                node = _DummyNode(page_text, url)
                wrapper = type("CanScore", (), {})()
                wrapper.node = node
                wrapper.score = 0.97  # prioridad muy alta
                return [wrapper]
    return []

# --------------------- Snapshot local misión/visión -------------------------
def _load_snapshot_mision_vision(path: str = None) -> dict:
    """Lee un snapshot HTML/TXT local (sin hardcodear contenido) y extrae misión y visión.
    El archivo debe contener encabezados 'Misión' y 'Visión' y sus párrafos posteriores.
    """
    base_dir = os.path.join(os.path.dirname(SECTIONS_CATALOG_PATH), "manual")
    repo_manual_dir = os.path.join(REPO_DATA_DIR, "manual")
    dyn_candidates = []
    if path is None:
        for d in [base_dir, repo_manual_dir]:
            if not os.path.isdir(d):
                continue
            dyn_candidates.extend([
                os.path.join(d, "mision_vision.html"),
                os.path.join(d, "mision_vision.txt"),
                os.path.join(d, "README_mision_vision.txt"),
            ])
        candidates = dyn_candidates
    else:
        candidates = [path]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        return {}
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return {}
    soup = BeautifulSoup(raw, "html.parser") if "<" in raw and ">" in raw else None
    text_blocks = []
    if soup:
        for tag in soup.find_all(["h1","h2","h3","strong","p","div","span"]):
            txt = re.sub(r"\s+", " ", tag.get_text(" ").strip())
            if txt:
                text_blocks.append(txt)
    else:
        for line in raw.splitlines():
            line2 = re.sub(r"\s+", " ", line).strip()
            if line2:
                text_blocks.append(line2)
    mission = []
    vision = []
    current = None
    def _is_instruction(line: str) -> bool:
        l = line.lower()
        return (
            "formato esperado" in l or
            "el chatbot parseará" in l or
            "no edites" in l or
            l.startswith("coloca aqui") or
            l.startswith("coloca aquí")
        )
    for blk in text_blocks:
        low = blk.lower()
        # Detectar encabezados exactos
        if re.fullmatch(r"mis[ií]ón", low):
            current = "mision"
            continue
        if re.fullmatch(r"vis[ií]ón", low):
            current = "vision"
            continue
        # Cese de captura si aparece línea instructiva o muy corta
        if _is_instruction(low):
            current = None
            continue
        if current == "mision":
            if not blk.strip():
                current = None
                continue
            # Aceptar párrafos cortos del snapshot (placeholders) ≥15 chars
            if len(blk) < 15:
                continue
            if not re.search(r"\+?\d[\d\s().-]{6,}", low):
                mission.append(blk)
        elif current == "vision":
            if not blk.strip():
                current = None
                continue
            if len(blk) < 15:
                continue
            if not re.search(r"\+?\d[\d\s().-]{6,}", low):
                vision.append(blk)
        # Si ya capturamos al menos un párrafo y llega un bloque corto < 25 chars, asumimos fin
        if current == "mision" and mission and len(blk) < 25:
            current = None
        if current == "vision" and vision and len(blk) < 25:
            current = None
    out = {}
    if mission:
        out["mision"] = re.sub(r"\s+", " ", " ".join(mission)).strip()
    if vision:
        out["vision"] = re.sub(r"\s+", " ", " ".join(vision)).strip()
    return out

def _direct_funciones() -> Optional[str]:
    """Extracción directa de funciones desde catálogos locales.
    Coincide sólo con la palabra 'función'/'funciones' (no 'funcionamiento') y filtra navegación/contacto.
    """
    rutas = [
        os.path.join(DATA_DIR, "sections_catalog.json"),
        os.path.join(DATA_DIR, "doc_catalog.json"),
        SECTIONS_CATALOG_PATH,
    ]
    ruido_nav = {"iniciar sesión","desplegar navegación","idiomas","configuración","alto contraste","solo texto","mapa del sitio","buscar","facebook","twitter","linkedin","whatsapp","compartir"}
    ruido_contacto = {"tel","tel.","telefono","teléfono","correo","email","dirección","horario","horarios","contacto"}
    pattern_func = re.compile(r"\bfunci[oó]n(?:es)?\b", re.I)
    candidatos: list[str] = []
    for ruta in rutas:
        if not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        bloques = []
        if isinstance(data, list):
            bloques = data
        elif isinstance(data, dict):
            if isinstance(data.get("items"), list):
                bloques = data["items"]
            elif isinstance(data.get("sections"), list):
                bloques = data["sections"]
            elif isinstance(data.get("documents"), list):
                bloques = data["documents"]
        for b in bloques:
            if isinstance(b, dict):
                texto = " ".join(filter(None,[b.get("text"), b.get("section"), b.get("page_title"), b.get("h1")]))
            else:
                texto = str(b)
            texto = re.sub(r"\s+"," ", texto).strip()
            if not texto:
                continue
            low = texto.lower()
            if not pattern_func.search(low):
                continue
            if "funcionamiento" in low:
                continue
            partes = re.split(r"\n{2,}|(?<=[\.!?])\s+", texto)
            for p in partes:
                pn = p.strip()
                if len(pn) < 50:
                    continue
                pl = pn.lower()
                if not pattern_func.search(pl):
                    continue
                if "funcionamiento" in pl:
                    continue
                if any(r in pl for r in ruido_nav):
                    continue
                if any(r in pl for r in ruido_contacto):
                    continue
                if re.search(r"visitas|publicado|última modificación|fecha de publicación", pl):
                    continue
                candidatos.append(pn)
    if not candidatos:
        return None
    dedup = []
    seen = set()
    for c in candidatos:
        k = c.lower()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(c)
    dedup.sort(key=len, reverse=True)
    top = dedup[:4]
    oraciones = []
    for bloque in top:
        sents = re.split(r"(?<=[\.!?])\s+", bloque)
        for s in sents:
            sl = s.lower().strip()
            if pattern_func.search(sl) and "funcionamiento" not in sl:
                if 40 <= len(s) <= 400 and not any(r in sl for r in ruido_nav) and not any(r in sl for r in ruido_contacto):
                    oraciones.append(s.strip())
    base = oraciones if oraciones else top
    final = []
    seen2 = set()
    for s in base:
        k = s.lower()
        if k in seen2:
            continue
        seen2.add(k)
        final.append(s.strip())
    if not final:
        return None
    # Quitar tarjetas/catálogo (indicadores 'Publicaciones ›', 'Documentos ›')
    final = [f for f in final if not re.search(r"\b(publicaciones|documentos)\b", f.lower())]
    if not final:
        return None
    encabezado = "Funciones de la UESVALLE:" if not final[0].lower().startswith("las funciones") else ""
    cuerpo = "\n- " + "\n- ".join(final)
    return (encabezado + cuerpo).strip()

# ============================ síntesis estilizada ============================
def _stylize_answer(raw: str, pregunta: str, nodes) -> str:
    """Reescribe de forma clara y cohesionada sin agregar información ajena.
    Usa sólo el contenido literal recuperado. Si el modo de estilo está
    desactivado o el texto es muy corto, devuelve el original.
    """
    if not STYLE_SUMMARIZE or not raw or len(raw.split()) < 30 or not _LLAMA_AVAILABLE:
        return raw
    # Construimos bloque de evidencia (limitado) para el prompt
    evidencias = []
    for n in nodes[:4]:
        txt = _node_text(n)
        if txt:
            evidencias.append(txt[:1800])
    joined = "\n\n".join(evidencias)
    # Prompt instructivo ultra-restricto
    prompt = (
        "Redacta en español formal y claro una respuesta a la pregunta dada, "
        "basándote EXCLUSIVAMENTE en las frases que siguen entre <evidencia>. "
        "No inventes datos, no añadas opiniones, no repitas teléfonos, correos ni horarios salvo que la pregunta explícitamente los solicite. "
        "Si no hay información suficiente para cubrir un punto, omite ese punto sin especular. "
        "Mantén 1-2 párrafos breves y, si procede, una lista con viñetas. \n\n"
        f"<pregunta>{pregunta}</pregunta>\n<evidencia>{raw}\n\n{joined}</evidencia>"
    )
    try:
        resp = _get_engine(TOP_K).query(prompt)
        txt = str(resp).strip()
        # validación mínima: debe contener algún token de la pregunta
        pq_toks = _tokens(pregunta)
        if pq_toks and not any(t in _norm(txt) for t in pq_toks):
            return raw  # fallback si perdió foco
        # evitar que la versión estilizada sea más corta que la evidencia útil
        if len(txt.split()) < len(raw.split()) * 0.6:
            return raw
        return txt
    except Exception:
        return raw

def _sources_from_nodes(nodes, limit=3):
    urls = []
    seen = set()
    for n in nodes:
        md = getattr(getattr(n, "node", n), "metadata", {}) or {}
        src = md.get("source") or md.get("url")
        if not src:
            continue
        if src in seen:
            continue
        seen.add(src)
        urls.append(src)
        if len(urls) >= limit:
            break
    return urls

# ===================== catálogo de secciones (enlaces) =======================

@lru_cache(maxsize=1)
def _sections():
    """Carga el catálogo de secciones HTML (generado por el crawler)."""
    if os.path.exists(SECTIONS_CATALOG_PATH):
        with open(SECTIONS_CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    return []

def _is_link_intent(q: str) -> bool:
    ql = _norm(q)
    # Palabras clave directas
    direct = [
        "enlace","link","seccion","sección","ruta","url","acceder","ir a","llevar",
        "abrir","consultar","donde esta","dónde está","quiero ver","ver sección",
        "direccion","dirección","camino","navegar","menu","menú","apartado","subsección",
        "donde encuentro","dónde encuentro","en que parte","en qué parte","como llegar","cómo llegar",
    ]
    if any(t in ql for t in direct):
        return True
    # Patrones comunes de navegación
    nav_patterns = [
        r"\b(donde|dónde) (esta|está|encuentro)\b",
        r"\b(como|cómo) (llego|ir|acceder)\b",
        r"\b(en\s+que|en\s+qué)\s+parte\b",
        r"\b(llevar(me)?|navegar a|abrir)\b",
    ]
    return any(re.search(p, ql, re.I) for p in nav_patterns)

def _resolve_section_candidates(q: str, k: int = 3):
    """Devuelve hasta k URLs ordenadas por score para la sección pedida."""
    items = _sections()
    if not items:
        return []

    q_toks = _tokens(q)
    scored = []

    for it in items:
        cand_text = " ".join([
            it.get("text", ""),
            it.get("page_title", ""),
            it.get("h1", ""),
            it.get("section", ""),
        ]).strip()

        s = _similarity(q, cand_text)

        # bonus si palabras de la consulta aparecen en el TEXTO del enlace
        txt_toks = _tokens(it.get("text", ""))
        if q_toks and q_toks.issubset(txt_toks):
            s += 0.20

        # bonus si tokens del PATH coinciden con la consulta
        path_toks = _path_tokens(it.get("url", ""))
        if q_toks and len(q_toks & path_toks) > 0:
            s += 0.15

        # preferir rutas internas profundas (evitar la home)
        depth = _path_depth(it.get("url", ""))
        s += min(depth, 6) * 0.05
        if depth == 0:
            s -= 0.25

        scored.append((s, it["url"], it.get("text",""), it.get("section","")))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(url, txt, score, section) for score, url, txt, section in scored[:k]]

def _resolve_section_url(q: str) -> tuple[str,str] | None:
    # Lookup directo por palabra clave exacta normalizada
    qn = _norm(q)
    # Revisar combinaciones presentes en mapping manual + dinámico
    for key, url in {**DYNAMIC_LINK_MAP, **KEYWORD_LINK_MAP}.items():
        if key in qn:
            return (url, key)
    cands = _resolve_section_candidates(q, k=1)
    if not cands:
        return None
    url, _, score, section = cands[0]
    return (url, section)

# ============================ clasificación intención =========================

def _detect_intent(q: str) -> Intent:
    """Uso del nuevo clasificador de reglas. Devuelve Intent dataclass."""
    return classify_intent(q)

# ============================= contexto conversacional ======================
_CONV_HISTORY: list[tuple[str,str]] = []  # [(usuario, bot)]
_MAX_HISTORY = 3

def _push_history(user_q: str, bot_a: str):
    _CONV_HISTORY.append((user_q.strip(), bot_a.strip()))
    if len(_CONV_HISTORY) > _MAX_HISTORY:
        _CONV_HISTORY.pop(0)

def _augment_with_history(q: str) -> str:
    """Si la consulta es muy corta o tiene pronombres, adjuntar breve contexto previo."""
    if len(_tokens(q)) > 2 and not re.search(r"\b(eso|esa|ese|allí|ahi|ahí|alli|allá|alla|el|la|los|las)\b", _norm(q)):
        return q
    if not _CONV_HISTORY:
        return q
    # Concatenar las últimas respuestas (solo texto del bot) para dar contexto
    prev = " \n".join(a for _, a in _CONV_HISTORY[-_MAX_HISTORY:])
    return f"Contexto previo: {prev}\nPregunta actual: {q}"  # se pasa así al motor

# =============================== guard de PII ================================
_PII_PATTERNS = [
    re.compile(r"\b\d{7,10}\b"),               # posibles números de identificación
    re.compile(r"\b(?:\+?57)?\s?\d{3}[\s-]?\d{3}[\s-]?\d{4}\b"),  # teléfonos colombianos
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # correos
]

def _contains_pii(q: str) -> bool:
    return any(p.search(q) for p in _PII_PATTERNS)

# =============================== métricas simples ===========================
_STATS = {"total":0,"intent":{},"fallbacks":0,"avg_latency":0.0}
_STAGE_TIMES: list[tuple[str,float]] = []  # última consulta detallada

def get_last_stage_times() -> list[tuple[str,float]]:
    return list(_STAGE_TIMES)

def _record_stats(intent: Intent, latency: float, fallback: bool):
    _STATS["total"] += 1
    _STATS["intent"].setdefault(intent.label, 0)
    _STATS["intent"][intent.label] += 1
    if fallback:
        _STATS["fallbacks"] += 1
    # media móvil simple
    t = _STATS["total"]
    _STATS["avg_latency"] = (_STATS["avg_latency"] * (t-1) + latency) / t

def get_metrics() -> dict:
    return _STATS.copy()

# ============================== small talk ===================================

def _is_small_talk(q: str) -> str | None:
    """Devuelve una respuesta corta si es small talk; si no, None."""
    if SMALL_TALK_PATTERNS["saludo"].search(q):
        return ("¡Hola! Soy el chatbot de la UESVALLE. Puedo guiarte por el sitio, "
                "dar enlaces a secciones y resumir contenidos. ¿En qué te ayudo?")
    if SMALL_TALK_PATTERNS["despedida"].search(q):
        return "¡Gracias por escribir! Si necesitas algo más, aquí estaré."
    if SMALL_TALK_PATTERNS["ayuda"].search(q):
        return ("Pídeme cosas como: “transparencia y acceso”, “plan anual de adquisiciones”, "
                "“directorios y teléfonos”, “misión y visión”, o envíame palabras sueltas.")
    return None

# ============================== interfaz QA =================================

def responder_pregunta(pregunta: str) -> str:
    """
    - SMALL TALK → respuesta breve.
    - ENLACE/RUTA/SECCIÓN → URL exacta + ruta de navegación.
    - CONTENIDO → índice semántico (dos pasadas, recall ampliado).
    - CATCH-ALL → intenta dar contexto útil.
    """
    if not pregunta:
        return "¿Qué te gustaría consultar del sitio de la UESVALLE?"

    # 0) Small talk
    st = _is_small_talk(pregunta)
    if st:
        return st

    start_t = time()
    # Cache rápida (normalización básica)
    q_norm_for_cache = _norm(pregunta)[:300]
    global _ANSWER_CACHE
    if '_ANSWER_CACHE' not in globals():
        _ANSWER_CACHE = {}
    if q_norm_for_cache in _ANSWER_CACHE:
        return _ANSWER_CACHE[q_norm_for_cache]

    # 1) Guard PII
    if _contains_pii(pregunta):
        msg = ("Por seguridad y privacidad, evita compartir datos personales (teléfonos, correos, identificación). "
               "Formúlame la consulta sin información sensible y con gusto te ayudo.")
        _record_stats(Intent("pii",1.0,["pii"]), time()-start_t, False)
        _push_history(pregunta, msg)
        return msg

    # Early link mapping (independiente de clasificación de intención). Evitar si es misión/visión o funciones (para poder extraer texto).
    norm_q_for_link = _norm(pregunta)
    if not any(x in norm_q_for_link for x in ["mision","misión","vision","visión","funcion","función","funciones"]):
        # Incluir mapping dinámico además del manual para early link
        for k, u in {**DYNAMIC_LINK_MAP, **KEYWORD_LINK_MAP}.items():
            if k in norm_q_for_link:
                ans_link = f"Aquí tienes el enlace oficial: {u}"
                _push_history(pregunta, ans_link)
                _ANSWER_CACHE[q_norm_for_cache] = ans_link
                return ans_link

    # Respuesta DIRECTA para misión / visión (evita que documentos ajenos dominen)
    norm_q = _norm(pregunta)
    wants_mision_only = ("mision" in norm_q or "misión" in norm_q) and not ("vision" in norm_q or "visión" in norm_q)
    wants_vision_only = ("vision" in norm_q or "visión" in norm_q) and not ("mision" in norm_q or "misión" in norm_q)
    wants_both_mv = (("mision" in norm_q or "misión" in norm_q) and ("vision" in norm_q or "visión" in norm_q)) or any(p in norm_q for p in ["mision vision","misión visión","mision y vision","misión y visión"])
    if wants_mision_only or wants_vision_only or wants_both_mv:
        snap = _load_snapshot_mision_vision() or {}
        if not snap:
            # Intentar fetch rápido (timeout reducido)
            snap = _fetch_live_mision_vision(timeout=1.0) or {}
        mission_par = snap.get("mision")
        vision_par = snap.get("vision")
        # Segundo intento si falta alguno
        if (wants_mision_only or wants_both_mv) and not mission_par:
            alt = _fetch_live_mision_vision(timeout=1.0)
            mission_par = alt.get("mision") if alt else mission_par
        if (wants_vision_only or wants_both_mv) and not vision_par:
            alt = _fetch_live_mision_vision(timeout=1.0)
            vision_par = alt.get("vision") if alt else vision_par
        out_lines = []
        if (wants_mision_only or wants_both_mv) and mission_par:
            out_lines.append(f"La misión de la UESVALLE es: {mission_par.strip()}")
        if (wants_vision_only or wants_both_mv) and vision_par:
            out_lines.append(f"La visión de la UESVALLE es: {vision_par.strip()}")
        if out_lines:
            ans_mv = "\n".join(out_lines)
            _push_history(pregunta, ans_mv)
            _ANSWER_CACHE[q_norm_for_cache] = ans_mv
            return ans_mv

    # Respuesta directa para funciones (antes de clasificación y retrieval)
    if any(t in norm_q for t in ["funcion","función","funciones","funciónes"]):
        funciones_live = _fetch_live_funciones(timeout=2.5)
        if not funciones_live:
            funciones_live = _direct_funciones()
        if funciones_live:
            _push_history(pregunta, funciones_live)
            _ANSWER_CACHE[q_norm_for_cache] = funciones_live
            return funciones_live
        # Fallback final: sólo enlace canónico si no se pudo extraer texto literal
        enlace_fun = KEYWORD_LINK_MAP.get("funciones") or KEYWORD_LINK_MAP.get("funciones y deberes")
        if enlace_fun:
            ans_fun_link = f"Aquí tienes el enlace oficial: {enlace_fun}"
            _push_history(pregunta, ans_fun_link)
            _ANSWER_CACHE[q_norm_for_cache] = ans_fun_link
            return ans_fun_link

    # 2) Clasificación de intención (enlace/general/específica/documento)
    t_stage_start = time()
    intent = _detect_intent(pregunta)
    _STAGE_TIMES.clear()
    _STAGE_TIMES.append(("clasificacion", time()-t_stage_start))

    # 2a) Documento: devolver fichas de catálogo de documentos si existen
    if intent.label == "document":
        # cargar catálogo de documentos ligero
        doc_path = os.path.join(STORAGE_DIR, "..", "doc_catalog.json")  # relativo al DATA_DIR
        # fallback real: usar DOC_CATALOG_PATH de config si se quisiera importarlo
        from chatbot.config import DOC_CATALOG_PATH
        path = DOC_CATALOG_PATH if os.path.exists(DOC_CATALOG_PATH) else doc_path
        items = []
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    items = json.load(f).get("items", [])
        except Exception:
            items = []
        # filtrar por coincidencia simple de tokens
        toks = _tokens(pregunta)
        matches = []
        for it in items:
            blob = " ".join([
                it.get("page_title",""), it.get("h1",""), it.get("link_text",""), it.get("section",""), it.get("doc_url",""),
            ])
            if any(t in _norm(blob) for t in toks):
                matches.append(it)
        matches = matches[:5]
        if matches:
            lines = ["Documentos relacionados:"]
            for m in matches:
                lines.append(f"- {m.get('link_text') or 'Documento'} → {m.get('doc_url')} (Página: {m.get('from_page')})")
            ans = "\n".join(lines)
        else:
            ans = ("No encontré documentos específicos asociados a tu búsqueda. "
                   "Prueba con palabras clave más concretas (ej.: 'PDF transparencia', 'formato PQRSD').")
        _record_stats(intent, time()-start_t, False)
        _push_history(pregunta, ans)
        return ans

    # 2b) Enlace explícito → devolver SOLO un enlace (el más probable/canónico)
    if intent.label == "link":
        best = _resolve_section_url(pregunta)
        if best:
            url, _ruta = best
            ans = f"Aquí tienes el enlace oficial: {url}"
            _record_stats(intent, time()-start_t, False)
            _push_history(pregunta, ans)
            return ans
        # Si no se encuentra, intenta sugerir el primer candidato disponible
        cands = _resolve_section_candidates(pregunta, k=1)
        if cands:
            url, _txt, _score, _ruta = cands[0]
            ans = f"Aquí tienes el enlace oficial: {url}"
            _record_stats(intent, time()-start_t, False)
            _push_history(pregunta, ans)
            return ans
        # Si no hay secciones, seguimos al contenido

    # Fallback temprano para términos inventados antes de iniciar retrieval costoso
    def _early_unknown(q: str) -> bool:
        tks = _tokens(q)
        if not tks:
            return False
        cat_blob = " ".join([it.get("text","") + " " + it.get("section","") for it in _sections()])
        norm_blob = _norm(cat_blob)
        missing = [t for t in tks if t not in norm_blob]
        return len(missing) >= max(2, int(len(tks)*0.7))
    if _early_unknown(pregunta):
        ans = ("No tengo evidencia suficiente en el sitio oficial para responder con precisión. "
               "Intenta con el nombre de una sección real (ej.: transparencia, misión y visión, PAA, PETI, PQRSD).")
        _record_stats(intent, time()-start_t, True)
        _push_history(pregunta, ans)
        _ANSWER_CACHE[q_norm_for_cache] = ans
        return ans

    # 2) Contenido — Pase 1 (preciso)
    aug_q = _augment_with_history(pregunta)
    # Ajuste de umbrales (bajados para mejorar recall temprano en sitio institucional)
    th1 = CONFIDENCE_THRESHOLD if ANSWER_MODE != "llama" else max(0.12, CONFIDENCE_THRESHOLD * 0.6)
    th2 = (CONFIDENCE_THRESHOLD * 0.7) if ANSWER_MODE != "llama" else max(0.09, CONFIDENCE_THRESHOLD * 0.45)

    if time()-start_t > MAX_QUERY_SECONDS:
        ans_timeout = ("Tiempo de procesamiento excedido antes de recuperar contenido. "
                        "Intenta reformular o espera unos segundos.")
        _record_stats(intent, time()-start_t, True)
        _push_history(pregunta, ans_timeout)
        _ANSWER_CACHE[q_norm_for_cache] = ans_timeout
        return ans_timeout

    t_retr1 = time()
    nodes = _first_pass(aug_q)
    # Inyección de contenido canónico si aplica y no es intención de enlace
    if intent.label != "link":
        canonical_nodes = _make_canonical_nodes(pregunta)
        if canonical_nodes:
            # Anteponer canónico manteniendo recuperación original para preservar párrafos
            nodes = canonical_nodes + nodes
    _STAGE_TIMES.append(("retrieval_1", time()-t_retr1))
    if nodes and nodes[0].score >= th1:
        if EXACT_MODE and intent.label in {"specific","general"} and ANSWER_MODE != "gpt":
            extract = _extract_exact_answer(pregunta, nodes)
            if extract:
                structured = _build_structured_answer(pregunta, nodes)
                if structured:
                    final = structured
                else:
                    final = extract
                _record_stats(intent, time()-start_t, False)
                _push_history(pregunta, final)
                _ANSWER_CACHE[q_norm_for_cache] = final
                return final
        # Modo GPT (si está habilitado) usa sólo el contenido recuperado como contexto
        if ANSWER_MODE == "gpt":
            ctx_blocks = []
            for n in nodes[:4]:
                text = _node_text(n)
                if not text:
                    continue
                md = getattr(getattr(n, "node", n), "metadata", {}) or {}
                title = md.get("section_title") or md.get("page_title") or ""
                if title:
                    ctx_blocks.append(f"[{title}]\n{text[:2500]}")
                else:
                    ctx_blocks.append(text[:2500])
            txt = answer_with_openai(ctx_blocks, pregunta)
        else:
            resp = _get_engine(TOP_K).query(_to_es(aug_q, strict=True))
            txt = str(resp).strip()
        _record_stats(intent, time()-start_t, False)
        _push_history(pregunta, txt)
        _ANSWER_CACHE[q_norm_for_cache] = txt
        return txt

    # 3) Contenido — Pase 2 (recall ampliado con sinónimos/keywords)
    if time()-start_t > MAX_QUERY_SECONDS:
        ans_timeout = ("Respuesta parcial: límite de tiempo alcanzado sin suficiente evidencia. "
                        "Reintenta con más detalle.")
        _record_stats(intent, time()-start_t, True)
        _push_history(pregunta, ans_timeout)
        _ANSWER_CACHE[q_norm_for_cache] = ans_timeout
        return ans_timeout

    t_retr2 = time()
    nodes2 = _second_pass(aug_q)
    if intent.label != "link":
        canonical_nodes = _make_canonical_nodes(pregunta)
        if canonical_nodes:
            nodes2 = canonical_nodes + nodes2
    _STAGE_TIMES.append(("retrieval_2", time()-t_retr2))
    if nodes2 and nodes2[0].score >= th2:
        if EXACT_MODE and intent.label in {"specific","general"} and ANSWER_MODE != "gpt":
            extract = _extract_exact_answer(pregunta, nodes2)
            if extract:
                structured = _build_structured_answer(pregunta, nodes2)
                if structured:
                    final = structured
                else:
                    final = extract
                _record_stats(intent, time()-start_t, False)
                _push_history(pregunta, final)
                _ANSWER_CACHE[q_norm_for_cache] = final
                return final
        if ANSWER_MODE == "gpt":
            ctx_blocks = []
            for n in nodes2[:4]:
                text = _node_text(n)
                if not text:
                    continue
                md = getattr(getattr(n, "node", n), "metadata", {}) or {}
                title = md.get("section_title") or md.get("page_title") or ""
                if title:
                    ctx_blocks.append(f"[{title}]\n{text[:2500]}")
                else:
                    ctx_blocks.append(text[:2500])
            txt = answer_with_openai(ctx_blocks, pregunta)
        else:
            resp = _get_engine(TOP_K_FALLBACK).query(_to_es(aug_q, strict=True))
            txt = str(resp).strip()
        _record_stats(intent, time()-start_t, False)
        _push_history(pregunta, txt)
        _ANSWER_CACHE[q_norm_for_cache] = txt
        return txt

    # Nuevo: si aún no alcanzamos umbral pero sí hay nodos, intenta generar con recall ampliado
    if nodes or 'nodes2' in locals():
        pool = nodes2 if (locals().get('nodes2')) else nodes
        if pool:
            if ANSWER_MODE == "gpt":
                ctx_blocks = []
                for n in pool[:4]:
                    text = _node_text(n)
                    if not text:
                        continue
                    md = getattr(getattr(n, "node", n), "metadata", {}) or {}
                    title = md.get("section_title") or md.get("page_title") or ""
                    if title:
                        ctx_blocks.append(f"[{title}]\n{text[:2500]}")
                    else:
                        ctx_blocks.append(text[:2500])
                txt = answer_with_openai(ctx_blocks, pregunta)
            else:
                txt = str(_get_engine(TOP_K_FALLBACK).query(_to_es(aug_q, strict=True))).strip()
            _record_stats(intent, time()-start_t, False)
            _push_history(pregunta, txt)
            _ANSWER_CACHE[q_norm_for_cache] = txt
            return txt

    # 4) Fallback definitivo (no hay evidencia suficiente)
    # Si tampoco hubo vector index (descarga falló) intentamos lexical fallback
    if not nodes and not nodes2:
        lex_docs = _load_lexical_fallback()
        if lex_docs:
            q_norm = _norm(pregunta)
            best = None
            best_score = 0.0
            toks = _tokens(pregunta)
            for d in lex_docs:
                text = d.get("text", "")
                if not text:
                    continue
                s_norm = _norm(text)
                # Score simple: cuenta de tokens presentes + fuzzy corta
                hits = sum(1 for t in toks if t in s_norm)
                if hits == 0:
                    continue
                fuzzy = difflib.SequenceMatcher(None, q_norm[:140], s_norm[:140]).ratio()
                score = hits + 0.4 * fuzzy
                if score > best_score:
                    best_score = score
                    best = text[:650]
            if best:
                ans = best.strip()
                _record_stats(intent, time()-start_t, False)
                _push_history(pregunta, ans)
                _ANSWER_CACHE[q_norm_for_cache] = ans
                return ans
    # Detección de consulta desconocida (tokens sin presencia en catálogo) → mensaje estándar
    def _looks_unknown(q: str) -> bool:
        tks = _tokens(q)
        if not tks:
            return False
        cat_text = " ".join([it.get("text","") + " " + it.get("section","") for it in _sections()])
        norm_cat = _norm(cat_text)
        absent = [t for t in tks if t not in norm_cat]
        return len(absent) >= max(2, int(len(tks)*0.7))
    if _looks_unknown(pregunta):
        ans = ("No tengo evidencia suficiente en el sitio oficial para responder con precisión. "
               "Prueba con el nombre de una sección o un término institucional reconocido.")
        _record_stats(intent, time()-start_t, True)
        _push_history(pregunta, ans)
        _ANSWER_CACHE[q_norm_for_cache] = ans
        return ans
    # Ofrecemos secciones relacionadas si existen; si no, mensaje neutral
    cands = _resolve_section_candidates(pregunta, k=2)
    if cands:
        lines = [
            ("No tengo evidencia suficiente en el sitio oficial para responder con precisión. "
             "Puedes consultar estas secciones relacionadas:"),
        ]
        for url, txt, _, ruta in cands:
            label = txt or ruta or "Sección relacionada"
            lines.append(f"- {label} → {url}")
        ans = "\n".join(lines)
        _record_stats(intent, time()-start_t, True)
        _push_history(pregunta, ans)
        return ans

    ans = ("No tengo evidencia suficiente en el sitio oficial para responder con precisión. "
           "Prueba con el nombre de la sección o un término más específico (ej.: “misión y visión”, “transparencia”, “PAA”, “PETI”, “PQRSD”).")
    _record_stats(intent, time()-start_t, True)
    _push_history(pregunta, ans)
    _ANSWER_CACHE[q_norm_for_cache] = ans
    return ans


if __name__ == "__main__":
    # Modo consola para pruebas locales
    print("Chatbot UESVALLE (escribe salir/exit/quit para terminar)")
    while True:
        q = input("> ").strip()
        if q.lower() in {"salir", "exit", "quit"}:
            break
        print(responder_pregunta(q), "\n")



