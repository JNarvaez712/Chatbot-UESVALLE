# chatbot/site_map.py
# Construye catálogos del sitio de dos formas:
# A) Desde un archivo data/routes.txt con TODAS las rutas (preferente)
# B) Con crawler BFS+sitemap (fallback si no hay routes.txt)
# -----------------------------------------------------------------------------
# Mejoras:
# - Ahora cada sección incluye `section` (ruta de navegación tipo breadcrumb).
# - Reconoce y normaliza términos clave como PAA, PETI, PQRSD, SGI, etc.
# - Catálogos: url_manifest.json, doc_catalog.json, sections_catalog.json.
# -----------------------------------------------------------------------------

import json, time, xml.etree.ElementTree as ET, os
from collections import deque
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from requests.exceptions import TooManyRedirects, ReadTimeout, ConnectTimeout
from bs4 import BeautifulSoup

from chatbot.config import (
    BASE_URL, USER_AGENT, HTTP_TIMEOUT, CRAWL_MAX_DEPTH,
    RESPECT_ROBOTS, URL_MANIFEST_PATH, DOC_CATALOG_PATH,
    SECTIONS_CATALOG_PATH, MAX_PAGINAS_RASTREO, DOC_EXTS,
    ROUTES_FILE_PATH, USE_EXTERNAL_ROUTES, ROUTES_FILE_REPO_FALLBACK,
    AUGMENT_CRAWL,
)
from chatbot.url_utils import normalize_url, path_to_section

HEADERS = {"User-Agent": USER_AGENT}

# ---------- Utilidad: asegurar carpeta padre antes de escribir ----------
def _ensure_parent(path: str):
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)

# Blocklist de rutas problemáticas (evita indexar duplicados y basura)
BLOCKLIST_SUBSTR = (
    "/mapa-del-sitio",
    "/feedback/",
    "/chat/",
    "/media/plugins/",
    "/mod/Tramites/img/iconos/",
)

# Textos genéricos que no aportan contexto como secciones
_GENERIC_ANCHORS = {
    "inicio","home","aqui","aquí","ver mas","ver más","ver","leer mas","leer más",
    "conocer mas","conocer más","clic aqui","clic aquí","click aqui","click aquí",
    "ir","más","mas","detalle","detalles","ver detalle","ver detalles",
    "ver informacion","ver información"
}

def _norm(s: str) -> str:
    import unicodedata, re
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _is_internal(u: str) -> bool:
    host = urlparse(u).netloc.lower()
    return host == "" or host.endswith("uesvalle.gov.co")

def _looks_doc(link: str) -> bool:
    l = link.lower()
    return any(l.endswith(ext) for ext in DOC_EXTS)

def _page_title_and_h1(soup: BeautifulSoup) -> tuple[str, str]:
    """Extrae <title> y primer <h1> de la página."""
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    h1 = ""
    h1_tag = soup.find("h1")
    if h1_tag:
        h1 = " ".join(h1_tag.get_text(" ", strip=True).split())
    return title, h1

# ----------------------------- A) DESDE routes.txt ----------------------------

def _load_routes_file() -> list[str]:
    """
    Busca routes.txt primero en ROUTES_FILE_PATH (runtime DATA_DIR),
    y si no existe, en el repo (ROUTES_FILE_REPO_FALLBACK).
    """
    if not USE_EXTERNAL_ROUTES:
        return []
    candidates = [ROUTES_FILE_PATH, ROUTES_FILE_REPO_FALLBACK]
    path = next((p for p in candidates if p and os.path.exists(p)), None)
    if not path:
        return []
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if not u:
                continue
            nu = normalize_url(u)
            if _is_internal(nu):
                urls.append(nu)
    # quitar duplicados conservando orden
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq

def build_from_routes_file():
    """Construye manifiesto + catálogo de secciones (1 entrada por URL)
       + catálogo de documentos, recorriendo SOLO las URLs del routes.txt.
    """
    routes = _load_routes_file()
    if not routes:
        return None  # para que el caller use el crawler tradicional

    print(f"📄 routes.txt detectado: {len(routes)} URLs")

    urls = []
    sections, docs = [], []

    err_404, err_other = 0, 0

    for i, url in enumerate(routes, start=1):
        if any(b in url for b in BLOCKLIST_SUBSTR):
            print(f"⏭️  Skip por blocklist: {url}")
            continue
        try:
            r = requests.get(
                url, headers=HEADERS, timeout=(5, 15), allow_redirects=True
            )
            ctype = r.headers.get("Content-Type", "").lower()
            if r.status_code >= 400:
                err_404 += 1
                continue
            urls.append(url)

            if "text/html" in ctype:
                soup = BeautifulSoup(r.text, "html.parser")
                page_title, h1 = _page_title_and_h1(soup)

                # sección propia con ruta tipo breadcrumb
                label = page_title or h1 or path_to_section(urlparse(url).path)
                sections.append({
                    "url": url,
                    "text": label,
                    "from_page": url,
                    "page_title": page_title or h1,
                    "h1": h1,
                    "section": path_to_section(urlparse(url).path),
                })

                # documentos enlazados
                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"].split("#")[0])
                    if not _is_internal(href) or not _looks_doc(href):
                        continue
                    link_text = " ".join(a.get_text(strip=True).split())
                    parent = a.find_parent(["p", "li", "div", "section", "article"])
                    ctx = " ".join(parent.get_text(" ", strip=True).split()) if parent else link_text
                    docs.append({
                        "doc_url": normalize_url(href),
                        "from_page": url,
                        "page_title": page_title or h1,
                        "h1": h1,
                        "link_text": link_text,
                        "context": ctx[:900],
                        "section": path_to_section(urlparse(url).path),
                    })
        except (TooManyRedirects, ReadTimeout, ConnectTimeout) as e:
            err_other += 1
            print(f"⚠️ Skip {url}: {e}")
            continue
        except Exception as e:
            err_other += 1
            print(f"⚠️ Error leyendo {url}: {e}")

        if i % 25 == 0:
            print(f"… procesadas {i}/{len(routes)} páginas")

        time.sleep(0.05)

    # persistir (asegurar carpetas)
    _ensure_parent(URL_MANIFEST_PATH)
    _ensure_parent(DOC_CATALOG_PATH)
    _ensure_parent(SECTIONS_CATALOG_PATH)

    with open(URL_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"base": BASE_URL, "count": len(urls), "urls": urls}, f, ensure_ascii=False, indent=2)
    with open(DOC_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"count": len(docs), "items": docs}, f, ensure_ascii=False, indent=2)
    with open(SECTIONS_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"count": len(sections), "items": sections}, f, ensure_ascii=False, indent=2)

    print(f"✅ Manifiesto (routes): {len(urls)} | 📚 Docs: {len(docs)} | 🧭 Secciones: {len(sections)}")
    print(f"Resumen: {err_404} con 404, {err_other} con errores/redirecciones.")
    return urls, docs, sections

# -------------------------- B) CRAWLER (fallback) -----------------------------

def _discover_sitemap_seeds(base: str) -> set:
    seeds = set()
    for cand in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            r = requests.get(urljoin(base, cand), headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code == 200 and "xml" in r.headers.get("Content-Type", "").lower():
                root = ET.fromstring(r.text)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//sm:loc", ns):
                    if loc.text:
                        seeds.add(normalize_url(loc.text.strip()))
        except Exception:
            pass
    return seeds

def _bootstrap_from_home() -> set:
    seeds = set()
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400:
            print(f"⚠️ HOME status {resp.status_code}")
            return seeds
        if "text/html" not in resp.headers.get("Content-Type", "").lower():
            return seeds
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            url = normalize_url(urljoin(BASE_URL, a["href"].split("#")[0]))
            if _is_internal(url):
                seeds.add(url)
        print(f"🔹 Bootstrap HOME: {len(seeds)} enlaces iniciales.")
    except Exception as e:
        print(f"⚠️ Error bootstrap HOME: {e}")
    return seeds

def _push_if_section(sections: list, from_url: str, a_tag, page_title: str, h1: str):
    """Agrega enlace como sección si es válido y no es genérico."""
    href = a_tag.get("href", "").strip()
    if not href:
        return
    target = normalize_url(urljoin(from_url, href.split("#")[0]))
    if not _is_internal(target) or _looks_doc(target):
        return
    text = " ".join(a_tag.get_text(" ", strip=True).split())
    if not text:
        return
    ntext = _norm(text)
    if ntext in _GENERIC_ANCHORS:
        return
    if target.rstrip("/") == normalize_url(BASE_URL).rstrip("/"):
        return
    section = path_to_section(urlparse(target).path)
    sections.append({
        "url": target,
        "text": text,
        "from_page": from_url,
        "page_title": page_title or h1,
        "h1": h1,
        "section": section
    })

def build_map_and_catalog():
    # 1) Intentar con routes.txt
    built = build_from_routes_file()
    if built and not AUGMENT_CRAWL:
        return built
    # Si AUGMENT_CRAWL está activo y hubo catálogo inicial, partimos de él y
    # luego descubrimos nuevas páginas con el crawler tradicional.
    seed_urls, seed_docs, seed_sections = (built or ([], [], []))

    # Si no, usa el crawler tradicional
    rp = None
    if RESPECT_ROBOTS:
        try:
            rp = robotparser.RobotFileParser()
            rp.set_url(urljoin(BASE_URL, "/robots.txt"))
            rp.read()
        except Exception:
            rp = None

    seeds = set(seed_urls)  # incluir las seeds del manifiesto inicial (routes.txt)
    seeds |= _discover_sitemap_seeds(BASE_URL)
    seeds |= _bootstrap_from_home()
    seeds.add(normalize_url(BASE_URL))
    if not seeds:
        seeds = {normalize_url(BASE_URL)}

    q = deque((s, 0) for s in seeds if _is_internal(s))
    visited, urls = set(), []
    catalog_docs, catalog_sections = [], []

    print(f"🌐 Mapeando sitio… seeds={len(seeds)} depth≤{CRAWL_MAX_DEPTH} max={MAX_PAGINAS_RASTREO}")

    while q and len(urls) < MAX_PAGINAS_RASTREO:
        url, depth = q.popleft()
        url = normalize_url(url)
        if url in visited or not _is_internal(url) or (rp and not rp.can_fetch(HEADERS["User-Agent"], url)) or depth > CRAWL_MAX_DEPTH:
            continue
        visited.add(url)

        try:
            r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT, allow_redirects=True)
            ctype = r.headers.get("Content-Type", "").lower()
            if r.status_code >= 400:
                print(f"⚠️ {r.status_code} en {url}")
                continue

            urls.append(url)

            if "text/html" in ctype:
                soup = BeautifulSoup(r.text, "html.parser")
                page_title, h1 = _page_title_and_h1(soup)

                for a in soup.find_all("a", href=True):
                    _push_if_section(catalog_sections, url, a, page_title, h1)

                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"].split("#")[0])
                    if not _is_internal(href) or not _looks_doc(href):
                        continue
                    link_text = " ".join(a.get_text(strip=True).split())
                    parent = a.find_parent(["p", "li", "div", "section", "article"])
                    ctx = " ".join(parent.get_text(" ", strip=True).split()) if parent else link_text
                    catalog_docs.append({
                        "doc_url": normalize_url(href),
                        "from_page": url,
                        "page_title": page_title or h1,
                        "h1": h1,
                        "link_text": link_text,
                        "context": ctx[:900],
                        "section": path_to_section(urlparse(url).path),
                    })

                for a in soup.find_all("a", href=True):
                    nxt = normalize_url(urljoin(url, a["href"].split("#")[0]))
                    if _is_internal(nxt) and not _looks_doc(nxt) and nxt not in visited:
                        q.append((nxt, depth + 1))

        except Exception as e:
            print(f"⚠️ Error obteniendo {url}: {e}")

        time.sleep(0.12)

    if not urls:
        urls = [normalize_url(BASE_URL)]
        print("ℹ️ Fallback: manifiesto vacío, se agrega la home.")

    # persistir (asegurar carpetas)
    _ensure_parent(URL_MANIFEST_PATH)
    _ensure_parent(DOC_CATALOG_PATH)
    _ensure_parent(SECTIONS_CATALOG_PATH)

    with open(URL_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"base": BASE_URL, "count": len(urls), "urls": urls}, f, ensure_ascii=False, indent=2)
    with open(DOC_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"count": len(catalog_docs), "items": catalog_docs}, f, ensure_ascii=False, indent=2)

    # deduplicar secciones por URL (texto más largo)
    best_by_url = {}
    for it in catalog_sections:
        u = it["url"]
        if u not in best_by_url or len(it["text"]) > len(best_by_url[u]["text"]):
            best_by_url[u] = it
    sections_unique = list(best_by_url.values())

    with open(SECTIONS_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"count": len(sections_unique), "items": sections_unique}, f, ensure_ascii=False, indent=2)

    print(f"📜 Manifiesto: {len(urls)} URLs | 📚 Docs: {len(catalog_docs)} | 🧭 Secciones: {len(sections_unique)}")
    return urls, catalog_docs, sections_unique

