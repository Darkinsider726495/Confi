"""MAE — Modo de Autonomia de Engenharia: o ciclo Examinar → Identificar → Hipotetizar → Propor → Modificar →
Testar → Analisar → Registrar, sobre o MÓDULO ALVO dentro do laboratório (laboratorio.py), sozinha, sem pedir
autorização a cada passo — mas com cada operação saindo pelo corretor (nível 0/1, auditada) e cada modificação
precedida de snapshot, com rollback garantido.

  O que o modo É:    o dono inicia («inicia o modo experimental»), pausa, retoma e encerra, por voz ou painel.
  O que ela FAZ:     semeia os arquivos do experimento no laboratório (de verdade: cria, edita, exclui), roda o
                     teste designado, lê a saída de verdade, propõe correção, edita, testa de novo e, se a
                     primeira hipótese não passar, tenta a alternativa; se nenhuma passar, restaura a versão boa
                     e registra a falha. Nada é simulado: os arquivos mudam mesmo, dentro de .lab/.
  O que NUNCA faz:   tocar arquivo fora de LAB_ROOT (o laboratório recusa); mudar o modo sozinha (iniciar/
                     pausar/encerrar são do dono — nem a thread de fundo muda); executar shell livre (só o
                     arquivo de teste designado, sem rede, com tempo limite); promover nada para o projeto real —
                     a versão experimental existe só no laboratório, e o que volta é o rollback.

Limitação de ambiente (documentada): sem Docker (Termux é o alvo), o laboratório do MAE isola diretório e
subprocesso, mas não kernel. Os resultados são registrados no diário de engenharia e na memória episódica quando
ativa. Uma experiência de laboratório nunca promove código: candidatos reais exigem staging, testes independentes,
backup e rollback."""
import os, re, json, time, threading, unicodedata
import broker as B
import laboratorio as LAB

BASE = os.path.dirname(os.path.abspath(__file__))
MODOS = ("encerrado", "ativo", "pausado")
ESTADOS = ("examinar", "identificar", "hipotetizar", "propor", "modificar", "testar", "analisar", "registrar")
ALVO, TESTE = "alvo.py", "teste_alvo.py"      # o experimento desta rodada: semente com defeito controlado
OBJETIVO = "consertar o defeito da semente no laboratório, provando com o teste designado"
INTERVALO = 20                                # s entre um passo e o outro no laço de fundo (passo a passo, visível)
MAX_LOG, MAX_HIST = 40, 12
_trava = threading.RLock()
_e = {"v": None, "arq": None}

# A semente: módulo pequeno com DEFEITO CONTROLADO plantado de propósito (prova prática) e o teste que o verifica.
# Hipótese 1 é ERRADA de propósito — para o ciclo mostrar tentativa → falha → alternativa → sucesso.
SEED = {
    ALVO: 'def dobrar(n):\n    """Dobra um número inteiro."""\n    return n * 2 + 1   # DEFEITO CONTROLADO: devolve o dobro mais um\n\n\ndef versao():\n    return "alvo v1"\n',
    TESTE: '"""Cada caso é um contrato que o módulo tem de cumprir; falha sai com código 1."""\nimport alvo\n\nCASOS = [("dobrar(2)", alvo.dobrar(2), 4), ("dobrar(0)", alvo.dobrar(0), 0),\n         ("dobrar(-3)", alvo.dobrar(-3), -6)]\nfalhas = [f"caso {nome}: esperado {esp}, obtido {obs}" for nome, obs, esp in CASOS if obs != esp]\nif falhas:\n    print("FALHOU: " + "; ".join(falhas))\n    raise SystemExit(1)\nprint("PASSOU")\n',
}
LAB.permitir_teste(SEED[TESTE])                # o único teste que o laboratório aceita rodar (conferido por hash)
DEFEITO = "a função dobrar devolve o valor com um a mais (soma 1 depois de multiplicar por 2)"
HIPOTESES = [
    {"id": "h1", "desc": "o +1 é arredondamento para ímpares: dobrar e, se o número for ímpar, somar 1",
     "acha": "return n * 2 + 1   # DEFEITO CONTROLADO: devolve o dobro mais um",
     "troca": "return n * 2 + (1 if n % 2 else 0)   # tentativa: arredondar ímpares"},          # ERRADA: dobrar(-3) vira -5
    {"id": "h2", "desc": "o +1 é sobra de uma edição anterior: a correção é apenas dobrar, sem soma",
     "acha": "return n * 2 + 1   # DEFEITO CONTROLADO: devolve o dobro mais um",
     "troca": "return n * 2   # correção: apenas dobrar"},                                     # CERTA: todos os casos passam
]


def _arq():
    return os.environ.get("FRIDAY_MAE_ARQ") or os.path.join(BASE, ".mae.json")


def _padrao():
    return {"modo": "encerrado", "estado": "", "problema": "", "hipotese": "", "hipoteses": [], "hip_i": 0,
            "arquivos_analise": [], "arquivos_modificados": [], "arquivos_excluidos": [], "resultado_teste": "",
            "resultado": "", "dif": "", "versao": "", "vid_boa": "", "tentativas": 0, "historico": [],
            "ultima_experiencia": None}


def _estado():
    """Lê o arquivo uma vez e valida TUDO: um estado adulterado ou quebrado nunca vira ação (padrão de autonomia.py)."""
    with _trava:
        arq = _arq()
        if _e["v"] is not None and _e["arq"] == arq:
            return _e["v"]
        v = _padrao()
        try:
            with open(arq, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict):
            if d.get("modo") in MODOS:
                v["modo"] = d["modo"]
            if d.get("estado") in ESTADOS:
                v["estado"] = d["estado"]
            for k in ("problema", "hipotese", "resultado_teste", "resultado", "dif", "versao", "vid_boa"):
                if isinstance(d.get(k), str):
                    v[k] = d[k][:400]
            for k in ("arquivos_analise", "arquivos_modificados", "arquivos_excluidos"):
                if isinstance(d.get(k), list):
                    v[k] = [str(x)[:100] for x in d[k][:20] if isinstance(x, str)]
            if isinstance(d.get("hipoteses"), list):
                v["hipoteses"] = [dict(h) for h in d["hipoteses"][:8] if isinstance(h, dict)]
            if isinstance(d.get("hip_i"), int) and 0 <= d["hip_i"] < 8:
                v["hip_i"] = d["hip_i"]
            if isinstance(d.get("tentativas"), int) and 0 <= d["tentativas"] < 100:
                v["tentativas"] = d["tentativas"]
            if isinstance(d.get("historico"), list):
                v["historico"] = [str(x)[:200] for x in d["historico"][-MAX_LOG:] if isinstance(x, str)]
            if isinstance(d.get("ultima_experiencia"), dict):
                v["ultima_experiencia"] = d["ultima_experiencia"]
        _e.update(v=v, arq=arq)
        return v


def _salvar(v):
    with _trava:
        v["historico"] = v["historico"][-MAX_LOG:]
        d = {k: x for k, x in v.items() if k != "_proposta"}   # proposta é estado de passo: não persiste
        with open(_arq(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        _e.update(v=v, arq=_arq())


def _anotar(v, msg):
    v["historico"].append(f"{time.strftime('%H:%M:%S')} {msg[:150]}")
    v["historico"] = v["historico"][-MAX_LOG:]


def reiniciar():
    """Limpa o estado em memória (os testes usam para começar do zero)."""
    with _trava:
        _e.update(v=None, arq=None)


# ---------------------------------------------------------------- um passo pelo corretor
def _corr(ferramenta, **args):
    """A mesma regra para tudo: a IA propõe, o corretor decide. Devolve (ok, texto)."""
    try:
        with B.uso_interno():              # as ferramentas que escrevem/rodam no laboratório são internas: só este ciclo as usa
            r = B.executar_estruturado(ferramenta, args, B.Turno())
    except Exception as ex:
        return False, f"erro do corretor: {type(ex).__name__}"
    texto = str(r.get("texto", ""))
    return r.get("estado") == "executada" and not texto.lower().startswith("erro"), texto


# ---------------------------------------------------------------- os 8 estados do ciclo
def _examinar(v):
    """Semear o experimento no laboratório — exclusão e recriação REAIS, confinadas, com snapshot e auditoria."""
    excluidos = []
    for nome in (ALVO, TESTE):
        ok, texto = _corr("lab_excluir", rel=nome)
        if ok:
            excluidos.append(nome)
    for nome in (ALVO, TESTE):
        ok, texto = _corr("lab_criar", rel=nome, conteudo=SEED[nome])
        if not ok:
            v["problema"] = f"não consegui semear {nome} no laboratório: {texto[:120]}"
            v["resultado"] = "falha"
            v["estado"] = "registrar"
            _anotar(v, v["problema"])
            return
    v["arquivos_excluidos"], v["arquivos_analise"] = excluidos, [ALVO, TESTE]
    v["arquivos_modificados"], v["problema"], v["hipotese"], v["dif"] = [], "", "", ""
    v["versao"], v["vid_boa"], v["tentativas"], v["resultado"] = "", "", 0, ""
    v["estado"] = "identificar"
    _anotar(v, ("excluí " + ", ".join(excluidos) + "; " if excluidos else "") + "semeei o experimento no laboratório")


def _identificar(v):
    """Roda o teste na semente e lê a saída REAL para achar a função que falhou."""
    ok, texto = _corr("lab_testar", rel=TESTE)
    v["resultado_teste"] = texto[:300]
    if not ok:
        v["problema"] = f"o teste nem roda na semente original: {texto[:160]}"
        v["resultado"] = "falha"
        v["estado"] = "registrar"
        _anotar(v, "a semente original nem roda o teste direito")
        return
    if texto.startswith("PASSOU"):
        v["problema"] = "a semente passou o teste de primeira: não há defeito controlado nesta rodada"
        v["resultado"] = "inconclusivo"
        v["estado"] = "registrar"
        _anotar(v, "a semente passou o teste de primeira")
        return
    m = re.search(r"caso (\w+)\(", texto)
    v["problema"] = DEFEITO if m and m.group(1) == "dobrar" else f"defeito não reconhecido pela saída do teste: {texto[:160]}"
    if m and m.group(1) == "dobrar":
        v["hipoteses"], v["hip_i"] = [dict(h) for h in HIPOTESES], 0
        v["estado"] = "hipotetizar"
        _anotar(v, f"problema identificado: {DEFEITO[:100]}")
    else:
        v["resultado"] = "falha"
        v["estado"] = "registrar"
        _anotar(v, v["problema"][:100])


def _hipotetizar(v):
    if v["hip_i"] >= len(v["hipoteses"]):
        v["estado"] = "analisar"          # acabaram as hipóteses: o analisar decide o rollback
        return
    v["hipotese"] = v["hipoteses"][v["hip_i"]]["desc"]
    v["estado"] = "propor"
    _anotar(v, f"hipótese {v['hip_i'] + 1}: {v['hipotese'][:100]}")


def _propor(v):
    h = v["hipoteses"][v["hip_i"]]
    ok, texto = _corr("lab_ler", rel=ALVO)
    if not ok or h["acha"] not in texto:
        v["hip_i"] += 1
        v["estado"] = "hipotetizar"
        _anotar(v, f"a hipótese {v['hip_i']} não se aplica ao código atual; vou à próxima")
        return
    v["dif"] = ""
    v["_proposta"] = texto.replace(h["acha"], h["troca"], 1)
    v["estado"] = "modificar"


def _modificar(v):
    proposta = v.pop("_proposta", "")
    if not proposta:
        v["estado"] = "hipotetizar"
        return
    ok, texto = _corr("lab_editar", rel=ALVO, novo_conteudo=proposta)
    if not ok:
        v["problema"] = f"a edição no laboratório foi recusada: {texto[:150]}"
        v["resultado"] = "falha"
        v["estado"] = "registrar"
        _anotar(v, "o corretor recusou a edição")
        return
    vid = re.search(r"versão ([0-9a-f]{6,32})", texto)
    if vid:
        if not v["vid_boa"]:
            v["vid_boa"] = vid.group(1)   # a versão de antes da 1ª edição = o ponto de rollback garantido
        v["versao"] = vid.group(1)
    v["dif"] = texto.split("Diferença:\n", 1)[1][:800] if "Diferença:\n" in texto else ""
    if ALVO not in v["arquivos_modificados"]:
        v["arquivos_modificados"].append(ALVO)
    v["tentativas"] += 1
    v["estado"] = "testar"
    _anotar(v, f"editei {ALVO} no laboratório (tentativa {v['tentativas']}, versão {v['versao']})")


def _testar(v):
    ok, texto = _corr("lab_testar", rel=TESTE)
    v["resultado_teste"] = texto[:300]
    v["estado"] = "analisar"
    _anotar(v, f"testei a correção: {texto[:100]}")


def _analisar(v):
    if v["resultado_teste"].startswith("PASSOU"):
        v["resultado"] = "sucesso"
        v["estado"] = "registrar"
        _anotar(v, "a correção fez o teste passar")
        return
    if v["versao"]:                       # desfaz a edição desta tentativa: a próxima hipótese parte do código limpo
        ok, texto = _corr("lab_restaurar", rel=ALVO, vid=v["versao"])
        _anotar(v, "a hipótese não resolveu; desfiz a edição desta tentativa" + ("" if ok else f" ({texto[:60]})"))
    v["hip_i"] += 1
    if v["hip_i"] < len(v["hipoteses"]):
        v["estado"] = "hipotetizar"       # tentar a alternativa: tentativa → falha → próxima
        _anotar(v, "vou tentar a alternativa")
        return
    if v["vid_boa"]:                      # nada funcionou: rollback garantido para a versão de antes do ciclo
        ok, texto = _corr("lab_restaurar", rel=ALVO, vid=v["vid_boa"])
        _anotar(v, f"nada funcionou; restaurei a versão boa ({v['vid_boa']}): {('feito' if ok else texto[:80])}")
    v["resultado"] = "falha"
    v["estado"] = "registrar"


def _registrar(v):
    exp = {"em": time.strftime("%Y-%m-%d %H:%M:%S"), "objetivo": OBJETIVO, "problema": v["problema"],
           "hipotese": v["hipotese"], "tentativas": v["tentativas"], "resultado": v["resultado"] or "inconclusivo",
           "previsao": "a correção proposta faz o teste do laboratório passar",
           "observado": v["resultado_teste"][:200] or "sem rodada de teste",
           "arquivos_modificados": list(v["arquivos_modificados"]), "arquivos_excluidos": list(v["arquivos_excluidos"]),
           "versao": v["versao"], "rollback": v["vid_boa"], "dif": v["dif"][:400]}
    v["ultima_experiencia"] = exp
    v["estado"] = ""
    v["modo"] = "encerrado"
    # A experiência segue dois caminhos append-only: memória episódica (quando ativa)
    # e diário da evolução. Nenhum resultado do laboratório concede permissão para promover.
    try:
        try:
            import experiencias as EXP
        except ImportError:
            from friday import experiencias as EXP
        EXP.registrar_mae(exp)
    except Exception:
        pass
    try:
        try:
            import evolucao as EV
        except ImportError:
            from friday import evolucao as EV
        EV.registrar_experiencia_mae(exp)
    except Exception:
        pass
    try:
        B._audit(ferramenta="mae:ciclo", decisao="registrado", resultado=exp["resultado"])
    except Exception:
        pass
    _anotar(v, f"ciclo {exp['resultado']} ({v['tentativas']} tentativa(s)); experiência registrada")


_PASSO = {"examinar": _examinar, "identificar": _identificar, "hipotetizar": _hipotetizar, "propor": _propor,
          "modificar": _modificar, "testar": _testar, "analisar": _analisar, "registrar": _registrar}


def _passo():
    """Avança UM estado do ciclo (o laço de fundo chama; os testes e o demo chamam direto). Nunca derruba nada."""
    with _trava:
        v = _estado()
        if v["modo"] != "ativo" or not v["estado"]:
            return
        try:
            _PASSO[v["estado"]](v)
        except Exception as ex:
            _anotar(v, f"erro no passo {v['estado']}: {type(ex).__name__}")
            v["resultado"] = "falha"
            v["estado"] = "registrar"
        _salvar(v)


def laco(falar=None, intervalo=INTERVALO):
    """Thread de fundo: o ciclo avança um passo por vez quando o modo está ativo. Nada derruba o núcleo."""
    while True:
        time.sleep(intervalo)
        try:
            v = _estado()
            if v["modo"] == "ativo" and v["estado"]:
                _passo()
                v2 = _estado()
                if falar and v2["modo"] == "encerrado" and v2["ultima_experiencia"]:
                    falar(f"Terminei a experiência no laboratório: {v2['ultima_experiencia']['resultado']} "
                          f"em {v2['tentativas']} tentativa(s).")
        except Exception:
            pass


# ---------------------------------------------------------------- comandos do dono (só ele muda o modo)
def _fold(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


R_LAB = re.compile(r"\b(modo experimental|laboratorio)\b")
R_INICIAR = re.compile(r"\b(iniciar?|inicia|comecar|comeca|rodar|roda|ligar|liga)\b[^.]{0,40}\b(modo experimental|laboratorio)\b")
R_PAUSAR = re.compile(r"\b(pausar|pausa|pausando)\b[^.]{0,40}\b(modo experimental|laboratorio)\b")
R_RETOMAR = re.compile(r"\b(retomar|retoma|continuar|continua)\b[^.]{0,40}\b(modo experimental|laboratorio)\b")
R_ENCERRAR = re.compile(r"\b(encerrar|encerra|terminar|termina|cancelar|cancela|parar|para)\b[^.]{0,40}\b(modo experimental|laboratorio)\b")
R_LOG = re.compile(r"\b(historico|registros|registro|o que voce fez|o que aconteceu)\b[^.]{0,40}\b(modo experimental|laboratorio)\b")


def _iniciar(v):
    if v["modo"] == "ativo":
        return "O modo experimental já está ativo e o ciclo está andando."
    if v["modo"] == "pausado":
        return _retomar(v)
    v.update(modo="ativo", estado="examinar", problema="", hipotese="", hipoteses=[], hip_i=0,
             arquivos_analise=[], arquivos_modificados=[], arquivos_excluidos=[], resultado_teste="",
             resultado="", dif="", versao="", vid_boa="", tentativas=0, ultima_experiencia=None)
    _salvar(v)
    try:
        B._audit(ferramenta="mae:modo", decisao="iniciado")
    except Exception:
        pass
    _anotar(v, "modo experimental iniciado pelo dono")
    _salvar(v)
    return f"Modo experimental iniciado. Objetivo: {OBJETIVO}. O ciclo vai semear o laboratório, achar o defeito e tentar corrigir — passo a passo, tudo no painel."


def _pausar(v):
    if v["modo"] != "ativo":
        return f"O modo experimental não está ativo (está {v['modo']}) — nada a pausar."
    v["modo"] = "pausado"
    _salvar(v)
    try:
        B._audit(ferramenta="mae:modo", decisao="pausado", resultado=v["estado"] or "-")
    except Exception:
        pass
    _anotar(v, f"pausado pelo dono no estado {v['estado'] or '—'}")
    _salvar(v)
    return f"Pausado no estado «{v['estado'] or 'sem ciclo'}». Dizer «retoma o laboratório» continua daí."


def _retomar(v):
    if v["modo"] != "pausado":
        return f"O modo experimental não está pausado (está {v['modo']})."
    v["modo"] = "ativo"
    _salvar(v)
    try:
        B._audit(ferramenta="mae:modo", decisao="retomado")
    except Exception:
        pass
    _anotar(v, "retomado pelo dono")
    _salvar(v)
    return f"Retomado do estado «{v['estado'] or 'sem ciclo'}»."


def _encerrar(v):
    em_ciclo = bool(v["estado"])
    if v["modo"] == "encerrado" and not em_ciclo:
        return "O modo experimental já está encerrado."
    if em_ciclo and v["vid_boa"] and v["arquivos_modificados"]:
        ok, texto = _corr("lab_restaurar", rel=ALVO, vid=v["vid_boa"])
        _anotar(v, f"encerrado pelo dono; rollback: {('feito' if ok else texto[:80])}")
    v.update(modo="encerrado", estado="")
    _salvar(v)
    try:
        B._audit(ferramenta="mae:modo", decisao="encerrado")
    except Exception:
        pass
    _anotar(v, "encerrado pelo dono")
    _salvar(v)
    return "Modo experimental encerrado." + (" A versão experimental voltou para a última versão boa." if em_ciclo else "")


def _status(v):
    if v["modo"] == "encerrado" and not v["estado"] and not v["ultima_experiencia"]:
        return "O laboratório está ocioso: nenhum ciclo rodou ainda. Diga «inicia o modo experimental» para começar."
    partes = [f"Modo {v['modo']}", f"estado: {v['estado'] or 'sem ciclo'}"]
    if v["problema"]:
        partes.append(f"problema: {v['problema'][:120]}")
    if v["hipotese"]:
        partes.append(f"hipótese: {v['hipotese'][:120]}")
    if v["arquivos_modificados"]:
        partes.append(f"modifiquei: {', '.join(v['arquivos_modificados'])}")
    if v["resultado_teste"]:
        partes.append(f"teste: {v['resultado_teste'][:120]}")
    if v["ultima_experiencia"]:
        partes.append(f"última experiência: {v['ultima_experiencia']['resultado']} ({v['ultima_experiencia']['em']})")
    return "; ".join(partes) + "."


def _log(v):
    if not v["historico"]:
        return "Sem registros do laboratório ainda."
    return "Registros do laboratório: " + " | ".join(v["historico"][-5:])


def tratar(texto):
    """Só o dono muda o modo (a thread de fundo NÃO muda). Consultas de estado e registros também aqui."""
    if not isinstance(texto, str) or len(texto) > 200:
        return None
    t = _fold(texto)
    if not R_LAB.search(t):
        return None
    v = _estado()
    if R_INICIAR.search(t):
        return _iniciar(v)
    if R_PAUSAR.search(t):
        return _pausar(v)
    if R_RETOMAR.search(t):
        return _retomar(v)
    if R_ENCERRAR.search(t):
        return _encerrar(v)
    if R_LOG.search(t):
        return _log(v)
    return _status(v)


# ---------------------------------------------------------------- painel (HUD): os 13 itens
def resumo():
    """Tudo que o painel do MAE mostra — só o que aconteceu de verdade, nada inventado."""
    v = _estado()
    return {"modo": v["modo"], "estado": v["estado"] or "sem ciclo", "objetivo": OBJETIVO, "problema": v["problema"],
            "hipotese": v["hipotese"], "hipoteses_n": len(v["hipoteses"]), "hip_i": v["hip_i"],
            "arquivos_analise": v["arquivos_analise"], "arquivos_modificados": v["arquivos_modificados"],
            "arquivos_excluidos": v["arquivos_excluidos"], "teste": TESTE,
            "teste_em_andamento": v["estado"] == "testar", "resultado_teste": v["resultado_teste"],
            "dif": v["dif"], "versao": v["versao"], "rollback": v["vid_boa"], "tentativas": v["tentativas"],
            "ultima_experiencia": v["ultima_experiencia"], "historico": v["historico"][-MAX_HIST:],
            "recursos": LAB.resumo()}


if __name__ == "__main__":
    e = _estado()
    print(json.dumps(resumo(), ensure_ascii=False, indent=1)[:2000])