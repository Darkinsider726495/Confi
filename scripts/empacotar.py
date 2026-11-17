#!/usr/bin/env python3
"""Cria um ZIP de distribuição da FRIDAY sem segredos nem estado pessoal."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXACT_EXCLUDED = {
    ".env", ".env.local", ".env.production", ".env.development",
    ".token", ".friday-token", "token.txt", "friday.db",
    "auditoria.jsonl", "diario.jsonl", ".ultimo-backup-ok",
}
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", ".evolucao",
    ".stage-backup", "cofre", "Memorias", "memorias", "memory",
    "memories", "backups", "backup", "build", "dist","logs", "evidencias",
}
EXCLUDED_SUFFIXES = (".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3", ".pyc", ".token", ".pem", ".key", ".p12", ".pfx")


def excluded(rel: Path) -> bool:
    parts = rel.parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    name = rel.name
    if name in EXACT_EXCLUDED:
        return True
    if name.startswith(".env") and name != ".env.example":
        return True
    if name.endswith(EXCLUDED_SUFFIXES):
        return True
    if name.endswith((".bak", ".backup", ".old")):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", nargs="?", type=Path,
                        default=ROOT.parent / "friday-pi-distribuicao.zip")
    args = parser.parse_args()
    dest = args.destino.expanduser().resolve()
    if dest == ROOT or ROOT in dest.parents:
        parser.error("o ZIP de saída deve ficar fora da pasta do projeto")

    env = ROOT / ".env"
    if env.exists():
        os.chmod(env, stat.S_IRUSR | stat.S_IWUSR)

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".friday-package-", suffix=".zip", dir=dest.parent)
    os.close(fd)
    temp = Path(temp_name)
    included = 0
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(ROOT.rglob("*")):
                rel = path.relative_to(ROOT)
                if excluded(rel) or path.is_symlink() or not path.is_file():
                    continue
                archive.write(path, (Path(ROOT.name) / rel).as_posix())
                included += 1
        os.replace(temp, dest)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    print(f"Pacote criado: {dest}")
    print(f"Arquivos incluídos: {included}")
    print("Segredos, bancos, diário evolutivo e memórias pessoais foram excluídos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
