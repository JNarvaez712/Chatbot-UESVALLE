# chatbot/site_map.py
import json
import time
import xml.etree.ElementTree as ET
from collections import deque
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from chatbot.config import (
    BASE_URL, USER_AGENT, HTTP_TIMEOUT, CRAWL_MAX_DEPTH, ALLOWED_DOMAINS,
    RESPECT_ROBOTS, URL_MANIFEST_PATH, MAX_PAGINAS_RASTREO
)
from chatbot.url_utils import normalize_url

HEADERS = {"User-Agent": USER_AGENT}

def _is_internal(u: str) -> bool:
    host = urlparse(u).netloc.lower()
    return host == "" or any(host.endswith(d) for d in ALLOWED_DOMAINS)

def _discover_sitemap_seeds(base: str) -> set[str]:
    seeds = set()
    for cand in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            r = requests.get(urljoin(base, cand), headers=HEADERS, timeout=HTTP_TIMEOUT)
            if r.status_code == 200 and "xml" in r.headers.get("Content-Type", "").lower():
                root = ET.fromstring(r.text)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//sm:loc", ns):
                    if loc.text:
                        seeds.add(normalize_url(loc.text.strip()))
        except Exception:
            pass
    return seeds

def _allowed(url: str, rp: robotparser.RobotFileParser | None) -> bool:
    if not RESPECT_ROBOTS or rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True

def build_url_manifest() -> list[str]:
    # robots
    rp = None
    if RESPECT_ROBOTS:
        try:
            rp = robotparser.RobotFileParser()
            rp.set_url(urljoin(BASE_URL, "/robots.txt"))
            rp.read()
        except Exception:
            rp = None

    seeds = {normalize_url(BASE_URL)} | _discover_sitemap_seeds(BASE_URL)
    q = deque((s, 0) for s in seeds if _is_internal(s))
    visited, urls = set(), []

    print(f"🌐 Construyendo manifiesto de URLs… seeds={len(seeds)}")

    while q and len(urls) < MAX_PAGINAS_RASTREO:
        url, depth = q.popleft()
        url = normalize_url(url)

        if url in visited or not _is_internal(url) or not _allowed(url, rp) or depth > CRAWL_MAX_DEPTH:
            continue
        visited.add(url)

        try:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
            ctype = r.headers.get("Content-Type", "").lower()
            urls.append(url)  # registra toda ruta válida, sea HTML o recurso

            if "text/html" in ctype:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    nxt = normalize_url(urljoin(url, a["href"]))
                    if nxt not in visited and _is_internal(nxt):
                        q.append((nxt, depth + 1))
        except Exception:
            pass

        time.sleep(0.2)  # cortesía al servidor

    urls = sorted(set(urls))
    # persistir
    manifest = {"base": BASE_URL, "count": len(urls), "urls": urls}
    with open(URL_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"📜 Manifiesto guardado en {URL_MANIFEST_PATH} con {len(urls)} URLs totales")
    return urls
