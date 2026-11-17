"""Neurônio 5 — Avaliação crítica e segurança.

Revisa um plano como um auditor que NÃO foi quem o fez (roda em outro processo, no modo distribuído) e responde: aprovado, devolvido (para revisão, com os motivos) ou
rejeitado (sem conserto neste plano). Confere: se o plano está completo; se o hash bate (nada foi mudado depois de assinado); se as ferramentas existem e batem com a estratégia do
catálogo; os EFEITOS de cada ação (nível, saída do aparelho, reversibilidade); se alguma hipótese foi promovida a fato; se o conteúdo é sensível; se cabe nos limites declarados;
se repete uma estratégia que já falhou; se os critérios de sucesso cobrem o que foi pedido; se toda ação tem verificação independente; se as dependências fecham.

O veredito carrega o hash do plano que foi revisado: o hub só executa um plano cujo hash seja o do veredito de aprovação. O planejador não tem como desligar este módulo — não existe
configuração para isso (config.py) e o hub não avança sem o veredito. Esta crítica NÃO concede permissão: quando algo exige o dono, ela só registra a exigência.
Este módulo não importa o corretor nem as tarefas: recebe do hub o catálogo de ferramentas e os passos derivados da estratégia, que o planejador não controla.
"""
from . import contrato as C
from .neuronio import Neuronio

CAMPOS_TEXTO = ("objetivo", "resultado_esperado")
CAMPOS_LISTA = ("etapas", "criterios_de_sucesso", "condicoes_para_interromper", "criterios_de_verificacao")


class Critica(Neuronio):
    nome = "critica"
    numero = 5
    papel = "revisa o plano de forma independente e pode rejeitá-lo ou devolvê-lo"
    responsabilidade = ("Verificar completude, integridade (hash), catálogo de ferramentas, efeitos e reversibilidade, hipótese tratada como fato, conteúdo sensível, limites declarados, repetição, "
                        "cobertura dos critérios, verificação independente e dependências. Pode rejeitar ou devolver. NÃO concede autorização e NÃO executa.")
    entradas = "plano + passos derivados do catálogo + catálogo de ferramentas + histórico de tentativas + origem do objetivo"
    saidas = "veredito (aprovado | devolvido | rejeitado) preso ao hash do plano, com checagens e exigências de autorização"
    confianca = "alta para as regras objetivas (hash, catálogo, nível); não avalia a qualidade pedagógica do conteúdo"

    def acao_revisar(self, corpo, ctx):
        plano = corpo.get("plano")
        if not isinstance(plano, dict):
            raise C.ErroNeuronio("entrada_invalida", "falta o plano")
        passos = corpo.get("passos_derivados")
        cat = corpo.get("catalogo_ferramentas") or {}
        interp = corpo.get("interpretacao") or {}
        hist = corpo.get("tentativas_anteriores") or []
        lim = corpo.get("limites_declarados") or []
        origem = corpo.get("origem_objetivo") or {}
        ciclo = corpo.get("limites_de_ciclo") or {}
        checagens, exigencias = [], []

        def regra(id_, ok, detalhe, efeito="devolve"):
            checagens.append({"regra": id_, "ok": bool(ok), "efeito_se_falhar": efeito, "detalhe": detalhe})

        # R1 completude
        faltam = [c for c in CAMPOS_TEXTO if not (isinstance(plano.get(c), str) and plano[c].strip())]
        faltam += [c for c in CAMPOS_LISTA if not (isinstance(plano.get(c), list) and plano[c])]
        if not isinstance(plano.get("estado_inicial"), dict):
            faltam.append("estado_inicial")
        for c in ("riscos_e_incertezas", "alternativas"):
            if not isinstance(plano.get(c), list):
                faltam.append(c)
        if plano.get("executavel") and not plano.get("riscos_e_incertezas"):
            faltam.append("riscos_e_incertezas")
        sem_just = [e.get("id") for e in plano.get("etapas") or [] if not (isinstance(e, dict) and e.get("justificativa") and e.get("resultado_esperado"))]
        regra("R1_completude", not faltam and not sem_just, "dez campos presentes" if not faltam and not sem_just else f"faltam: {', '.join(faltam)}; etapas sem justificativa/resultado: {', '.join(map(str, sem_just))}")
        # R2 integridade
        recalc = C.hash_plano(plano)
        regra("R2_integridade", plano.get("hash") == recalc, "o hash confere: o plano não mudou depois de assinado" if plano.get("hash") == recalc else "o hash NÃO confere: o plano foi alterado depois de assinado", "rejeita")
        # R9 ciclo
        maxv = int(ciclo.get("max_replanos", 3)) + 1
        regra("R9_limite_de_replanos", int(plano.get("versao") or 0) <= maxv, f"versão {plano.get('versao')} de no máximo {maxv}", "rejeita")
        # R14 coerência com a comparação
        esc = plano.get("escolha") or {}
        regra("R14_estrategia_vem_da_comparacao", plano.get("estrategia") == esc.get("escolhida") or not plano.get("executavel"),
              f"estratégia {plano.get('estrategia')!r} {'é' if plano.get('estrategia') == esc.get('escolhida') else 'NÃO é'} a que a comparação de hipóteses colocou na frente ({esc.get('escolhida')!r})")
        # R3 catálogo e ferramentas
        efeitos = []
        if plano.get("executavel"):
            execs = [e for e in plano.get("etapas") or [] if isinstance(e, dict) and e.get("tipo") == "execucao"]
            tools_plano = [t for e in execs for t in (e.get("ferramentas") or [e.get("ferramenta")])]
            tools_derivadas = [p.get("ferramenta") for p in passos or []]
            ok3 = bool(passos) and tools_plano == tools_derivadas and all(t in cat for t in tools_derivadas)
            regra("R3_catalogo", ok3, "as ferramentas do plano são as da estratégia do catálogo e existem" if ok3 else f"plano cita {tools_plano}, o catálogo deriva {tools_derivadas}", "rejeita")
            proibida = [t for t in tools_derivadas if t in cat and int(cat[t].get("nivel", 2)) >= 4]
            regra("R3b_nivel_proibido", not proibida, "nenhuma ferramenta de nível 4" if not proibida else f"nível 4 (não existe): {proibida}", "rejeita")
            # R4 efeitos
            for p in passos or []:
                info = cat.get(p.get("ferramenta"), {})
                perfil = info.get("perfil") or {}
                nivel = int(info.get("nivel", 2))
                efeitos.append({"ferramenta": p.get("ferramenta"), "nivel": nivel, "externo": bool(perfil.get("externo", True)), "reversibilidade": perfil.get("reversibilidade", "desconhecida"),
                                "impacto": perfil.get("impacto"), "escopo": perfil.get("escopo"), "descricao": perfil.get("descricao", "efeito desconhecido")})
                if nivel >= 2:
                    exigencias.append({"motivo": f"«{p.get('ferramenta')}» é de nível {nivel}: o corretor exige confirmação do dono", "fonte": "corretor"})
                if perfil.get("externo", True):
                    exigencias.append({"motivo": f"«{p.get('ferramenta')}» alcança fora do aparelho ou tem efeito desconhecido", "fonte": "exploracao.PERFIS"})
                if perfil.get("reversibilidade") == "irreversivel":
                    exigencias.append({"motivo": f"o efeito de «{p.get('ferramenta')}» não pode ser desfeito", "fonte": "exploracao.PERFIS"})
        if (interp.get("efeitos") or {}).get("externo"):
            exigencias.append({"motivo": "o pedido envolve ação externa: " + ", ".join((interp.get("efeitos") or {}).get("categorias") or []), "fonte": "percepção"})
        if origem.get("origem") == "sugerido_pelo_sistema" and not origem.get("aceito"):
            exigencias.append({"motivo": "o objetivo foi sugerido pelo sistema e o dono ainda não o aceitou", "fonte": "registro do objetivo"})
        regra("R4_efeitos_e_autorizacao", True, ("exige o dono: " + "; ".join(sorted({e['motivo'] for e in exigencias}))) if exigencias else "ações locais, de baixo impacto, dentro do que o dono pediu: o próprio pedido autoriza")
        # R5 hipótese não vira fato
        mal = [f for f in (plano.get("estado_inicial") or {}).get("fatos") or [] if not (isinstance(f, dict) and f.get("tipo") == "fato" and f.get("origem"))]
        regra("R5_hipotese_nao_vira_fato", not mal, "todo «fato» do estado inicial é tipado como fato e tem origem" if not mal else f"{len(mal)} item(ns) listado(s) como fato sem ser fato observado ou sem origem")
        # R6 conteúdo sensível
        texto = (plano.get("parametros_da_estrategia") or {}).get("texto") or ""
        sens = False
        if texto:
            import memoria as _m
            sens = _m.sensivel(texto)
        regra("R6_conteudo_sensivel", not sens, "o conteúdo não parece senha, cartão ou documento" if not sens else "o conteúdo parece dado sensível: não guardo", "rejeita")
        # R7 limites declarados
        estoura = []
        if plano.get("executavel") and texto:
            for d in lim:
                uso = len(texto.encode("utf-8")) if d.get("unidade") == "bytes" else len(texto)
                if uso > d.get("maximo", 10**9):
                    estoura.append(f"{uso} {d.get('unidade')} > {d.get('maximo')}")
        regra("R7_limites_declarados", not estoura, "o conteúdo cabe nos limites declarados da estratégia" if not estoura else "excede o limite declarado: " + "; ".join(estoura))
        # R8 repetição
        rep = [h for h in hist if h.get("estrategia") == plano.get("estrategia") and h.get("resultado") != "sucesso"]
        regra("R8_sem_repeticao", not rep, "a estratégia não foi tentada antes neste objetivo" if not rep else f"«{plano.get('estrategia')}» já foi tentada neste objetivo e não cumpriu: repetir não traz informação")
        # R10 cobertura dos critérios
        tipos_crit = {c.get("tipo") for c in plano.get("criterios_de_sucesso") or [] if isinstance(c, dict)}
        pedidos = {"semanas": "semanas" in (interp.get("parametros") or {}), "limite_diario": "minutos_dia" in (interp.get("parametros") or {})}
        sem_cobertura = [k for k, quer in pedidos.items() if quer and interp.get("tipo_objetivo") == "plano_de_estudo" and k not in tipos_crit]
        regra("R10_criterios_cobrem_o_pedido", not sem_cobertura, "os critérios cobrem semanas e limite diário pedidos" if not sem_cobertura else f"o pedido tem restrição sem critério de sucesso: {sem_cobertura}")
        # R11 verificação independente
        etapas = [e for e in plano.get("etapas") or [] if isinstance(e, dict)]
        ids_verif = {e["id"]: e for e in etapas if e.get("tipo") == "verificacao"}
        todas_verificadas = all(any(d == ex["id"] for v in ids_verif.values() for d in v.get("depende_de") or []) for ex in etapas if ex.get("tipo") == "execucao")
        indep = any(isinstance(v, dict) and v.get("fonte_independente") for v in plano.get("criterios_de_verificacao") or [])
        regra("R11_verificacao_independente", todas_verificadas and indep, "toda ação tem uma etapa de verificação com fonte independente" if todas_verificadas and indep else "há ação sem verificação independente: uma função não declara o próprio sucesso")
        # R12 dependências
        ids = [e.get("id") for e in etapas]
        ok12 = len(set(ids)) == len(ids)
        vistos = set()
        for e in etapas:
            for d in e.get("depende_de") or []:
                if d not in vistos:
                    ok12 = False
            vistos.add(e.get("id"))
        regra("R12_dependencias", ok12, "dependências existem e só apontam para etapas anteriores" if ok12 else "há dependência ausente, repetida ou adiante (ciclo possível)")
        # veredito
        falhas = [c for c in checagens if not c["ok"]]
        if any(c["efeito_se_falhar"] == "rejeita" for c in falhas):
            veredito = "rejeitado"
        elif falhas:
            veredito = "devolvido"
        else:
            veredito = "aprovado"
        unicas = list({e["motivo"]: e for e in exigencias}.values())
        return {"veredito": veredito, "plano_hash": plano.get("hash"), "hash_recalculado": recalc, "versao": plano.get("versao"), "checagens": checagens,
                "motivos": [{"regra": c["regra"], "texto": c["detalhe"], "efeito": c["efeito_se_falhar"]} for c in falhas], "exigencias_de_autorizacao": unicas,
                "autorizacao_necessaria": bool(unicas), "efeitos_avaliados": efeitos,
                "resumo": {"aprovado": "plano aprovado" + (" — mas exige a autorização do dono" if unicas else ""), "devolvido": "plano devolvido para revisão: " + "; ".join(c["detalhe"] for c in falhas),
                           "rejeitado": "plano rejeitado: " + "; ".join(c["detalhe"] for c in falhas if c["efeito_se_falhar"] == "rejeita")}[veredito]}
