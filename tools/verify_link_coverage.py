import os
import sys
from pathlib import Path
from collections import defaultdict

# Ensure project root on sys.path so we can import 'chatbot'
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from chatbot.bot import KEYWORD_LINK_MAP, DYNAMIC_LINK_MAP

ROUTES_FILE = ROOT_DIR / 'data' / 'routes.txt'

def load_routes(path: Path):
    routes = []
    if not path.is_file():
        return routes
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            routes.append(line)
    return routes

def invert_maps(manual: dict, dynamic: dict):
    url_to_keywords = defaultdict(set)
    for k, v in manual.items():
        url_to_keywords[v].add(k)
    for k, v in dynamic.items():
        url_to_keywords[v].add(k)
    return url_to_keywords

def main():
    routes = load_routes(ROUTES_FILE)
    url_to_keywords = invert_maps(KEYWORD_LINK_MAP, DYNAMIC_LINK_MAP)
    total = len(routes)
    covered = 0
    missing = []
    examples = []
    for r in routes:
        kws = url_to_keywords.get(r, set())
        if kws:
            covered += 1
            if len(examples) < 5:
                examples.append((r, sorted(kws)[:8]))
        else:
            missing.append(r)

    print(f"Total rutas: {total}")
    print(f"Rutas cubiertas: {covered}")
    print(f"Rutas sin keywords: {len(missing)}")
    if missing:
        print("--- FALTANTES (max 20) ---")
        for m in missing[:20]:
            print(m)
    print("--- Ejemplos de cobertura (hasta 5) ---")
    for url, kwlist in examples:
        print(url)
        print("  ->", ", ".join(kwlist))
    # Detect URLs mapped but not in routes.txt (maybe google sites)
    extra_urls = [u for u in url_to_keywords.keys() if u not in routes]
    print(f"URLs extra (fuera de routes.txt): {len(extra_urls)}")
    if extra_urls:
        for e in extra_urls[:10]:
            print("EXTRA:", e)

if __name__ == '__main__':
    main()
