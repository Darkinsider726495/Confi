"""Mãos da FRIDAY: um sentido novo. A câmera acompanha as SUAS mãos dentro do navegador (MediaPipe) e você modela em 3D com gestos.
Adaptado do Voxel Architect (github.com/DEVNEPTUNE/potential-palm-tree).

O que sai do navegador para cá é pouco, de propósito:
  - o NOME de um gesto, de uma lista fixa (`GESTOS`); nunca imagem, nunca os pontos da mão;
  - o modelo 3D que VOCÊ manda salvar (só números inteiros: posições de blocos numa grade).
Nenhuma ferramenta da IA usa isto, e o servidor nunca pede a câmera: quem abre a página /maos é você.
Nada é apagado: cada salvamento é uma versão nova (`.cerebro/modelos3d/<nome>/<data>.json`) e o modelo vira um neurônio em Memorias (projeto)."""
import re, json, time, threading, datetime as dt
import memoria as M

GESTOS = {
    "construir": "pinça da mão direita: coloca blocos (segure para travar a intenção)",
    "apagar": "pinça da esquerda + indicador da direita: apaga blocos",
    "fixar": "palma direita aberta: transforma o esboço em blocos",
    "agarrar": "punho esquerdo: segura o mundo e o move",
    "girar": "duas palmas abertas: gira o mundo",
    "reiniciar": "dois punhos segurando: limpa a cena (um rascunho é guardado antes)",
}
MAX_BLOCOS = 20000          # tamanho da página (cabe numa grade de 1,2 unidades); é limite de tela, não de memória dela
LIMITE_COORD = 500          # posição máxima de um bloco na grade
MAX_NOME = 60
INTERVALO_MIN_S = 5.0       # o mesmo modelo não é salvo mais de uma vez a cada 5 s (o navegador salva rascunhos sozinho)
PASTA = "modelos3d"
ESTATICOS = {               # única lista do que /static/maos serve (nada de caminho vindo da URL)
    "three.min.js": "text/javascript; charset=utf-8", "hands.js": "text/javascript; charset=utf-8",
    "maos_gestos.js": "text/javascript; charset=utf-8", "maos.js": "text/javascript; charset=utf-8",
    "hands_solution_packed_assets_loader.js": "text/javascript; charset=utf-8",
    "hands_solution_simd_wasm_bin.js": "text/javascript; charset=utf-8", "hands_solution_simd_wasm_bin.wasm": "application/wasm",
    "hands_solution_simd_wasm_bin.data": "application/octet-stream", "hands_solution_packed_assets.data": "application/octet-stream",
    "hands.binarypb": "application/octet-stream", "hand_landmark_lite.tflite": "application/octet-stream",
    "hand_landmark_full.tflite": "application/octet-stream", "LICENSE-three.txt": "text/plain; charset=utf-8",
}
_trava = threading.Lock()
_e = {"gestos": {}, "ultimo": "", "t": 0.0}
_ult_salvo = {}


def gesto(nome):
    """Um gesto da lista fixa chegou do navegador. Devolve False para qualquer outro nome."""
    if not isinstance(nome, str) or nome not in GESTOS:
        return False
    with _trava:
        _e["gestos"][nome] = _e["gestos"].get(nome, 0) + 1
        _e["ultimo"], _e["t"] = nome, time.time()
    try:
        import prefrontal as PFC
        PFC.perceber("maos", nome)
    except Exception:
        pass
    return True


def _slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", M._fold(nome)).strip("-")[:40] or "modelo"


def _nome_limpo(nome):
    n = M._titulo_limpo(nome if isinstance(nome, str) else "")[:MAX_NOME].strip()
    if not n:
        n = "modelo"
    if M.sensivel(n):
        raise ValueError("esse nome parece um dado sensível; escolha outro")
    return n


def _blocos_validos(voxels):
    if not isinstance(voxels, list) or not voxels:
        raise ValueError("modelo vazio")
    if len(voxels) > MAX_BLOCOS:
        raise ValueError(f"blocos demais (máx. {MAX_BLOCOS})")
    vistos = set()
    for v in voxels:
        if not isinstance(v, (list, tuple)) or len(v) != 3:
            raise ValueError("bloco inválido")
        for c in v:
            if isinstance(c, bool) or not isinstance(c, int) or abs(c) > LIMITE_COORD:
                raise ValueError("coordenada inválida")
        vistos.add((v[0], v[1], v[2]))
    return sorted(vistos)


def _dir(nome):
    return M._dentro(M.base() / ".cerebro" / PASTA / _slug(nome))


_VERSAO = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:-(\d+))?\.json$")


def _versoes(pasta):
    """Versões de um modelo, da mais antiga para a mais nova. Ordena pela data e depois pelo número («-2», «-3»): só ordenar o nome errava, porque «-2.json» vem antes de «.json»."""
    achadas = []
    for a in pasta.glob("*.json"):
        m = _VERSAO.match(a.name)
        if m:
            achadas.append(((m.group(1), int(m.group(2) or 1)), a))
    return [a for _, a in sorted(achadas)]


def guardar_modelo(nome, voxels, rascunho=False, agora=None):
    """Salva uma NOVA versão do modelo. Levanta ValueError (entrada ruim) ou RuntimeError (memória desligada). Devolve {'ok', 'nome', 'blocos', 'versao'}."""
    if not M.ativo():
        raise RuntimeError("memória desligada (OBSIDIAN_VAULT=off)")
    nome = _nome_limpo(nome)
    blocos = _blocos_validos(voxels)
    t = time.time() if agora is None else agora
    with _trava:
        if t - _ult_salvo.get(_slug(nome), -1e9) < INTERVALO_MIN_S:
            raise ValueError("calma: acabei de guardar esse modelo")
        _ult_salvo[_slug(nome)] = t
    when = M._agora()
    pasta = _dir(nome)
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{when:%Y-%m-%d_%H-%M-%S}"
    arq, k = pasta / f"{base}.json", 1
    while arq.exists():                                    # nunca sobrescreve uma versão
        k += 1
        arq = pasta / f"{base}-{k}.json"
    versao = len(_versoes(pasta)) + 1
    M._escrever(arq, json.dumps({"nome": nome, "criado": when.isoformat(timespec="seconds"), "rascunho": bool(rascunho), "grade": 1.2,
                                 "blocos": [list(b) for b in blocos]}, ensure_ascii=False))
    xs, ys, zs = zip(*blocos)
    dim = f"{max(xs) - min(xs) + 1}×{max(ys) - min(ys) + 1}×{max(zs) - min(zs) + 1}"
    try:
        M.guardar(f"Modelo 3D {nome}", f"Modelo 3D que construí com as mãos: {len(blocos)} blocos, {dim} (versão {versao}{', rascunho' if rascunho else ''}). "
                  f"Os dados ficam em .cerebro/{PASTA}/{_slug(nome)}.", tipo="projeto", importancia=2, tags="maos modelo3d")
    except (ValueError, OSError, RuntimeError):
        pass                                               # o modelo já está guardado; o neurônio é um bônus
    return {"ok": True, "nome": nome, "blocos": len(blocos), "versao": versao}


def modelos():
    """Nomes dos modelos guardados (o nome que você deu), em ordem alfabética."""
    if not M.ativo():
        return []
    raiz = M.base() / ".cerebro" / PASTA
    nomes = []
    if raiz.is_dir():
        for d in sorted(raiz.iterdir())[:500]:
            if d.is_dir() and not d.is_symlink():
                ult = _versoes(d)
                if ult:
                    try:
                        nomes.append(str(json.loads(ult[-1].read_text(encoding="utf-8")).get("nome", d.name))[:MAX_NOME])
                    except (OSError, ValueError):
                        continue
    return sorted(set(nomes), key=str.lower)


def carregar(nome):
    """Última versão do modelo: lista de [x, y, z] ou None."""
    if not M.ativo() or not isinstance(nome, str):
        return None
    try:
        pasta = _dir(_nome_limpo(nome))
    except ValueError:
        return None
    ult = _versoes(pasta) if pasta.is_dir() else []
    if not ult:
        return None
    try:
        d = json.loads(ult[-1].read_text(encoding="utf-8"))
        return [list(b) for b in _blocos_validos(d.get("blocos"))]
    except (OSError, ValueError):
        return None


def resumo():
    """Para o painel (chamado toda hora): só conta pastas, não lê os modelos."""
    n = 0
    if M.ativo():
        try:
            raiz = M.base() / ".cerebro" / PASTA
            n = sum(1 for d in raiz.iterdir() if d.is_dir() and not d.is_symlink()) if raiz.is_dir() else 0
        except OSError:
            n = 0
    with _trava:
        return {"gestos": sum(_e["gestos"].values()), "ultimo": _e["ultimo"], "modelos": n}


# ---------------------------------------------------------------- por voz
_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_USAR = re.compile(_P + r"(?:como (?:eu )?(?:uso|usar|usa) (?:as |suas )?maos|abra as maos|modo maos|quero modelar(?: em 3d)?|me ensine a usar as maos|o que sao (?:as )?suas maos|o que voce faz com as maos)$")
_MODELOS = re.compile(_P + r"(?:quais (?:sao )?(?:os )?(?:meus )?modelos(?: 3d)?(?: que (?:eu )?(?:fiz|construi|salvei))?|meus modelos(?: 3d)?|o que (?:eu )?construi com as maos)$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).rstrip(".!? ")
    if _USAR.match(f):
        return ("As mãos são um sentido novo: abra «/maos» no painel e deixe a câmera ver as suas mãos. Pinça da direita constrói, a palma aberta fixa, o punho da esquerda agarra o mundo, "
                "duas palmas giram e dois punhos segurando reiniciam a cena, mas eu guardo um rascunho antes. A câmera fica só no navegador: para mim chega apenas o nome do gesto e os modelos que você salvar.")
    if _MODELOS.match(f):
        m = modelos()
        if not m:
            return "Você ainda não salvou nenhum modelo 3D. Abra «/maos», construa e toque em «Salvar modelo»."
        return f"Você salvou {len(m)} {'modelo' if len(m) == 1 else 'modelos'} 3D: " + ", ".join(m[:10]) + (" e mais." if len(m) > 10 else ".")
    return None
