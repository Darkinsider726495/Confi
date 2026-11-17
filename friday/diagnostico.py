"""Confere o ambiente e diz o que falta. Não imprime nenhum segredo: só ✔ / ✖ / •.
  python friday/main.py --diagnostico            verificações locais (rápido)
  python friday/main.py --diagnostico --completo  também testa nuvem, internet e Supabase (usa 1 chamada de IA)
O resultado também fica em diagnostico.txt (pode colar na conversa)."""
import os, sys, time, socket, datetime as dt
import ferramentas as F
import broker as B
import android as A
import internet as W

BASE = os.path.dirname(os.path.abspath(__file__))
SAIDA = []


def linha(simbolo, nome, detalhe=""):
    s = f"{simbolo} {nome}" + (f" — {detalhe}" if detalhe else "")
    SAIDA.append(s)
    print(s, flush=True)
    return simbolo == "✔"


def teste(nome, fn, ok_msg=None):
    try:
        r = fn()
        return linha("✔", nome, ok_msg if ok_msg is not None else (str(r)[:90] if r else ""))
    except Exception as e:
        return linha("✖", nome, str(e)[:140])


def rodar(completo=False):
    SAIDA.clear()
    print(f"FRIDAY — diagnóstico ({dt.datetime.now():%d/%m/%Y %H:%M})\n", flush=True)
    r = []
    # --- ambiente ---
    linha("•", "Python", sys.version.split()[0])
    android = A.disponivel()
    r.append(linha("✔" if android else "•", "Termux:API (celular Android)", "encontrado" if android else "não encontrado: normal fora do celular; no celular instale o app Termux:API e rode 'pkg install termux-api'"))
    if android:
        r.append(teste("Bateria / status do celular", A.status_celular))
        r.append(teste("Voz (alto-falante)", lambda: A.dizer("Teste da FRIDAY. Se você ouviu isso, a voz do Android está funcionando."), "falei uma frase: você ouviu?"))
        r.append(teste("Notificação", lambda: A.notificar_local("FRIDAY", "Teste de notificação", id="friday-teste"), "mostrei uma notificação: ela apareceu?"))
        r.append(teste("Vibração", lambda: A.vibrar(200), "vibrei: você sentiu?"))
        if completo:
            r.append(teste("Localização", A.localizacao))
            r.append(teste("Reconhecimento de voz do Android (diga algo agora)", lambda: A.ouvir_uma_vez() or (_ for _ in ()).throw(RuntimeError("não ouvi nada ou sem permissão do microfone"))))
        else:
            linha("•", "Localização e microfone", "teste com --completo (pede permissões)")
        r.append(teste("Mantém o celular acordado (wake-lock)", lambda: A.wake_lock() or "pedido enviado"))
        boot = os.path.expanduser("~/.termux/boot/friday")
        r.append(linha("✔" if os.path.exists(boot) else "✖", "Início automático (Termux:Boot)", "instalado" if os.path.exists(boot) else "falta rodar termux/instalar-termux.sh"))
        n = len(A.contatos())
        linha("✔" if n else "•", "Contatos permitidos para SMS/ligação", f"{n} cadastrado(s)" if n else "nenhum: defina CONTATOS no .env para ela poder enviar mensagens")
    # --- segurança / configuração ---
    pin = os.getenv("FRIDAY_PIN", "")
    r.append(linha("✔" if len(pin) >= 4 else "✖", "PIN das ações críticas", "definido" if len(pin) >= 4 else "defina FRIDAY_PIN (mín. 4 dígitos); sem ele as ações de nível 3 nunca são liberadas"))
    ok, n = B.verificar_auditoria()
    r.append(linha("✔" if ok else "✖", "Auditoria (cadeia de hashes)", f"{n} eventos íntegros" if ok else f"ADULTERADA após {n} eventos"))
    # --- laboratório de engenharia (MAE) ---
    try:
        import laboratorio as LAB_MAE
        raiz = LAB_MAE._lab_absoluto()
        r.append(linha("✔", "Laboratório de engenharia (.lab/)", f"{LAB_MAE._tamanho_lab() // 1024} KB usados (limite 50 MB), raiz {raiz}; isolado por caminho — sem Docker no Termux, a limitação está documentada"))
        import mae as MAE_D
        e = MAE_D._estado()
        r.append(linha("✔", "Modo de autonomia de engenharia (MAE)", f"modo {e['modo']}" + (f", estado {e['estado']}" if e["estado"] else "") + (f"; última experiência: {e['ultima_experiencia']['resultado']}" if e["ultima_experiencia"] else "")))
    except Exception as e:
        r.append(linha("✖", "Laboratório / MAE", f"não pôde ser conferido: {type(e).__name__}: {e}"))
    provedor = (os.getenv("IA_PROVEDOR") or "anthropic").strip().lower()
    if provedor == "groq":
        tem_chave = bool(os.getenv("GROQ_API_KEY"))
        detalhe = "Groq configurada" if tem_chave else "GROQ_API_KEY ausente; defina a chave no .env ou use IA_MODO=local"
    else:
        tem_chave = bool(os.getenv("ANTHROPIC_API_KEY"))
        detalhe = "Anthropic configurada" if tem_chave else "ANTHROPIC_API_KEY ausente: só o modelo local (sem ferramentas)"
    r.append(linha("✔" if tem_chave else "•", f"API de IA ({provedor})", detalhe))
    # --- IA local (Ollama) ---
    base = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    modelo = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    local_ok = False
    try:
        import requests
        nomes = [m.get("name", "") for m in requests.get(base + "/api/tags", timeout=4).json().get("models", [])]
        local_ok = modelo in nomes or modelo + ":latest" in nomes
        r.append(linha("✔" if local_ok else "✖", "IA local (Ollama)", f"servidor no ar, modelo {modelo} " + ("presente" if local_ok else f"AUSENTE: rode 'ollama pull {modelo}'")))
    except Exception:
        obrigatorio = (os.getenv("IA_MODO") or "").strip().lower() == "local"
        r.append(linha("✖" if obrigatorio else "•", "IA local (Ollama)", "servidor não responde" + ("; IA_MODO=local exige o Ollama no ar" if obrigatorio else ": opcional (reserva sem internet). Veja docs/ANDROID.md, 'IA local'")))
    linha("✔" if os.getenv("NTFY_URL") else "•", "Push (ntfy)", "configurado" if os.getenv("NTFY_URL") else "opcional, não configurado")
    linha("✔" if os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")) else "•", "Leads (Supabase)", "configurado" if os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") else "opcional, não configurado")
    linha("•", "Horário de silêncio", os.getenv("SILENCIO") or "não definido (ela fala a qualquer hora)")
    porta = int(os.getenv("HUD_PORTA", "8080"))
    with socket.socket() as s:
        livre = s.connect_ex(("127.0.0.1", porta)) != 0
    linha("✔" if livre else "•", f"Porta do painel {porta}", "livre" if livre else "em uso (a FRIDAY já está rodando?)")
    # --- nuvem / internet (só com --completo) ---
    if completo:
        def ia():
            import cerebro as C
            C.HIST.clear()
            return C._nuvem([{"role": "user", "content": "Responda só: ok"}], B.Turno())
        r.append(teste("IA na nuvem (1 chamada)", ia))
        if local_ok:
            def gerar():
                import requests
                t0 = time.time()
                x = requests.post(base + "/api/generate", timeout=300, json={"model": modelo, "prompt": "Responda só: ok", "stream": False, "options": {"num_predict": 8}})
                x.raise_for_status()
                return f"respondeu em {time.time() - t0:.0f} s (a 1ª vez inclui carregar o modelo na memória)"
            r.append(teste("IA local responde (1 chamada)", gerar))
        r.append(teste("Pesquisa na internet", lambda: "ok" if "1." in W.pesquisar_web("previsão do tempo São Paulo") else (_ for _ in ()).throw(RuntimeError("sem resultados"))))
        r.append(teste("Leitura de página", lambda: "ok" if len(W.ler_pagina("https://example.com")) > 60 else (_ for _ in ()).throw(RuntimeError("vazio"))))
        if os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")):
            r.append(teste("Leads (Supabase)", lambda: F.leads_novos(24 * 30)))
    else:
        linha("•", "Nuvem, internet e Supabase", "teste com --completo")
    falhas = sum(1 for x in SAIDA if x.startswith("✖"))
    resumo = "\nTudo certo." if not falhas else f"\n{falhas} ponto(s) precisam de atenção (✖)."
    print(resumo)
    SAIDA.append(resumo.strip())
    try:
        with open(os.environ.get("FRIDAY_DIAG_ARQ") or os.path.join(BASE, "..", "diagnostico.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(SAIDA) + "\n")
    except OSError:
        pass
    return 1 if falhas else 0
