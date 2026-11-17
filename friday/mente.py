"""Números REAIS das partes da mente dela para a tela 3D (/mente). Só leitura; nunca expõe chave, frase ou conteúdo de nota.

Cada camada da tela corresponde a um módulo de verdade:
  sentidos → pré-córtex (registro) → significado (Transformer + adaptador dela) → memória (neurônios e sinapses do cofre)
  → rotina (GRU) → núcleo (nove neurônios distribuídos) → corretor (decide o que pode) → saída (voz e ações).
"""
import os


def _sig():
    try:
        import significado as SIG
        m = SIG.motor()
        return {"motor": m or "desligado", "limiar": round(float(SIG.limiar()), 2) if m else None,
                "camadas": 12 if m == "transformer" else 1, "indexadas": len(SIG._idx.get("itens", {}))}
    except Exception:
        return {"motor": "desligado", "limiar": None, "camadas": 0, "indexadas": 0}


def _rotina():
    try:
        import rotina as R
        m = R.carregar()
        if not m:
            return {"treinada": False, "status": R.treinar_status(), "oculto": R.OCULTO, "janela": R.JANELA}
        _, meta = m
        prev = [{"rotulo": R._nome(r), "chance": c} for r, c in R.previsao()[:3]] if meta.get("confiavel") else []
        return {"treinada": True, "confiavel": bool(meta.get("confiavel")), "dias": meta.get("dias"), "oculto": R.OCULTO, "janela": R.JANELA,
                "rotulos": [R._nome(r) for r in meta.get("rotulos", [])], "previsao": prev,
                "erro_rede": meta.get("perda_validacao"), "erro_simples": meta.get("perda_jeito_simples")}
    except Exception:
        return {"treinada": False, "status": "indisponível", "oculto": 24, "janela": 24}


def _llm():
    prov = (os.getenv("IA_PROVEDOR") or "anthropic").strip().lower()
    if prov == "groq":
        try:
            import provedor_groq as G
            modelo = os.getenv("GROQ_MODEL") or G.DEFAULT_MODEL
        except Exception:
            modelo = os.getenv("GROQ_MODEL") or "groq"
    else:
        modelo = os.getenv("LLM_MODEL") or prov
    return {"provedor": prov, "modelo": str(modelo)[:60], "modo": (os.getenv("IA_MODO") or "auto").strip().lower()}


def _fila():
    try:
        import assimilacao as A
        return A._FILA.qsize()
    except Exception:
        return 0


def resumo():
    return {"ok": True, "significado": _sig(), "rotina": _rotina(), "llm": _llm(), "fila_assimilacao": _fila()}
