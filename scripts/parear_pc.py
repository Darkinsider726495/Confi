#!/usr/bin/env python3
"""Mostra, no Termux, o comando para colar no PC e sincronizar o cofre pelo Wi-Fi. A chave aparece SÓ aqui: não mande para ninguém.

    python scripts/parear_pc.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
import sincronia as S


def main():
    if not S.ligada():
        print("A sincronização está desligada. Diga à FRIDAY: «liga a sincronização com o PC» e rode isto de novo.")
        return 1
    ip = S.ip_local()
    print("Celular e PC precisam estar no MESMO Wi-Fi.\n")
    print("1) Copie para o PC o arquivo scripts/sincronizar_pc.py (está no zip da FRIDAY).")
    print("2) No PC (Windows: PowerShell; Linux/Kali: terminal), rode UMA vez:\n")
    print(f'   python sincronizar_pc.py --friday http://{ip}:{S.PORTA} --chave {S.chave()} --pasta "Cofre FRIDAY"\n')
    print("   Depois, para manter sincronizando sozinho:  python sincronizar_pc.py --pasta \"Cofre FRIDAY\" --sempre")
    print("\nA chave é a senha da sua memória: não mande em chat nem print. Para trocar a chave, apague friday/.sync_chave.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
