# chatbot/crawler.py
import time
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib import robotparser

from chatbot.config import (
    BASE_URL, USER_AGENT, HTTP_TIMEOUT, MAX_PAGINAS_RASTREO,
    CRAWL_MAX_DEPTH, ALLOWED_DOMAINS, RESPECT_ROBOTS,
)
from chatbot.url_utils import normalize_url

HEADERS = {"User-Agent": USER_AGENT}


def _allowed(url: str, rp: robotparser.RobotFileParser | None) -> bool:
    if not RESPECT_ROBOTS or rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def _is_internal(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host.endswith(d) for d in ALLOWED_DOMAINS) or host == ""


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _discover_from_sitemap(base_url: str) -> list[str]:
    """
    Intenta leer /sitemap.xml y extraer URLs iniciales.
    """
    candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
    ]
    found = []
    for s in candidates:
        try:
            r = requests.get(s, headers=HEADERS, timeout=HTTP_TIMEOUT)
            if r.status_code != 200 or "xml" not in r.headers.get("Content-Type", "").lower():
                continue
            root = ET.fromstring(r.text)
            # namespaces comunes
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//sm:loc", ns):
                found.append(loc.text.strip())
        except Exception:
            pass
    return list({normalize_url(u) for u in found if u})


def rastrear_sitio(url_inicial: str = BASE_URL, max_paginas: int = MAX_PAGINAS_RASTREO):
    """
    Rastreo BFS con límites de profundidad y respeto de robots+sitemap.
    Devuelve lista de dicts: {"url": URL, "text": CONTENIDO}
    """
    dominio_base = urlparse(url_inicial).netloc.lower()

    # robots.txt
    rp = None
    if RESPECT_ROBOTS:
        try:
            robots_url = urljoin(url_inicial, "/robots.txt")
            rp = robotparser.RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            rp = None

    # cola inicial: homepage + sitemap (si existe)
    queue = deque()
    start_urls = {normalize_url(url_inicial)}
    start_urls.update(_discover_from_sitemap(url_inicial))
    for u in start_urls:
        queue.append((u, 0))

    visited = set()
    results = []
    print(f"🌐 Inicio rastreo: {url_inicial} | seeds: {len(start_urls)}")

    while queue and len(results) < max_paginas:
        url, depth = queue.popleft()
        url = normalize_url(url)
        if url in visited:
            continue
        visited.add(url)

        if not _is_internal(url):
            continue
        if not _allowed(url, rp):
            continue
        if depth > CRAWL_MAX_DEPTH:
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            ctype = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in ctype:
                # omitimos aquí los binarios; los maneja document_loader.py
                continue
            html = resp.text
            text = _clean_text(html)
            results.append({"url": url, "text": text})
            print(f"✅ [{len(results)}] {url} (d={depth})")

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                link = normalize_url(link)
                if link not in visited and _is_internal(link):
                    queue.append((link, depth + 1))

        except Exception as e:
            print(f"⚠️ Error: {url} -> {e}")

        time.sleep(0.3)  # buen ciudadano

    print(f"🧭 Fin rastreo. Páginas HTML extraídas: {len(results)}")
    return results

