# chatbot/url_utils.py
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    """Normaliza esquema y dominio, pero respeta la '/' final (no la recorta)."""
    try:
        p = urlparse(url)
        scheme = p.scheme or "https"
        netloc = p.netloc.lower()
        path = p.path or "/"
        # ❌ NO recortamos la barra final: algunos CMS la requieren
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return url

def path_to_section(path: str) -> str:
    """Convierte '/publicaciones/1558/transparencia-informacion-publica'
       a 'Publicaciones › Transparencia Informacion Publica'."""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return "Inicio"
    # Solo palabras (omitimos IDs numéricos)
    parts = [p.replace("-", " ").replace("_", " ") for p in parts if not p.isdigit()]
    return " › ".join(s.title() for s in parts) if parts else "Inicio"

