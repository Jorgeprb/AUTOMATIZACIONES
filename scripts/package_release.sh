#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/Recepcionista_App_release.zip}"
mkdir -p "$(dirname "$OUT")"
python - "$ROOT" "$OUT" <<'PY'
from pathlib import Path
import sys, zipfile
root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
excluded_dirs = {'.git', 'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist', 'build', 'backups'}

def include(path: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in excluded_dirs for part in rel.parts):
        return False
    if path.suffix in {'.pyc', '.pyo'} or '.bak' in path.name or path.name.endswith(('~', '.orig')):
        return False
    if path.name.startswith('.env') and not path.name.endswith(('.example', '.example.local')):
        return False
    return True

with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and include(path) and path.resolve() != out:
            archive.write(path, Path(root.name) / path.relative_to(root))
print(f'Release creado: {out}')
PY
