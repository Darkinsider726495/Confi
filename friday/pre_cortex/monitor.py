"""Neurônio 9 — Monitoramento.

Olha a SAÚDE do conjunto (nunca o conteúdo dos objetivos): quais trabalhadores respondem, quanto cada módulo demora, quantos erros deu, o que está parado, e diz em que MODO o
sistema deve operar: normal, degradado (um módulo que pode faltar faltou — segue com aviso e pedindo o dono) ou bloqueado (um módulo crítico faltou — nada avança sem ele).

Os módulos NÃO são igualmente confiáveis, e isto aparece em número: cada um tem uma confiança-base DECLARADA aqui (uma suposição de projeto, não uma medida — por exemplo,
regras objetivas valem mais que uma contagem pequena) que cai com a taxa de falha observada e vai a zero se o módulo não responde. O que o monitor devolve é o que o hub
recebeu dos trabalhadores; ele não consulta ninguém sozinho e não age: quem decide é o hub.
"""
from .neuronio import Neuronio

# confiança-base por neurônio: SUPOSIÇÃO DE PROJETO (não medida). O motivo está ao lado, para o painel mostrar.
CONFIANCA_BASE = {
    "percepcao": (0.7, "interpreta por regras; cobre só as frases que as regras conhecem"),
    "contexto": (0.8, "lê fatos direto do corretor e das experiências; as contagens são pequenas"),
    "hipoteses": (0.5, "compara por contagem de poucos registros; não é probabilidade calibrada"),
    "planejamento": (0.6, "gera de um currículo interno, sem fonte externa verificada"),
    "critica": (0.9, "aplica regras objetivas (hash, catálogo, nível, limites); não avalia qualidade pedagógica"),
    "verificador": (0.9, "relê o armazenamento real; inconclusivo onde não há leitor independente"),
    "aprendizagem": (0.5, "lições provisórias com n pequeno; só a contagem acumulada pesa"),
    "monitor": (0.7, "vê o que os trabalhadores relatam; não enxerga o que não relatam"),
}
LENTO_MS = 2000.0           # p95 acima disto (numa janela de até 100 chamadas) marca o módulo como lento


class Monitor(Neuronio):
    nome = "monitor"
    numero = 9
    no_hub = True
    critico = False
    papel = "acompanha a saúde dos módulos e diz em que modo operar"
    responsabilidade = ("Resumir trabalhadores no ar ou fora, tempos de resposta, erros, objetivos parados e módulos lentos; dar a cada módulo uma confiança explicada; "
                        "indicar o modo (normal, degradado, bloqueado). NÃO age, NÃO reinicia nada e NÃO lê o conteúdo dos objetivos.")
    entradas = "saúde dos trabalhadores (como o hub a recebeu) + estados dos objetivos + neurônios esperados"
    saidas = "modo de operação, módulos com confiança e estado, trabalhadores, alertas"
    confianca = "só reflete o que foi relatado; um trabalhador que mente sobre si mesmo não é detectado aqui"

    def acao_avaliar(self, corpo, ctx):
        saude = corpo.get("saude") or {}
        esperados = corpo.get("esperados") or {}
        objetivos = corpo.get("objetivos") or []
        agora = float(corpo.get("agora") or 0)
        trabalhadores, modulos, alertas = {}, {}, []
        por_neuronio = {}
        for w, s in saude.items():
            if not s.get("disponivel"):
                trabalhadores[w] = {"estado": "fora_do_ar", "tipo": s.get("tipo"), "erro": s.get("erro", "")}
                continue
            trabalhadores[w] = {"estado": "no_ar", "tipo": s.get("tipo"), "pid": s.get("pid"), "resposta_ms": s.get("resposta_ms"), "iniciado_em": s.get("iniciado_em")}
            for n, e in (s.get("neuronios") or {}).items():
                por_neuronio[n] = (w, e)
        for n, info in esperados.items():
            base, motivo = CONFIANCA_BASE.get(n, (0.5, "módulo sem confiança-base declarada"))
            dest = info.get("trabalhador")
            if n not in por_neuronio:
                modulos[n] = {"estado": "indisponivel", "critico": bool(info.get("critico")), "trabalhador": dest, "confianca": 0.0, "confianca_base": base, "motivo_da_base": motivo,
                              "explicacao": f"o trabalhador «{dest}» não respondeu: confiança zero, não conto com este módulo"}
                continue
            w, e = por_neuronio[n]
            total = (e.get("concluidas") or 0) + (e.get("falhas") or 0)
            taxa = (e.get("falhas") or 0) / total if total else 0.0
            p95 = e.get("tempo_p95_ms")
            conf = round(base * (1 - taxa), 3)
            estado = "ok"
            if total and taxa >= 0.5:
                estado = "com_erros"
            elif p95 is not None and p95 > LENTO_MS:
                estado = "lento"
            elif taxa > 0:
                estado = "ok_com_falhas_antigas"
            modulos[n] = {"estado": estado, "critico": bool(info.get("critico")), "trabalhador": w, "confianca": conf, "confianca_base": base, "motivo_da_base": motivo,
                          "taxa_de_falha": round(taxa, 3), "chamadas": total, "tempo_medio_ms": e.get("tempo_medio_ms"), "tempo_p95_ms": p95, "em_andamento": e.get("em_andamento", 0),
                          "duplicadas": e.get("duplicadas", 0), "ultimo_erro": e.get("ultimo_erro", ""),
                          "explicacao": f"base {base:.2f} ({motivo})" + (f", reduzida pela taxa de falha {taxa:.0%}" if taxa else "")}
        criticos_fora = sorted(n for n, m in modulos.items() if m["critico"] and m["estado"] == "indisponivel")
        degradaveis_fora = sorted(n for n, m in modulos.items() if not m["critico"] and m["estado"] == "indisponivel")
        lentos = sorted(n for n, m in modulos.items() if m["estado"] == "lento")
        com_erros = sorted(n for n, m in modulos.items() if m["estado"] == "com_erros")
        if criticos_fora:
            modo = "bloqueado"
            alertas.append({"nivel": "grave", "texto": "módulo crítico fora do ar: " + ", ".join(criticos_fora) + ". Nenhum objetivo avança sem ele (a crítica e a verificação não podem ser puladas)."})
        elif degradaveis_fora or com_erros:
            modo = "degradado"
            alertas.append({"nivel": "aviso", "texto": "operando em modo degradado: " + ", ".join(degradaveis_fora + com_erros) + ". O fluxo segue de forma conservadora e pede o dono antes de agir."})
        else:
            modo = "normal"
        for n in lentos:
            alertas.append({"nivel": "aviso", "texto": f"«{n}» está lento (p95 {modulos[n]['tempo_p95_ms']} ms)"})
        for w, t in trabalhadores.items():
            if t["estado"] == "fora_do_ar":
                alertas.append({"nivel": "grave" if any(m["trabalhador"] == w and m["critico"] for m in modulos.values()) else "aviso", "texto": f"trabalhador «{w}» fora do ar: {t.get('erro', '')[:120]}"})
        contagem = {}
        for o in objetivos:
            contagem[o.get("estado")] = contagem.get(o.get("estado"), 0) + 1
        paradas = [o for o in objetivos if o.get("estado") in ("aguardando_autorizacao", "aguardando_confirmacao_do_corretor", "bloqueado", "precisa_do_dono")]
        return {"modo": modo, "modulos": modulos, "trabalhadores": trabalhadores, "alertas": alertas, "criticos_fora": criticos_fora, "degradaveis_fora": degradaveis_fora, "lentos": lentos,
                "objetivos": {"por_estado": contagem, "total": len(objetivos), "parados": [{"id": o.get("id"), "estado": o.get("estado")} for o in paradas][:20]},
                "avaliado_em": agora,
                "aviso": "a confiança-base de cada módulo é uma suposição de projeto declarada no código, não uma medida"}
