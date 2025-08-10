# chatbot/url_utils.py
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    """
    Normaliza URLs para reducir duplicados: esquema/host, sin fragmentos,
    path sin slash final (excepto raíz).
    """
    try:
        p = urlparse(url)
        scheme = p.scheme or "https"
        netloc = p.netloc.lower()
        path = p.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return url
