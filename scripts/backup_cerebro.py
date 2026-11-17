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

FORA_SEMPRE = {".env", "auditoria.jsonl", ".friday-token", "token.txt"}


def _destino_padrao():
    d = Path(os.path.expanduser("~/storage/downloads"))
    return d if d.is_dir() else ROOT


def criar(saida=None, com_privado=False, agora=None):
    """Cria o zip e devolve (caminho, quantos arquivos). Confere o zip depois de escrever."""
    base = M.base()
    if base is None or not base.is_dir():
        raise SystemExit("Não achei o cofre da FRIDAY (memória desligada ou ainda vazia).")
    saida = Path(saida) if saida else _destino_padrao()
    saida.mkdir(parents=True, exist_ok=True)
    nome = saida / time.strftime("FRIDAY-cerebro-%Y%m%d-%H%M%S.zip", time.localtime(agora))
    n = 0
    tmp = nome.with_suffix(".zip.parcial")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.is_symlink():
                continue
            rel = f.relative_to(base)
            if f.name in FORA_SEMPRE or f.name.endswith((".tmp", ".parcial")):
                continue
            if not com_privado and rel.parts and rel.parts[0] == "Privado":
                continue
            z.write(f, "FRIDAY/" + rel.as_posix())
            n += 1
    with zipfile.ZipFile(tmp) as z:
        ruim = z.testzip()
    if ruim:
        raise SystemExit(f"O zip saiu com defeito em {ruim}; tente de novo.")
    os.replace(tmp, nome)
    return nome, n


def _seguro(nome):
    p = PurePosixPath(nome)
    return bool(p.parts) and p.parts[0] == "FRIDAY" and not p.is_absolute() and ".." not in p.parts and "\\" not in nome


def restaurar(arq, agora=None):
    """Renomeia o cérebro atual para FRIDAY-antes-DATA (nada é apagado) e extrai o backup no lugar. Devolve (antigo, quantos)."""
    base = M.base()
    if base is None:
        raise SystemExit("A memória está desligada (OBSIDIAN_VAULT=off).")
    with zipfile.ZipFile(arq) as z:
        nomes = [i for i in z.infolist() if not i.is_dir()]
        if not nomes or not all(_seguro(i.filename) for i in nomes):
            raise SystemExit("Esse zip não é um backup do cérebro da FRIDAY (ou tem caminhos suspeitos). Nada foi mudado.")
        antigo = None
        if base.exists():
            antigo = base.with_name(time.strftime("FRIDAY-antes-%Y%m%d-%H%M%S", time.localtime(agora)))
            base.rename(antigo)
        base.parent.mkdir(parents=True, exist_ok=True)
        for i in nomes:
            destino = base.parent / i.filename
            destino.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(destino, "wb") as dst:
                dst.write(src.read())
    M._cache.clear() if hasattr(M, "_cache") else None
    return antigo, len(nomes)


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
