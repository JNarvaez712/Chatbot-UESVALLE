# chatbot/crawler.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

# URL inicial del sitio de UESVALLE
BASE_URL = "https://www.uesvalle.gov.co"

# Cabeceras para simular un navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UESVALLEBot/1.0; +https://www.uesvalle.gov.co/)"
}

def es_enlace_interno(link, dominio_base):
    parsed_link = urlparse(link)
    return parsed_link.netloc in ("", dominio_base)

def limpiar_texto(html):
    soup = BeautifulSoup(html, "html.parser")

    # Eliminar scripts y estilos
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Obtener texto limpio
    return soup.get_text(separator="\n", strip=True)

def rastrear_sitio(url_inicial=BASE_URL, max_paginas=30):
    visitadas = set()
    por_visitar = [url_inicial]
    resultados = []
    dominio_base = urlparse(url_inicial).netloc

    print("🌐 Iniciando rastreo desde:", url_inicial)

    while por_visitar and len(visitadas) < max_paginas:
        url = por_visitar.pop(0)

        if url in visitadas:
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            html = resp.text
            texto = limpiar_texto(html)
            resultados.append({
                "url": url,
                "text": texto
            })
            print(f"✅ {url} (OK)")

            # Buscar más enlaces en la página
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"].split("#")[0])  # Eliminar anchors
                if es_enlace_interno(link, dominio_base) and link not in visitadas:
                    por_visitar.append(link)

        except Exception as e:
            print(f"⚠️ Error al acceder a {url}: {e}")

        visitadas.add(url)
        time.sleep(0.5)  # Respetar el servidor

    print(f"🧭 Rastreo completo. Se extrajo contenido de {len(resultados)} páginas.")
    return resultados
