#!/usr/bin/env python3
"""Cópia de segurança do CÉREBRO da FRIDAY (o cofre: memórias, tópicos, lembranças, sinapses, rede de significado, GRU da rotina).

    python scripts/backup_cerebro.py                       cria ~/storage/downloads/FRIDAY-cerebro-AAAAMMDD-HHMM.zip
    python scripts/backup_cerebro.py --saida PASTA         cria o zip em outra pasta
    python scripts/backup_cerebro.py --com-privado         inclui a pasta Privado/ (cuidado: a pasta Downloads é vista por outros apps)
    python scripts/backup_cerebro.py --restaurar ARQ.zip   volta um backup (pare a FRIDAY antes: bash termux/parar.sh)

Nunca entra: o .env (chaves), a auditoria, o token do painel — eles nem ficam no cofre. A pasta Privado/ fica de fora por padrão.
Restaurar não apaga nada: o cérebro atual é renomeado para «FRIDAY-antes-DATA», ao lado, e o backup entra no lugar.
"""
import argparse, os, sys, time, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
import memoria as M
from backup import criar, restaurar  # noqa: E402  (a lógica mora em friday/backup.py)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida")
    ap.add_argument("--com-privado", action="store_true")
    ap.add_argument("--restaurar")
    a = ap.parse_args()
    if a.restaurar:
        antigo, n = restaurar(a.restaurar)
        print(f"✅ Restaurado: {n} arquivos.")
        if antigo:
            print(f"O cérebro que estava aqui foi guardado (não apagado) em: {antigo}")
        print("Ligue a FRIDAY de novo:  nohup bash termux/supervisor.sh >/dev/null 2>&1 &")
        return 0
    nome, n = criar(a.saida, a.com_privado)
    mb = nome.stat().st_size / 1e6
    print(f"✅ Backup do cérebro: {nome}  ({n} arquivos, {mb:.1f} MB)")
    print("Guarde uma cópia FORA do celular (Google Drive, PC). Sem chaves: o .env não entra." + ("" if a.com_privado else " A pasta Privado/ ficou de fora."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
