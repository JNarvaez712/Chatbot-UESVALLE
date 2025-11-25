#!/usr/bin/env python
"""Verifica que el repositorio esté limpio antes de hacer push a Hugging Face o producción.

Comprobaciones:
    1. Que no existan archivos de bytecode de Python rastreados (*.pyc, *.pyo) ni directorios __pycache__.
    2. Que no haya archivos que superen el umbral de tamaño (por defecto 7MB) salvo que estén en la lista de permitidos.
    3. Que existan los patrones de ignore requeridos (sanidad de .gitignore).

Códigos de salida:
    0: OK
    1: Se encontraron archivos prohibidos rastreados
    2: Se detectaron archivos sobredimensionados
    3: Faltan patrones de ignore requeridos
    4: Otro error inesperado

Uso:
    python tools/verify_clean_push.py [--max-size 7000000] [--allow ruta1 ruta2]

Integración en pre-commit o CI:
    pre-commit:  `python tools/verify_clean_push.py || exit 1`
    Paso en GitHub Action antes del push.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = ["*.pyc", "*.pyo"]  # Patrones de bytecode prohibidos
REQUIRED_IGNORE_LINES = ["__pycache__/", "*.pyc"]  # Líneas que deben existir en .gitignore
DEFAULT_MAX_SIZE = 7_000_000  # ~7MB (tamaño máximo por defecto)

def git_ls_files(pattern: str | None = None) -> list[str]:
    """Ejecuta `git ls-files` opcionalmente filtrado por patrón y devuelve lista de rutas."""
    cmd = ["git", "ls-files"]
    if pattern:
        cmd.append(pattern)
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]

def get_tracked_files() -> list[Path]:
    """Devuelve todas las rutas rastreadas por Git como objetos Path."""
    out = subprocess.check_output(["git", "ls-files"], text=True)
    return [Path(p) for p in out.splitlines() if p.strip()]

def find_forbidden() -> list[Path]:
    """Localiza archivos prohibidos (bytecode o directorios __pycache__) que estén rastreados."""
    forbidden = []
    for patt in FORBIDDEN_PATTERNS:
        forbidden.extend(Path(f) for f in git_ls_files(patt))
    # Directorios __pycache__ explícitos presentes en la ruta
    for f in get_tracked_files():
        if "__pycache__" in f.parts:
            forbidden.append(f)
    # Eliminar duplicados conservando orden
    uniq = []
    seen = set()
    for f in forbidden:
        if f not in seen:
            uniq.append(f)
            seen.add(f)
    return uniq

def find_oversized(max_size: int, allow: set[Path]) -> list[tuple[Path, int]]:
    """Devuelve lista de (ruta, tamaño) para archivos que superan el límite y no están permitidos."""
    results = []
    for f in get_tracked_files():
        if f in allow:
            continue
        if not f.is_file():
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size > max_size:
            results.append((f, size))
    return results

def check_gitignore() -> bool:
    """Verifica que exista .gitignore y que incluya las líneas requeridas."""
    gi = Path('.gitignore')
    if not gi.exists():
        return False
    content = gi.read_text(encoding='utf-8', errors='ignore').splitlines()
    present = {line.strip() for line in content}
    for required in REQUIRED_IGNORE_LINES:
        if required not in present:
            return False
    return True

def main() -> int:
    """Punto de entrada principal: ejecuta las validaciones y devuelve el código de salida."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-size', type=int, default=DEFAULT_MAX_SIZE,
                        help='Maximum allowed file size in bytes (default: 7MB).')
    parser.add_argument('--allow', nargs='*', default=[],
                        help='Paths to allow even if exceeding size.')
    args = parser.parse_args()

    allow = {Path(p).resolve() for p in args.allow}

    forbidden = find_forbidden()
    if forbidden:
        print("[FALLO] Se encontraron archivos de bytecode o directorios __pycache__ rastreados:")
        for f in forbidden:
            print(f" - {f}")
        return 1

    oversized = find_oversized(args.max_size, allow)
    if oversized:
        print(f"[FALLO] Archivos rastreados exceden el tamaño permitido (> {args.max_size} bytes):")
        for f, sz in oversized:
            print(f" - {f} ({sz} bytes)")
        return 2

    if not check_gitignore():
        print("[FALLO] Faltan patrones requeridos en .gitignore")
        return 3

    print("[OK] Repositorio limpio para hacer push.")
    return 0

if __name__ == '__main__':
    try:
        code = main()
    except Exception as e:
        print(f"[ERROR] Inesperado: {e}")
        code = 4
    sys.exit(code)
