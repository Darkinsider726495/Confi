"""Catálogo de estratégias do pré-córtex (lado do hub).

As estratégias NÃO são inventadas pelos neurônios: vêm do catálogo do planejador (`planejador.OBJETIVOS`, que é código) e, para pedidos que saem do aparelho, das
ferramentas de nível ≥ 2 do corretor. Um neurônio só escolhe entre elas por nome. O hub é quem traduz «estratégia + conteúdo» nos passos executáveis, de modo que
um plano vindo de outro processo nunca traz ferramenta ou argumento por conta própria.
"""
import broker as B
import criar as K
import experiencias as X
import planejador as PL

from . import conhecimento as CONH
from . import exploracao as EX

TIPOS = ("plano_de_estudo", "registrar_informacao", "acao_externa")
FAMILIA_REGISTRO = ("plano_de_estudo", "registrar_informacao")
# Limites que o próprio código DECLARA (recusa com mensagem). O que o código faz sem declarar (por exemplo, `anotar` cortar o texto) NÃO está aqui: se aparecer,
# aparece como diferença entre o previsto e o observado, e é daí que a experiência nasce.
LIMITES_DECLARADOS = {
    "guardar_memoria": [{"campo": "texto", "maximo": 2000, "unidade": "caracteres", "fonte": "memoria.guardar (recusa texto maior) e planejador.OBJETIVOS"}],
    "criar_arquivo": [{"campo": "conteudo", "maximo": K.MAX_ARQ, "unidade": "bytes", "fonte": "criar.MAX_ARQ"}],
    "anotar": [],
    "anotar_em_partes": [],
}
# Estratégias que o pré-córtex acrescenta ao catálogo do planejador usando SÓ ferramentas que o corretor já tem e na mesma faixa de risco: o nome é código (um dev decide), nenhum aprendizado cria uma.
ESTRATEGIAS_EXTRA = {
    "anotar_em_partes": {"base": "anotar", "descricao": "salvar em várias notas curtas (até %d caracteres cada), uma por parte, em ordem" % CONH.PARTE_MAX,
                         "hipotese": "o texto cabe em várias notas curtas e relê-las em ordem devolve o texto completo",
                         "esperado": "N notas novas no banco, cada uma com «[parte i/N]» e juntas com o texto completo"},
}


def nivel_de(ferramenta, args=None):
    n = B.FERRAMENTAS[ferramenta]["nivel"]
    try:
        return int(n(args or {}) if callable(n) else n)
    except Exception:
        return 2


def candidatas(tipo, params, amb, nivel_max=1):
    """Descritores das estratégias possíveis para o tipo de objetivo, com disponibilidade, nível, limites declarados e perfil de impacto. Sem evidências (isso é do contexto)."""
    saida = []
    if tipo in FAMILIA_REGISTRO:
        for ordem, e in enumerate(PL.OBJETIVOS["registrar_informacao"]["estrategias"]):
            motivo = PL._indisponivel(e, {"texto": "x"}, amb, nivel_max)
            f0 = e["ferramentas"][0]
            try:
                nivel = PL._nivel_da_estrategia(e, {"texto": "x"})
            except Exception:
                nivel = 2                                            # ferramenta ausente ou nível indecifrável: na dúvida, trata como sensível
            saida.append({"id": e["id"], "ferramentas": list(e["ferramentas"]), "descricao": e["descricao"], "hipotese_do_catalogo": e["hipotese"], "esperado_do_catalogo": e["esperado"],
                          "disponivel": motivo is None, "motivo_indisponivel": motivo, "nivel": nivel,
                          "limites_declarados": LIMITES_DECLARADOS.get(f0, []), "perfil": EX.PERFIS.get(f0), "ordem": ordem})
        for nome, x in ESTRATEGIAS_EXTRA.items():
            b = next((c for c in saida if c["id"] == x["base"]), None)
            if b is None:
                continue
            saida.append({"id": nome, "ferramentas": list(b["ferramentas"]), "descricao": x["descricao"], "hipotese_do_catalogo": x["hipotese"], "esperado_do_catalogo": x["esperado"],
                          "disponivel": b["disponivel"], "motivo_indisponivel": b["motivo_indisponivel"], "nivel": b["nivel"], "limites_declarados": LIMITES_DECLARADOS.get(nome, []),
                          "perfil": {**(EX.PERFIS.get(x["base"]) or {}), "custo": 0.3}, "ordem": len(saida), "varias_chamadas": True})
    elif tipo == "acao_externa":
        ferr = (params or {}).get("ferramenta_possivel")
        if ferr and ferr in B.FERRAMENTAS:
            saida.append({"id": ferr, "ferramentas": [ferr], "descricao": f"usar a ferramenta «{ferr}» do corretor", "hipotese_do_catalogo": "a ação acontece depois que o dono autoriza e o corretor confirma",
                          "esperado_do_catalogo": "o corretor executa e registra na auditoria", "disponivel": True, "motivo_indisponivel": None, "nivel": nivel_de(ferr),
                          "limites_declarados": [], "perfil": EX.PERFIS.get(ferr), "ordem": 0})
    return saida


def passos(tipo, estrategia, params):
    """Os passos executáveis de uma estratégia do catálogo, ou levanta ValueError. É a ÚNICA fonte de passos que o hub executa."""
    if tipo in FAMILIA_REGISTRO:
        if estrategia in ESTRATEGIAS_EXTRA:
            texto = str(params.get("texto") or "")
            if not texto.strip():
                raise ValueError("não há texto para dividir em partes")
            partes = CONH.dividir_em_partes(texto)
            n = len(partes)
            return [{"descricao": f"salvar a parte {i}/{n}", "ferramenta": "anotar", "args": {"texto": CONH.marcar_parte(i, n, c)}, **({"depende_de": [f"p{i - 1}"]} if i > 1 else {})}
                    for i, c in enumerate(partes, 1)]
        e = next((x for x in PL.OBJETIVOS["registrar_informacao"]["estrategias"] if x["id"] == estrategia), None)
        if e is None:
            raise ValueError(f"estratégia «{estrategia}» não existe no catálogo")
        return e["montar"]({k: v for k, v in params.items() if k in ("texto", "titulo")})
    if tipo == "acao_externa":
        if estrategia == "enviar_sms" and params.get("contato") and params.get("mensagem"):
            return [{"descricao": "enviar o SMS", "ferramenta": "enviar_sms", "args": {"contato": params["contato"], "texto": params["mensagem"]}}]
        if estrategia == "ligar" and params.get("contato"):
            return [{"descricao": "fazer a ligação", "ferramenta": "ligar", "args": {"contato": params["contato"]}}]
        raise ValueError("faltam dados para montar a ação externa (contato ou mensagem)")
    raise ValueError(f"tipo «{tipo}» sem estratégias")


def texto_esperado(estrategia, passos_):
    """O que a conferência independente deve achar guardado para esta estratégia (antes de qualquer normalização do armazenamento)."""
    if len(passos_) > 1:                                                     # várias partes: o esperado é o texto das partes sem as marcas, em ordem
        return "\n".join(CONH.tirar_marca(p["args"].get("texto", ""))[2] for p in passos_)
    p = passos_[0]
    a = p["args"]
    return a.get("texto") if "texto" in a else a.get("conteudo", "")
