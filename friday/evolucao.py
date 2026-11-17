"""Promoção local e controlada de candidatos da FRIDAY (sem API externa).

O módulo oferece: allowlist de alvos, testes da versão atual, testes numa cópia
staging, backup append-only por hash, troca atômica, teste pós-promoção e rollback.

IMPORTANTE: staging é uma cópia temporária, NÃO um sandbox de kernel. Código Python
executado nos testes ainda pode acessar o SO/rede com as permissões do usuário.
Use apenas candidatos e testes confiáveis; para isolamento forte, rode o processo
com um usuário/contêiner separado (não presumimos que Termux ofereça isso).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FRIDAY_DIR = (BASE / "friday").resolve()
STATE_DIR = (BASE / ".evolucao").resolve()
BACKUP_DIR = STATE_DIR / "backups"
JOURNAL = STATE_DIR / "diario.jsonl"
MAX_SOURCE_BYTES = 500_000
TEST_TIMEOUT = 120
MAX_TEST_TIMEOUT = 600
_TRAVA_DIARIO = threading.RLock()

# Lista explícita; o mecanismo de evolução não pode modificar as próprias proteções.
ALVOS_PERMITIDOS = frozenset({
    "memoria.py", "neuronios.py", "curiosidade.py", "planejador.py",
    "conversa.py", "objetivos.py", "tarefas.py", "voz.py", "visao.py",
})
ALVOS_PROTEGIDOS = frozenset({
    "evolucao.py", "gerador_local.py", "mae.py", "laboratorio.py", "broker.py",
    "catalogo.py", "autonomia.py", "coordenador.py", "privacidade.py",
    "verificacao.py", "main.py", "estado.py", "protocolos.py", "ferramentas.py",
})

# Verificação heurística: bloqueia novas capacidades perigosas óbvias no diff.
# Não substitui revisão de segurança nem sandbox de kernel.
_IMPORTS_SENSIVEIS = frozenset({
    "subprocess", "socket", "ctypes", "multiprocessing", "pty", "telnetlib",
    "paramiko", "requests", "http.client", "urllib", "ftplib",
})
_CHAMADAS_SENSIVEIS = frozenset({
    "eval", "exec", "compile", "__import__", "importlib.import_module", "setattr", "delattr",
    "open", "builtins.open", "os.open", "os.remove", "os.unlink", "os.rmdir", "os.rename", "os.replace",
    "os.chmod", "os.chown", "os.system", "os.popen", "shutil.rmtree", "shutil.move", "shutil.copyfile",
    "subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call",
    "subprocess.check_output", "socket.socket", "requests.get", "requests.post", "requests.request",
    "urllib.request.urlopen", "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "pathlib.Path.open", "pathlib.Path.unlink", "pathlib.Path.write_text", "pathlib.Path.write_bytes",
    "pathlib.Path.mkdir", "pathlib.Path.rmdir", "pathlib.Path.rename", "pathlib.Path.replace",
})
_CHAMADAS_SENSIVEIS_TERMINAIS = frozenset({
    "unlink", "rmtree", "write_text", "write_bytes", "remove", "replace", "rename",
    "chmod", "chown", "mkdir", "rmdir", "popen", "system", "urlopen",
})


def _hash(bytes_: bytes) -> str:
    return hashlib.sha256(bytes_).hexdigest()


def _registro(evento: dict) -> None:
    """Diário estruturado append-only; não oferece operação de apagamento."""
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    linha = {"ts": time.time(), **evento}
    dados = (json.dumps(linha, ensure_ascii=False, sort_keys=True, default=str) + "\n").encode("utf-8")
    with _TRAVA_DIARIO:
        fd = os.open(str(JOURNAL), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(fd, dados)
            os.fsync(fd)
        finally:
            os.close(fd)


def _alvo(relativo: str) -> Path:
    """Resolve alvo autorizado existente ou um novo módulo em friday/generated/."""
    if not isinstance(relativo, str) or not relativo or "\\" in relativo:
        raise ValueError("Caminho inválido.")
    p = Path(relativo)
    if p.is_absolute() or any(parte in (".", "..") for parte in p.parts):
        raise ValueError("Caminho absoluto e travessia de diretório não são permitidos.")

    # Módulos existentes: apenas a allowlist da raiz friday/.
    if len(p.parts) == 2 and p.parts[0] == "friday":
        nome = p.parts[1]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", nome):
            raise ValueError("Nome de módulo inválido.")
        if nome in ALVOS_PROTEGIDOS or nome not in ALVOS_PERMITIDOS:
            raise PermissionError(f"Módulo não promovível por automodificação: {nome}")
        bruto = FRIDAY_DIR / nome
        if bruto.is_symlink():
            raise ValueError("Links simbólicos não podem ser alvos de promoção.")
        alvo = bruto.resolve()
        if alvo.parent != FRIDAY_DIR or not alvo.is_file():
            raise ValueError("O alvo existente deve ser um arquivo regular dentro de friday/.")
        return alvo

    # Criação/atualização de módulos isolados: nunca substitui os módulos de segurança.
    if len(p.parts) == 3 and p.parts[0] == "friday" and p.parts[1] == "generated":
        nome = p.parts[2]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,60}\.py", nome):
            raise ValueError("Nome de módulo gerado inválido.")
        pasta = FRIDAY_DIR / "generated"
        if pasta.is_symlink() or not pasta.is_dir():
            raise ValueError("A pasta friday/generated/ deve existir e não pode ser link simbólico.")
        bruto = pasta / nome
        if bruto.is_symlink():
            raise ValueError("Links simbólicos não podem ser alvos de promoção.")
        alvo = bruto.resolve()
        if alvo.parent != pasta.resolve() or (alvo.exists() and not alvo.is_file()):
            raise ValueError("O módulo gerado deve ser um arquivo regular direto em friday/generated/.")
        return alvo

    raise ValueError("Use friday/<módulo autorizado>.py ou friday/generated/<módulo_novo>.py.")


def _marcadores_risco(source: str) -> Counter:
    """Conta capacidades sensíveis óbvias presentes no AST do candidato."""
    arvore = ast.parse(source)
    achados: Counter = Counter()
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modulo = alias.name
                root = modulo.split(".", 1)[0]
                if modulo in _IMPORTS_SENSIVEIS or root in _IMPORTS_SENSIVEIS:
                    achados[f"import:{modulo}"] += 1
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            if module in _IMPORTS_SENSIVEIS or root in _IMPORTS_SENSIVEIS:
                achados[f"import:{module}"] += 1
        elif isinstance(node, ast.Call):
            partes = []
            atual = node.func
            while isinstance(atual, ast.Attribute):
                partes.append(atual.attr)
                atual = atual.value
            if isinstance(atual, ast.Name):
                partes.append(atual.id)
                nome = ".".join(reversed(partes))
                terminal = node.func.attr if isinstance(node.func, ast.Attribute) else nome
                if nome in _CHAMADAS_SENSIVEIS or terminal in _CHAMADAS_SENSIVEIS_TERMINAIS:
                    chave = nome if nome in _CHAMADAS_SENSIVEIS else f"*.{terminal}"
                    achados[f"call:{chave}"] += 1
                    assinatura = ast.dump(node, annotate_fields=True, include_attributes=False)
                    assinatura_hash = hashlib.sha256(assinatura.encode("utf-8")).hexdigest()[:20]
                    achados[f"call-expr:{chave}:{assinatura_hash}"] += 1
    return achados


def validar_candidato(relativo: str, conteudo: str) -> dict:
    """Valida alvo, tamanho, sintaxe e aumento de capacidades sensíveis óbvias."""
    alvo = _alvo(relativo)
    if not isinstance(conteudo, str):
        raise TypeError("O código candidato precisa ser texto UTF-8.")
    dados = conteudo.encode("utf-8")
    if len(dados) > MAX_SOURCE_BYTES:
        raise ValueError("Conteúdo maior que 500 KB.")
    if not conteudo.strip():
        raise ValueError("Candidato vazio.")
    ast.parse(conteudo, filename=relativo)
    original = alvo.read_text(encoding="utf-8") if alvo.exists() else ""
    antes, depois = _marcadores_risco(original), _marcadores_risco(conteudo)
    acrescentados = {k: depois[k] - antes[k] for k in depois if depois[k] > antes[k]}
    if acrescentados:
        nomes = ", ".join(f"{k} (+{n})" for k, n in sorted(acrescentados.items()))
        raise PermissionError("O candidato adiciona capacidade sensível bloqueada pela política local: " + nomes)
    return {"alvo": relativo, "sha256": _hash(dados), "bytes": len(dados), "sintaxe": "válida",
            "marcadores_sensiveis_novos": 0}


def _validar_comandos(comandos) -> list[list[str]]:
    """Só permite pytest/unittest executados como módulo Python; nunca shell ou `-c`."""
    if not isinstance(comandos, (list, tuple)) or not comandos:
        raise ValueError("É obrigatório fornecer ao menos um comando de teste confiável.")
    saida: list[list[str]] = []
    executaveis = {sys.executable, "python", "python3"}
    for cmd in comandos:
        if not isinstance(cmd, (list, tuple)) or len(cmd) < 3:
            raise ValueError("Use [python, -m, pytest|unittest, ...] para cada teste.")
        if any(not isinstance(x, str) or not x or "\x00" in x for x in cmd):
            raise ValueError("Argumento de teste inválido.")
        if cmd[0] not in executaveis or cmd[1] != "-m" or cmd[2] not in {"pytest", "unittest"}:
            raise ValueError("Comandos aceitos: Python -m pytest ou Python -m unittest; shell e módulos arbitrários são bloqueados.")
        if any(x in {"-c", "--eval", "--exec"} for x in cmd):
            raise ValueError("Execução inline de código não é permitida.")
        # Evita caminhos explícitos que escapem do projeto de teste.
        for x in cmd[3:]:
            if not x.startswith("-") and ".." in Path(x).parts:
                raise ValueError("Caminhos de teste não podem conter '..'.")
        saida.append(list(cmd))
    return saida


def _executar_testes(comandos, timeout=TEST_TIMEOUT, cwd=None):
    """Executa somente comandos de teste validados, sem shell e com ambiente reduzido.

    Atenção: o ambiente reduzido não desliga a rede e não é isolamento de kernel.
    """
    comandos_ok = _validar_comandos(comandos)
    raiz = Path(cwd or BASE).resolve()
    resultados = []
    home = raiz / ".evolucao" / "test-home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(raiz),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    for cmd in comandos_ok:
        try:
            proc = subprocess.run(cmd, cwd=str(raiz), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=timeout, shell=False, env=env,
                                  close_fds=True)
            resultado = {"comando": cmd, "codigo": proc.returncode, "saida": proc.stdout[-12000:]}
        except subprocess.TimeoutExpired as exc:
            saida = exc.stdout or ""
            if isinstance(saida, bytes):
                saida = saida.decode("utf-8", "replace")
            resultado = {"comando": cmd, "codigo": -1, "saida": str(saida)[-12000:], "timeout": True}
        except OSError as exc:
            resultado = {"comando": cmd, "codigo": -2, "saida": f"erro ao executar teste: {type(exc).__name__}"}
        resultados.append(resultado)
        if resultado["codigo"] != 0:
            return False, resultados
    return True, resultados


def _copiar_staging(destino: Path) -> Path:
    """Copia o projeto para staging sem estado local, segredos usuais, caches ou links."""
    ignorar_padrao = shutil.ignore_patterns(
        ".git", ".evolucao", ".cerebro", ".lab", "__pycache__", ".pytest_cache",
        ".venv", "venv", "node_modules", "build", "dist", ".env", ".env.*",
        "*.db", "*.sqlite", "*.sqlite3", "*.pyc",
    )

    def ignorar_links(diretorio, nomes):
        ignorados = set(ignorar_padrao(diretorio, nomes))
        links = [nome for nome in nomes if nome not in ignorados and (Path(diretorio) / nome).is_symlink()]
        if links:
            raise ValueError("Staging cancelado: o projeto contém links simbólicos fora das áreas ignoradas: "
                             + ", ".join(links[:10]))
        return list(ignorados)

    staged = destino / "project"
    # symlinks=False evita importar links de fora; a função acima os recusa antes da cópia.
    shutil.copytree(BASE, staged, ignore=ignorar_links, symlinks=False)
    return staged


def _arquivar(caminho: Path, motivo: str) -> Path | None:
    """Regra «nada é apagado»: em vez de remover, MOVE o arquivo para .evolucao/arquivo/ (recuperável)."""
    if not caminho.exists() and not caminho.is_symlink():
        return None
    destino_dir = STATE_DIR / "arquivo"
    destino_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destino = destino_dir / f"{time.time_ns()}-{motivo}-{caminho.name}"
    os.replace(caminho, destino)
    return destino


def _escrever_atomico(destino: Path, dados: bytes, modo: int | None = None) -> None:
    fd, nome = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=str(destino.parent))
    tmp = Path(nome)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        if modo is not None:
            os.chmod(tmp, modo & 0o777)
        os.replace(tmp, destino)
        try:
            dfd = os.open(str(destino.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        if tmp.exists():          # só sobra se a escrita falhou: vai para o arquivo, não para o lixo
            try:
                _arquivar(tmp, "tmp-falho")
            except OSError:
                pass


def _criar_backup(alvo: Path, original: bytes, relativo: str, original_existe: bool = True) -> Path:
    """Cria snapshot sem sobrescrita, com hash e permissões restritivas; nunca apaga backups."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = _hash(original)
    pasta = BACKUP_DIR / f"{alvo.stem}-{time.time_ns()}-{digest[:12]}"
    pasta.mkdir(mode=0o700)
    fonte = pasta / "original.py.bak"
    with fonte.open("xb") as f:
        f.write(original)
        f.flush()
        os.fsync(f.fileno())
    manifesto = {"alvo": relativo, "sha256": digest, "bytes": len(original), "original_existe": original_existe,
                 "criado_em": time.time(),
                 "aviso": "backup append-only do mecanismo; permissões locais não são uma barreira contra o mesmo usuário/root"}
    meta = pasta / "manifest.json"
    with meta.open("x", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    for p in (fonte, meta):
        try:
            os.chmod(p, 0o400)
        except OSError:
            pass
    try:
        os.chmod(pasta, 0o500)
    except OSError:
        pass
    return fonte


def promover(relativo: str, conteudo: str, comandos_teste, timeout: int = TEST_TIMEOUT) -> dict:
    """Testa baseline e candidato em staging, promove atomicamente e testa novamente.

    Também cria módulos em `friday/generated/`, mas exige um teste específico
    `tests/test_<nome>.py` (com `pytest.importorskip` para permitir que a versão
    ainda inexistente seja pulada no baseline). Módulos gerados não são conectados
    automaticamente ao núcleo; a integração explícita fica a cargo do projeto.
    """
    alvo = _alvo(relativo)
    comandos_ok = _validar_comandos(comandos_teste)
    timeout = max(1, min(int(timeout), MAX_TEST_TIMEOUT))
    original_existe = alvo.exists()
    if not original_existe:
        if not relativo.startswith("friday/generated/"):
            raise ValueError("Só é permitido criar módulos novos em friday/generated/.")
        required_test = f"test_{alvo.stem}.py"
        test_file = BASE / "tests" / required_test
        if not test_file.is_file() or test_file.is_symlink():
            raise ValueError(f"Para criar este módulo, crie primeiro tests/{required_test}.")
        # Pode-se executar apenas o teste dedicado ou a suíte completa em tests/.
        menciona_teste = any(
            required_test in arg or arg == "tests"
            for cmd in comandos_ok for arg in cmd
        )
        if not menciona_teste:
            raise ValueError(f"Inclua tests/{required_test} ou a pasta tests/ nos testes de promoção.")
    original = alvo.read_bytes() if original_existe else b""
    if not isinstance(conteudo, str):
        raise TypeError("O código candidato precisa ser texto UTF-8.")
    novo = conteudo.encode("utf-8")
    if original_existe and original == novo:
        return {"status": "sem_mudanca", "hash": _hash(original)}
    validacao = validar_candidato(relativo, conteudo)

    baseline_ok, baseline = _executar_testes(comandos_ok, timeout=timeout, cwd=BASE)
    if not baseline_ok:
        _registro({"evento": "promocao_bloqueada", "alvo": relativo, "motivo": "baseline_falhou", "testes": baseline})
        return {"status": "bloqueado", "motivo": "Os testes da versão atual falharam; nenhuma alteração foi aplicada.", "testes_baseline": baseline}

    # Validação do código candidato ocorre numa cópia separada, antes de tocar no arquivo ativo.
    with tempfile.TemporaryDirectory(prefix="friday-staging-") as tmpdir:
        staged_root = _copiar_staging(Path(tmpdir))
        staged_target = staged_root / relativo
        staged_target.parent.mkdir(parents=True, exist_ok=True)
        staged_target.write_bytes(novo)
        staged_ok, staged_results = _executar_testes(comandos_ok, timeout=timeout, cwd=staged_root)

    if not staged_ok:
        _registro({"evento": "candidato_rejeitado", "alvo": relativo, "motivo": "testes_staging_falharam",
                   "hash_candidato": _hash(novo), "testes_baseline": baseline, "testes_staging": staged_results})
        return {"status": "rejeitado", "motivo": "O candidato falhou no staging; o arquivo ativo não foi tocado.",
                "validacao": validacao, "testes_baseline": baseline, "testes_staging": staged_results}

    backup = _criar_backup(alvo, original, relativo, original_existe=original_existe)
    modo = (alvo.stat().st_mode & 0o777) if original_existe else 0o644
    try:
        _escrever_atomico(alvo, novo, modo)
        pos_ok, pos_results = _executar_testes(comandos_ok, timeout=timeout, cwd=BASE)
        if not pos_ok:
            if original_existe:
                _escrever_atomico(alvo, original, modo)
            else:
                _arquivar(alvo, "rollback")      # módulo novo que falhou: sai de friday/ mas fica recuperável
            _registro({"evento": "rollback_automatico", "alvo": relativo, "antes": _hash(original),
                       "original_existe": original_existe, "candidato": _hash(novo),
                       "backup": str(backup.relative_to(BASE)), "testes_pos_promocao": pos_results})
            return {"status": "revertido", "motivo": "A verificação pós-promoção falhou; a versão anterior foi restaurada.",
                    "backup": str(backup.relative_to(BASE)), "testes_baseline": baseline,
                    "testes_staging": staged_results, "testes_pos_promocao": pos_results}
        _registro({"evento": "promocao_aprovada", "alvo": relativo, "antes": _hash(original), "depois": _hash(novo),
                   "criado": not original_existe, "backup": str(backup.relative_to(BASE)),
                   "testes_baseline": baseline, "testes_staging": staged_results, "testes_pos_promocao": pos_results})
        return {"status": "promovido", "criado": not original_existe, "hash_anterior": _hash(original),
                "hash_novo": _hash(novo), "backup": str(backup.relative_to(BASE)), "validacao": validacao,
                "testes_baseline": baseline, "testes_staging": staged_results, "testes_pos_promocao": pos_results}
    except Exception as exc:
        # Nunca deixa a aplicação parcialmente modificada se ocorrer erro após a troca.
        try:
            if original_existe:
                atual = alvo.read_bytes() if alvo.exists() else b""
                if atual != original:
                    _escrever_atomico(alvo, original, modo)
            elif alvo.exists():
                _arquivar(alvo, "rollback")
        finally:
            _registro({"evento": "erro_promocao", "alvo": relativo, "erro": type(exc).__name__,
                       "original_existe": original_existe, "backup": str(backup.relative_to(BASE))})
        raise


def registrar_experiencia_mae(experiencia: dict) -> bool:
    """Liga o MAE ao diário da evolução sem misturar o teste toy à produção.

    O resultado é uma observação, nunca uma autorização para promover código.
    """
    if not isinstance(experiencia, dict):
        return False
    permitidos = ("em", "objetivo", "problema", "hipotese", "tentativas", "resultado",
                  "previsao", "observado", "arquivos_modificados", "arquivos_excluidos", "versao", "rollback", "dif")
    dado = {k: experiencia.get(k) for k in permitidos if k in experiencia}
    dado["evento"] = "experiencia_mae"
    dado["origem"] = "mae_laboratorio"
    dado["resultado"] = dado.get("resultado") if dado.get("resultado") in {"sucesso", "falha", "inconclusivo"} else "inconclusivo"
    for k in ("objetivo", "problema", "hipotese", "previsao", "observado", "dif", "versao", "rollback"):
        if k in dado and isinstance(dado[k], str):
            dado[k] = dado[k][:400]
    for k in ("arquivos_modificados", "arquivos_excluidos"):
        if k in dado and isinstance(dado[k], list):
            dado[k] = [str(x)[:100] for x in dado[k][:20]]
    try:
        _registro(dado)
        return True
    except OSError:
        return False


def historico(limite: int = 50) -> list[dict]:
    if not JOURNAL.exists():
        return []
    limite = max(1, min(int(limite), 500))
    try:
        linhas = JOURNAL.read_text(encoding="utf-8").splitlines()[-limite:]
    except OSError:
        return []
    saida = []
    for linha in linhas:
        try:
            item = json.loads(linha)
            if isinstance(item, dict):
                saida.append(item)
        except ValueError:
            continue
    return saida
