"""Conferir o EFEITO de uma ação por fora da ferramenta (Fase 2).

Uma ferramenta que devolve «Lembrete criado» só disse que achou que criou. Aqui a FRIDAY olha o estado real — o banco, a pasta de arquivos, o cofre —
e responde uma de quatro coisas:

  confirmado       o efeito está lá (forca = «independente» quando veio de olhar o estado; «da_resposta» quando é uma leitura e só temos a resposta dela)
  refutado         a ferramenta disse que fez e o efeito NÃO está lá (ou a leitura voltou com erro)
  nao_verificavel  não há como conferir daqui (SMS, ligação, relé, lanterna…): fica registrado como «executada sem verificação», nunca como cumprida
  inconclusivo     era possível conferir, mas a conferência falhou (cofre desligado, erro de leitura): também não vira cumprida

Duas fases, porque «existe um lembrete com esse texto» não prova que ESTA ação o criou: `antes()` tira uma marca (o maior id, os arquivos de hoje, a hora)
e `depois()` só aceita o que apareceu depois dela. A marca é pequena e serializável: quem retoma uma tarefa depois de um reinício usa a mesma marca
para saber se uma ação interrompida chegou a acontecer.

A evidência é uma frase curta, sem o conteúdo do que foi pedido. Este módulo só LÊ: não chama o corretor e não escreve em nada.
"""
import os, re, time
import broker as B
import ferramentas as F
import criar as K
import memoria as M
import neuronios as NEU
import privacidade as P

CONFIRMADO, REFUTADO, NAO_VERIFICAVEL, INCONCLUSIVO = "confirmado", "refutado", "nao_verificavel", "inconclusivo"
VEREDITOS = (CONFIRMADO, REFUTADO, NAO_VERIFICAVEL, INCONCLUSIVO)
INDEPENDENTE, DA_RESPOSTA, NENHUMA = "independente", "da_resposta", "nenhuma"
FOLGA = 5.0          # segundos de tolerância nas comparações de relógio
FOLGA_MTIME = 0.25   # o relógio dos arquivos é «grosso» (alguns milissegundos atrás do relógio comum); folga curta para não aceitar nota antiga

# Por que cada ferramenta com efeito no mundo não dá para conferir daqui (o motivo vai para a evidência).
SEM_COMO_CONFERIR = {
    "enviar_sms": "o SMS sai do celular e não há como ver daqui se foi entregue",
    "ligar": "a ligação acontece no celular e não há como conferir daqui",
    "rele": "o relé é físico e não devolve o estado a ela",
    "lanterna": "a lanterna é do celular e não devolve o estado a ela",
    "vibrar": "a vibração é do celular e não deixa rastro",
    "notificar": "a notificação sai pelo servidor de push e não há confirmação de leitura",
    "preparar_whatsapp": "só abre o WhatsApp; quem envia é o dono",
    "localizacao": "o GPS do celular não é conferível por outro caminho",
    "compartilhar_arquivo": "o menu de compartilhar é do Android; o destino é do dono",
    "esquecer_memoria": "ainda não há conferência de arquivamento",
    "consolidar_memoria": "ainda não há conferência da consolidação",
    "exportar_cerebro": "ainda não há conferência do arquivo exportado",
}
_ESPACOS = re.compile(r"\s+")


def _uma_linha(t):
    return _ESPACOS.sub(" ", str(t)).strip()


def _v(veredito, evidencia, forca=INDEPENDENTE):
    return {"veredito": veredito, "forca": forca if veredito in (CONFIRMADO, REFUTADO) else NENHUMA, "evidencia": P.redigir(evidencia, 200), "em": time.time()}


# ---------------------------------------------------------------- conferências por ferramenta: (antes(args) -> dict, conferir(args, base) -> (veredito, evidencia))
def _antes_lembrete(args):
    return {"marca": F.marca_lembretes()}


def _conf_lembrete(args, base):
    agora = time.time()
    minutos = max(0.1, min(float(args.get("minutos", 0)), 60 * 24 * 30))
    texto = str(args.get("texto", ""))[:200]
    alvo = base["t0"] + minutos * 60
    for quando, t, _feito in F.lembretes_depois(base["marca"]):
        if t == texto and alvo - FOLGA <= quando <= agora + minutos * 60 + FOLGA:
            return CONFIRMADO, "o lembrete novo está no banco, com o texto e o horário pedidos"
    return REFUTADO, "nenhum lembrete novo com o texto e o horário pedidos apareceu no banco"


def _antes_nota(args):
    return {"marca": F.marca_notas()}


def _conf_nota(args, base):
    texto = str(args.get("texto", ""))[:1000]
    if texto in F.notas_depois(base["marca"]):
        return CONFIRMADO, "a nota nova está no banco com o texto pedido"
    return REFUTADO, "nenhuma nota nova com o texto pedido apareceu no banco"


def _parecidos(nome):
    """Arquivos da pasta que podem ter nascido de `criar_arquivo(nome, …)`: «nome.ext», «nome-2.ext», «nome-3.ext»…"""
    base, ext = os.path.splitext(str(nome).strip())
    padrao = re.compile(re.escape(base) + r"(?:-\d+)?" + re.escape(ext) + r"\Z")
    return sorted(n for n in os.listdir(K.pasta()) if padrao.match(n))


def _antes_arquivo(args):
    return {"existentes": _parecidos(args.get("nome", ""))}


def _conf_arquivo(args, base):
    novos = [n for n in _parecidos(args.get("nome", "")) if n not in set(base.get("existentes", []))]
    if not novos:
        return REFUTADO, "nenhum arquivo novo com esse nome apareceu na pasta"
    esperado = str(args.get("conteudo", ""))
    for n in novos:
        p = os.path.join(K.pasta(), n)
        try:
            with open(p, encoding="utf-8") as f:
                lido = f.read(K.MAX_ARQ + 1)
        except (OSError, UnicodeDecodeError):
            continue
        if lido == esperado:
            return CONFIRMADO, f"o arquivo «{n}» existe, com {os.path.getsize(p)} bytes e o conteúdo pedido"
    return REFUTADO, "apareceu um arquivo novo com esse nome, mas o conteúdo não é o pedido"


def _conf_memoria(args, base):
    if not M.ativo():
        return INCONCLUSIVO, "a memória está desligada: não há onde conferir"
    texto = _uma_linha(args.get("texto", ""))
    pasta = M.base() / "Memorias"
    desde = base["t0"] - FOLGA_MTIME
    try:
        nomes = [n for n in os.listdir(pasta) if n.endswith(".md")]
    except OSError:
        return REFUTADO, "a pasta de memórias não existe ou está vazia"
    for n in nomes:
        p = pasta / n
        try:
            if p.stat().st_mtime < desde:
                continue
        except OSError:
            continue
        nota = M._ler_nota(p)
        if nota and not nota["privado"] and texto in _uma_linha(nota["corpo"]):
            return CONFIRMADO, "uma nota de memória alterada agora contém o texto pedido"
    return REFUTADO, "nenhuma nota de memória alterada depois do pedido contém o texto pedido"


def _conf_silenciar(args, base):
    resta = F.silencio_ativo()
    if resta <= 0:
        return REFUTADO, "o modo foco não está ativo"
    pedido = max(1, min(float(args.get("minutos", 0)), 60 * 24)) * 60
    decorrido = time.time() - base["t0"]
    if pedido - decorrido - FOLGA - 1 <= resta <= pedido + FOLGA:
        return CONFIRMADO, "o modo foco está ativo com o tempo pedido"
    return INCONCLUSIVO, "o modo foco está ativo, mas com um tempo diferente do pedido (outra ordem pode ter mudado)"


def _conf_voltar(args, base):
    return (CONFIRMADO, "o modo foco não está mais ativo") if F.silencio_ativo() <= 0 else (REFUTADO, "o modo foco continua ativo")


def _conf_pedido(args, base):
    if not M.ativo():
        return INCONCLUSIVO, "a memória está desligada: não há onde conferir"
    texto = _uma_linha(args.get("texto", ""))[:300]
    for p in NEU.pedidos():
        if p["texto"] and p["texto"] == texto:
            return CONFIRMADO, "o pedido está em aberto na pasta de pedidos, com o texto pedido"
    return REFUTADO, "nenhum pedido em aberto tem o texto pedido"


VERIFICADORES = {
    "criar_lembrete": (_antes_lembrete, _conf_lembrete),
    "anotar": (_antes_nota, _conf_nota),
    "criar_arquivo": (_antes_arquivo, _conf_arquivo),
    "guardar_memoria": (None, _conf_memoria),
    "silenciar": (None, _conf_silenciar),
    "voltar_a_falar": (None, _conf_voltar),
    "pedir_evolucao": (None, _conf_pedido),
}


def _nivel_zero(nome):
    f = B.FERRAMENTAS.get(nome)
    return bool(f) and not callable(f["nivel"]) and f["nivel"] == 0


def classe(nome):
    """«independente» (olha o estado), «leitura» (só a resposta serve) ou «nenhuma» (não há como conferir)."""
    if nome in VERIFICADORES:
        return "independente"
    return "leitura" if _nivel_zero(nome) else "nenhuma"


def conferivel(nome):
    return classe(nome) != "nenhuma"


def tem_efeito(nome):
    """A ferramenta muda alguma coisa (nível ≥ 1) ou é conferida por estado? Leituras puras não viram tarefa."""
    return nome in VERIFICADORES or (nome in B.FERRAMENTAS and not _nivel_zero(nome))


# ---------------------------------------------------------------- interface
def antes(nome, args):
    """Marca de antes de executar: um dicionário pequeno (números, listas de nomes), seguro para guardar em JSON. Nunca levanta exceção."""
    base = {"t0": time.time()}
    try:
        fase = VERIFICADORES.get(nome, (None, None))[0]
        if fase:
            base.update(fase(args or {}))
    except Exception as e:
        base["sem_marca"] = type(e).__name__
    return base


def depois(nome, args, base, resultado="", erro=False):
    """Confere o efeito. `args` são os argumentos como o corretor os recebeu; `resultado`/`erro` o que a ferramenta respondeu.
    Devolve {veredito, forca, evidencia, em}. A resposta da ferramenta NÃO decide: nas ferramentas com conferência por estado só o estado conta."""
    base = base or {}
    args = args or {}
    if nome in VERIFICADORES:
        if base.get("sem_marca") or "t0" not in base:
            return _v(INCONCLUSIVO, "não consegui tirar a marca de antes da ação, então não dá para saber se o efeito veio dela")
        try:
            veredito, evidencia = VERIFICADORES[nome][1](args, base)
        except Exception as e:
            return _v(INCONCLUSIVO, f"não consegui conferir ({type(e).__name__})")
        if erro and veredito == CONFIRMADO:
            evidencia += " (mesmo com a ferramenta relatando erro)"
        elif not erro and veredito == REFUTADO:
            evidencia += " (a ferramenta tinha respondido que deu certo)"
        return _v(veredito, evidencia)
    if _nivel_zero(nome):
        r = str(resultado or "").strip()
        if erro or r.startswith("Erro"):
            return _v(REFUTADO, "a consulta voltou com erro", DA_RESPOSTA)
        if not r:
            return _v(REFUTADO, "a consulta voltou vazia", DA_RESPOSTA)
        return _v(CONFIRMADO, f"a consulta respondeu ({len(r)} caracteres); só a resposta dela foi usada", DA_RESPOSTA)
    return _v(NAO_VERIFICAVEL, SEM_COMO_CONFERIR.get(nome, "ainda não existe conferência para esta ferramenta"))
