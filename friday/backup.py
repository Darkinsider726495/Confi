"""Cópia de segurança do cérebro (o cofre) em zip: sem segredos, sem Privado/ por padrão; restaurar não apaga nada.
Também faz a cópia SEMANAL sozinha (gancho do laço proativo) e responde «faça um backup» / «quando foi o último backup?».
"""
import json, os, re, time, zipfile
from pathlib import Path, PurePosixPath
import memoria as M

BASE_PROJ = Path(__file__).resolve().parent.parent
FORA_SEMPRE = {".env", "auditoria.jsonl", ".friday-token", "token.txt"}


def _destino_padrao():
    """No celular: a pasta Downloads (fácil de mandar para o Drive). Fora dele: «Backups FRIDAY», ao lado do cofre (nunca dentro do código)."""
    d = Path(os.path.expanduser("~/storage/downloads"))
    if d.is_dir():
        return d
    r = M.raiz()
    return (r / "Backups FRIDAY") if r else Path(os.path.expanduser("~")) / "FRIDAY-backups"


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




# ---------------------------------------------------------------- automático, uma vez por semana
def _arq_estado():
    return M.base() / ".cerebro" / "backup.json" if M.ativo() else None


def ultimo():
    """(quando, caminho) do último backup que ela fez, ou (0, "")."""
    a = _arq_estado()
    try:
        d = json.loads(a.read_text(encoding="utf-8"))
        return float(d.get("t", 0)), str(d.get("arq", ""))
    except (OSError, ValueError, AttributeError):
        return 0.0, ""


def fazer(agora=None):
    """Faz o backup agora e anota quando. Devolve a frase para ela dizer."""
    agora = time.time() if agora is None else agora
    nome, n = criar(agora=agora)
    a = _arq_estado()
    a.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.with_suffix(".tmp")
    tmp.write_text(json.dumps({"t": agora, "arq": str(nome), "n": n}), encoding="utf-8")
    os.replace(tmp, a)
    return f"Fiz a cópia de segurança do meu cérebro: {n} arquivos, em {nome.parent}. Guarde uma cópia fora do celular."


def dias():
    try:
        return max(0.0, float(os.getenv("BACKUP_DIAS", "7")))
    except ValueError:
        return 7.0


def gancho(agora=None):
    """Para o laço proativo: se faz mais de BACKUP_DIAS dias (padrão 7; 0 = desligado), faz a cópia e avisa."""
    agora = time.time() if agora is None else agora
    if not M.ativo() or not dias() or not M.base().is_dir():
        return []
    t, _ = ultimo()
    if agora - t < dias() * 86400:
        return []
    try:
        return [fazer(agora)]
    except (OSError, SystemExit, zipfile.BadZipFile):
        return []


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_FAZER = re.compile(_P + r"(?:faca|faz|fazer|cria|crie)(?: um| uma)? (?:backup|copia de seguranca)(?: do (?:seu )?cerebro)?(?: agora)?[ .!?]*$")
_QUANDO = re.compile(_P + r"(?:quando (?:foi|fez) (?:o |a )?(?:ultimo |ultima )?(?:backup|copia de seguranca)|(?:tem|fez) backup)[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _FAZER.match(f):
        if not M.ativo():
            return "A memória está desligada: não há cérebro para copiar."
        try:
            return fazer()
        except (OSError, SystemExit) as e:
            return f"Não consegui fazer a cópia: {e}"
    if _QUANDO.match(f):
        t, arq = ultimo()
        if not t:
            return f"Ainda não fiz nenhuma cópia. Faço sozinha a cada {dias():g} dias, ou agora se você pedir «faça um backup»."
        d = (time.time() - t) / 86400
        return f"A última cópia foi há {d:.0f} dias ({Path(arq).name}). A próxima sai sozinha em {max(0, dias() - d):.0f} dias."
    return None
