# chatbot/crawler.py
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from chatbot.config import (
    BASE_URL,
    USER_AGENT,
    MAX_PAGINAS_RASTREO,
    HTTP_TIMEOUT,
)

HEADERS = {"User-Agent": USER_AGENT}


def _es_enlace_interno(link: str, dominio_base: str) -> bool:
    parsed_link = urlparse(link)
    return parsed_link.netloc in ("", dominio_base)


def _limpiar_texto_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def rastrear_sitio(url_inicial: str = BASE_URL, max_paginas: int = MAX_PAGINAS_RASTREO):
    visitadas = set()
    por_visitar = [url_inicial]
    resultados = []
    dominio_base = urlparse(url_inicial).netloc

    print("🌐 Iniciando rastreo:", url_inicial)

    while por_visitar and len(visitadas) < max_paginas:
        url = por_visitar.pop(0)
        if url in visitadas:
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
            texto = _limpiar_texto_html(html)
            resultados.append({"url": url, "text": texto})
            print(f"✅ {url}")

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"].split("#")[0])
                if _es_enlace_interno(link, dominio_base) and link not in visitadas:
                    por_visitar.append(link)

        except Exception as e:
            print(f"⚠️ Error en {url}: {e}")

        visitadas.add(url)
        time.sleep(0.5)  # respeta el servidor

    print(f"🧭 Rastreo completo. Páginas extraídas: {len(resultados)}")
    return resultados
