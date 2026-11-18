"""Laboratório de Modificação Destrutiva (MAE) — isolamento por diretório.
Nenhuma operação de arquivo pode sair de LAB_ROOT (validação de caminho + symlink resolvido).
Toda modificação é precedida de um snapshot (versão) para permitir rollback (recuperação garantida).
Auditoria: cada operação chama B._audit() — registra o fato, não o conteúdo.
Limitação documentada: sem Docker (Termux alvo), o isolamento é lógico (caminho) e não de kernel."""

import os, re, sys, json, shutil, difflib, threading, time, subprocess, hashlib
from pathlib import Path
import broker as B

# LAB_ROOT — ambiente experimental explicitamente designado.
# Pode ser sobreposto por env (FRIDAY_LAB), mas padrão: <projeto>/.lab/
BASE = os.path.dirname(os.path.abspath(__file__))
LAB_ROOT = os.environ.get("FRIDAY_LAB") or os.path.join(BASE, ".lab")

VERSOES = os.path.join(LAB_ROOT, ".versoes")  # snapshots (versões) anteriores
GRAVE_JARDIM = os.path.join(LAB_ROOT, ".grave")  # lixo para exclusões (recuperável via versão)

EXT_PERMITIDAS = {".py", ".json", ".md", ".txt", ".yaml", ".yml", ".sh"}
MAX_ARQ = 500_000          # 500 KB por arquivo
MAX_LAB = 50_000_000       # 50 MB no laboratório inteiro
# _trava para operações de escrita/snapshot: uma modificação por vez
_trava = threading.RLock()
TESTE_TIMEOUT = 30          # segundos: nenhum teste do laboratório roda mais que isto
TESTE_PADRAO = re.compile(r"^teste_[\w\-. ]{1,50}\.py$")   # só arquivos de teste designados rodam aqui dentro
# Só roda o teste cujo CONTEÚDO é conhecido (hash SHA-256 registrado por código da FRIDAY: as sementes do mae.py).
# Um arquivo com o nome certo e outro conteúdo não roda. Não há ferramenta do corretor que registre um hash.
_TESTES_PERMITIDOS = set()


def permitir_teste(conteudo):
    """Registra o conteúdo de um teste conhecido (chamado por código, nunca pela IA). Devolve o hash."""
    h = hashlib.sha256(str(conteudo).encode("utf-8")).hexdigest()
    _TESTES_PERMITIDOS.add(h)
    return h

def _lab_absoluto():
    """Resolve LAB_ROOT para caminho absoluto real (sem symlinks). Cria se não existe."""
    os.makedirs(LAB_ROOT, exist_ok=True)
    return os.path.realpath(LAB_ROOT)

def _validar_caminho(rel):
    """Valida se o caminho relativo confinado está DENTRO do LAB_ROOT. Recusa qualquer fuga.
    A checagem vem ANTES da normalização: nada é limpo antes de ser julgado (um «../» limpo passa a olhar desatento)."""
    if not rel or not isinstance(rel, str):
        raise ValueError("Caminho de laboratório vazio ou inválido.")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        raise ValueError(f"Caminho absoluto recusado no laboratório: {rel!r}")
    segs = rel.replace("\\", "/").split("/")
    if ".." in segs:
        raise ValueError(f"Fuga de laboratório recusada: {rel!r}")
    if any(s.startswith(".") for s in segs):
        raise ValueError(f"Nome oculto recusado no laboratório: {rel!r} (as áreas internas .versoes/.grave ficam fora do alcance)")
    rel = "/".join(s for s in segs if s)          # só agora limpa "./" e "//" vazios — depois da checagem
    if not rel:
        raise ValueError("Caminho de laboratório vazio ou inválido.")
    if os.path.splitext(rel)[1].lower() not in EXT_PERMITIDAS:
        raise ValueError(f"Tipo de arquivo não permitido no laboratório: {os.path.splitext(rel)[1]!r}. Use: {', '.join(sorted(EXT_PERMITIDAS))}")
    lab = _lab_absoluto()
    alvo = os.path.realpath(os.path.join(lab, rel))
    if not (alvo == lab or alvo.startswith(lab + os.sep)):
        raise ValueError(f"Fuga de laboratório recusada: {rel!r} (resolve para {alvo!r} fora de {lab!r})")
    if alvo in (os.path.realpath(VERSOES), os.path.realpath(GRAVE_JARDIM)):
        raise ValueError("Sem acesso à área interna de versões/lixo do laboratório.")
    return alvo

def _tamanho_lab():
    total = 0
    for raiz, _, arqs in os.walk(LAB_ROOT):
        for a in arqs:
            try: total += os.path.getsize(os.path.join(raiz, a))
            except OSError: pass
    return total

def _snapshot(caminho_abs):
    """Salva a versão atual de um arquivo antes de mexer. Devolve o id da versão (ou None se não existia)."""
    if not os.path.exists(caminho_abs):
        return None
    rel = os.path.relpath(caminho_abs, LAB_ROOT)
    ts = time.strftime("%Y%m%d-%H%M%S")
    vid = hashlib.sha256((rel + ts + str(os.path.getmtime(caminho_abs))).encode()).hexdigest()[:12]
    dir_ = os.path.join(VERSOES, vid)
    os.makedirs(os.path.join(dir_, os.path.dirname(rel) or "."), exist_ok=True)
    destino = os.path.join(dir_, rel)
    # shutil.copy2 é leitura + escrita, não é chamada de apagar — é seguro contra a regra de "nada é apagado"
    if os.path.islink(caminho_abs):
        raise ValueError(f"Arquivo {rel!r} é um link simbólico: não pode ser modificado no laboratório.")
    shutil.copy2(caminho_abs, destino)
    meta = {"id": vid, "arquivo": rel, "ts": ts, "size": os.path.getsize(destino)}
    with open(os.path.join(dir_, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return vid

def _diferenca(antes: str, depois: str, nome: str):
    """Unificado de diferenças para o painel (linhas de alteração)."""
    antes_l = antes.splitlines(keepends=True) if antes else []
    depois_l = depois.splitlines(keepends=True) if depois else []
    return list(difflib.unified_diff(antes_l, depois_l, fromfile=f"{nome} (antes)", tofile=f"{nome} (depois)"))

def _tamanhos_lab_ok(novo_bytes=0):
    if _tamanho_lab() + novo_bytes > MAX_LAB:
        raise ValueError("Laboratório cheio (limite de 50 MB).")

def _relativo(alvo_abs):
    lab = _lab_absoluto()
    if not (alvo_abs == lab or alvo_abs.startswith(lab + os.sep)):
        raise ValueError("Fora do laboratório.")
    return os.path.relpath(alvo_abs, lab)

# ------------------------------------------------------- Operações (todas confinadas)

def criar(rel, conteudo):
    """Cria um arquivo dentro do LAB_ROOT. Não sobrescreve: recusa se existir."""
    alvo = _validar_caminho(rel)
    c = str(conteudo).encode("utf-8")
    if len(c) > MAX_ARQ: raise ValueError(f"Conteúdo grande demais ({len(c)} B, máximo {MAX_ARQ}).")
    if os.path.lexists(alvo): raise ValueError(f"Arquivo {rel!r} já existe no laboratório.")
    with _trava:
        _tamanhos_lab_ok(len(c))
        os.makedirs(os.path.dirname(alvo) or LAB_ROOT, exist_ok=True)
        with open(alvo, "x", encoding="utf-8") as f:
            f.write(str(conteudo))
        B._audit(ferramenta="lab_criar", decisao="executado", resultado=rel)
        return f"Criado no laboratório: {rel} ({len(c)} bytes)."

def ler(rel):
    """Lê um arquivo do laboratório (confinado)."""
    alvo = _validar_caminho(rel)
    if not os.path.exists(alvo): raise ValueError(f"Arquivo {rel!r} não existe no laboratório.")
    with open(alvo, encoding="utf-8") as f:
        txt = f.read(MAX_ARQ + 1)
    if len(txt) > MAX_ARQ: raise ValueError("Arquivo grande demais para leitura inteira.")
    B._audit(ferramenta="lab_ler", decisao="executado", resultado=rel)
    return txt

def listar(auditar=True):
    """Lista arquivos do laboratório (relativo a LAB_ROOT, sem .versoes/.grave). O painel lê sem auditar: ele pergunta a cada segundo,
    e uma leitura dele não é uma ação dela (sem isso a trilha do corretor enchia de «lab_listar»)."""
    lab = _lab_absoluto()
    arqs = []
    for raiz, pastas, nomes in os.walk(lab):
        pastas[:] = [p for p in pastas if p not in (".versoes", ".grave")]
        for n in nomes:
            rel = os.path.relpath(os.path.join(raiz, n), lab)
            if os.path.splitext(rel)[1].lower() in EXT_PERMITIDAS:
                arqs.append(rel)
    if auditar:
        B._audit(ferramenta="lab_listar", decisao="executado")
    return sorted(arqs)

def editar(rel, novo_conteudo):
    """Edita um arquivo do laboratório. Tira snapshot antes. Devolve a diferença entre versões."""
    alvo = _validar_caminho(rel)
    novo = str(novo_conteudo).encode("utf-8")
    if len(novo) > MAX_ARQ: raise ValueError(f"Conteúdo grande demais ({len(novo)} B, máximo {MAX_ARQ}).")
    if not os.path.exists(alvo): raise ValueError(f"Arquivo {rel!r} não existe: use lab_criar.")
    with _trava:
        _tamanhos_lab_ok(len(novo))
        vid = _snapshot(alvo)
        antes = ler(rel)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(str(novo_conteudo))
        diff = _diferenca(antes, str(novo_conteudo), rel)
        B._audit(ferramenta="lab_editar", decisao="executado", resultado=rel, versao=vid)
        return f"Editado {rel} (versão {vid}). Diferença:\n" + ("".join(diff) or "— o arquivo não mudou —")[:1200]

def excluir(rel):
    """Exclui (movendo para .grave/ para recuperação garantida) um arquivo do laboratório."""
    alvo = _validar_caminho(rel)
    if not os.path.exists(alvo): raise ValueError(f"Arquivo {rel!r} não existe no laboratório.")
    with _trava:
        vid = _snapshot(alvo)
        rel_l = os.path.relpath(alvo, LAB_ROOT)
        destino = os.path.join(GRAVE_JARDIM, rel_l)
        os.makedirs(os.path.dirname(destino) or GRAVE_JARDIM, exist_ok=True)
        # Reposição real e recuperável: move para a área de lixo (permite restauração)
        os.remove(alvo)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(ler_versao(vid, rel_l))
        B._audit(ferramenta="lab_excluir", decisao="executado", resultado=rel, versao=vid)
        return f"Excluído do laboratório: {rel} (recuperável na versão {vid})."

def renomear(rel, novo_rel):
    """Renomeia (na verdade: copia conteúdo, snapshot, excluir antigo) um arquivo no laboratório."""
    alvo = _validar_caminho(rel)
    novo_alvo = _validar_caminho(novo_rel)
    if not os.path.exists(alvo): raise ValueError(f"Arquivo {rel!r} não existe no laboratório.")
    if os.path.lexists(novo_alvo): raise ValueError(f"Destino {novo_rel!r} já existe no laboratório.")
    with _trava:
        vid = _snapshot(alvo)
        conteudo = ler(rel)
        os.makedirs(os.path.dirname(novo_alvo) or LAB_ROOT, exist_ok=True)
        with open(novo_alvo, "x", encoding="utf-8") as f:
            f.write(conteudo)
        # exclusão real (com recuperação via versão)
        os.remove(alvo)
        B._audit(ferramenta="lab_renomear", decisao="executado", resultado=f"{rel} -> {novo_rel}", versao=vid)
        return f"Renomeado no laboratório: {rel} -> {novo_rel} (versão {vid})."

def ler_versao(vid, rel):
    """Lê a versão snapshot de um arquivo (para rollback ou diferença)."""
    p = os.path.join(VERSOES, vid, rel)
    if not os.path.exists(p): raise ValueError(f"Versão {vid!r} do arquivo {rel!r} não existe.")
    with open(p, encoding="utf-8") as f:
        return f.read()

def restaurar(vid, rel):
    """Recupera uma versão anterior (rollback) de um arquivo do laboratório."""
    alvo = _validar_caminho(rel)
    conteudo = ler_versao(vid, rel)
    with _trava:
        vid_atual = _snapshot(alvo) if os.path.exists(alvo) else None
        os.makedirs(os.path.dirname(alvo) or LAB_ROOT, exist_ok=True)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(conteudo)
        B._audit(ferramenta="lab_restaurar", decisao="executado", resultado=rel, versao=vid, versao_anterior=vid_atual)
        return f"Restaurado {rel} para a versão {vid}."

def historico_versoes(rel=None):
    """Lista versões (snapshot) registradas para um arquivo ou para o laboratório todo."""
    lab = _lab_absoluto()
    arqs = []
    if not os.path.isdir(VERSOES): return []
    for vid in os.listdir(VERSOES):
        meta_p = os.path.join(VERSOES, vid, "meta.json")
        try:
            with open(meta_p, encoding="utf-8") as f: meta = json.load(f)
        except (OSError, ValueError): continue
        if rel is None or meta.get("arquivo") == rel:
            arqs.append(meta)
    return sorted(arqs, key=lambda m: m["ts"], reverse=True)

def diferenca_versoes(vid, rel):
    """Mostra a diferença entre a versão atual e a versão de snapshot (para o painel)."""
    atual = ler(rel) if os.path.exists(_validar_caminho(rel)) else ""
    antiga = ler_versao(vid, rel)
    return "".join(_diferenca(antiga, atual, rel))[:2000]

def testar(rel):
    """Roda DENTRO do laboratório o único arquivo de teste designado (nome «teste_*.py», já confinado). Sem shell, sem rede, com tempo limite:
    subprocess com o próprio interpretador, cwd = LAB_ROOT, ambiente limpo (só PATH, FRIDAY_LAB e a versão do python), o arquivo
    é o único que entra na linha de comando. Limitação documentada: sem Docker (Termux alvo), este é o máximo de isolamento de
    execução possível — o que roda é o arquivo de teste que o próprio ciclo gravou no laboratório, não um comando da IA."""
    if not TESTE_PADRAO.fullmatch(str(rel)):
        raise ValueError("Só roda no laboratório um arquivo de teste designado (nome teste_*.py, até 50 caracteres).")
    alvo = _validar_caminho(rel)
    if not os.path.exists(alvo):
        raise ValueError(f"Arquivo de teste {rel!r} não existe no laboratório.")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "FRIDAY_LAB": LAB_ROOT,
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    with _trava:                                   # a mesma trava das escritas: entre conferir o hash e rodar, ninguém troca o arquivo
        with open(alvo, "rb") as _f:
            _h = hashlib.sha256(_f.read()).hexdigest()
        if _h not in _TESTES_PERMITIDOS:
            B._audit(ferramenta="lab_testar", decisao="negado_desconhecido", resultado=rel)
            raise ValueError(f"Teste {rel!r} recusado: o conteúdo não é de um teste conhecido do laboratório.")
        B._audit(ferramenta="lab_testar", decisao="executado", resultado=rel)
        try:
            r = subprocess.run([sys.executable, rel], capture_output=True, text=True,
                               timeout=TESTE_TIMEOUT, cwd=LAB_ROOT, env=env)
            if r.returncode == 0:
                return f"PASSOU: {(r.stdout or 'sem saída')[:1200].strip()}"
            return f"FALHOU (código {r.returncode}): {(r.stdout + r.stderr).strip()[-1500:]}"
        except subprocess.TimeoutExpired:
            return f"FALHOU (tempo esgotado): o teste passou de {TESTE_TIMEOUT}s e foi abortado."


def resumo():
    """Para o painel (HUD): o que está no laboratório e o que já foi modificado."""
    try:
        n = len(listar(auditar=False))
    except Exception:
        n = 0
    return {"arquivos": n, "versoes": len(historico_versoes()), "raiz": LAB_ROOT,
            "uso_bytes": _tamanho_lab(), "max_bytes": MAX_LAB}

# ------------------------------------------------------- Registro de ferramentas no corretor

def registrar_todas():
    """Registra as ferramentas do laboratório no corretor. Nível 1 (baixo risco, automático + auditoria), não 2:
    o que justifica a autonomia NÃO é a ferramenta, é o confinamento — toda operação fica presa em LAB_ROOT
    (validação de caminho + resolução de symlink), tira snapshot antes de modificar e é recuperável. Sem o
    confinamento, nenhuma dessas ferramentas existiria (destruição fora do laboratório continua proibida)."""
    B.registrar("lab_criar", "Cria um arquivo dentro do laboratório de engenharia (isolado, .lab/).",
                {"rel": {"type": "string", "maxLength": 100}, "conteudo": {"type": "string", "maxLength": MAX_ARQ}},
                ["rel", "conteudo"], criar, nivel=1, audit_args=("rel",), interno=True)
    B.registrar("lab_ler", "Lê um arquivo do laboratório de engenharia (isolado, .lab/).",
                {"rel": {"type": "string", "maxLength": 100}},
                ["rel"], ler, nivel=0, audit_args=("rel",))
    B.registrar("lab_listar", "Lista arquivos do laboratório de engenharia (isolado, .lab/).",
                {}, [], listar, nivel=0)
    B.registrar("lab_editar", "Edita um arquivo do laboratório (snapshot + diferença automática).",
                {"rel": {"type": "string", "maxLength": 100}, "novo_conteudo": {"type": "string", "maxLength": MAX_ARQ}},
                ["rel", "novo_conteudo"], editar, nivel=1, audit_args=("rel",), interno=True)
    B.registrar("lab_excluir", "Exclui (recuperável, vai para a lixeira do laboratório) um arquivo do laboratório.",
                {"rel": {"type": "string", "maxLength": 100}},
                ["rel"], excluir, nivel=1, audit_args=("rel",), interno=True)
    B.registrar("lab_renomear", "Renomeia (copia + exclui a antiga, recuperável) um arquivo do laboratório.",
                {"rel": {"type": "string", "maxLength": 100}, "novo_rel": {"type": "string", "maxLength": 100}},
                ["rel", "novo_rel"], renomear, nivel=1, audit_args=("rel", "novo_rel"), interno=True)
    B.registrar("lab_restaurar", "Recupera uma versão anterior (rollback) de um arquivo do laboratório.",
                {"rel": {"type": "string", "maxLength": 100}, "vid": {"type": "string", "maxLength": 32}},
                ["rel", "vid"], restaurar, nivel=1, audit_args=("rel", "vid"), interno=True)
    B.registrar("lab_diferenca", "Mostra a diferença entre a versão atual e uma versão anterior de um arquivo do laboratório.",
                {"rel": {"type": "string", "maxLength": 100}, "vid": {"type": "string", "maxLength": 32}},
                ["rel", "vid"], diferenca_versoes, nivel=0, audit_args=("rel", "vid"))
    B.registrar("lab_historico", "Lista as versões (snapshots) de um arquivo ou do laboratório todo.",
                {"rel": {"type": "string", "maxLength": 100}},
                [], historico_versoes, nivel=0, audit_args=("rel",))
    B.registrar("lab_testar", "Roda o arquivo de teste designado (teste_*.py) dentro do laboratório, sem shell e sem rede.",
                {"rel": {"type": "string", "maxLength": 100}},
                ["rel"], testar, nivel=1, audit_args=("rel",), interno=True)

