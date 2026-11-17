"""Telemetria do painel, clima, briefing falado e relatório de sistemas.
Tudo local, exceto o clima (Open-Meteo, API pública sem chave) e os leads (Supabase, se configurado)."""
import os, time, threading, datetime as dt
import requests
import ferramentas as F
import android as A
import broker as B

INICIO = time.time()
MODO_IA = {"v": "—"}  # o cérebro atualiza: "nuvem", "local" ou "sem chave"
PAINEL = {"metricas": {}, "clima": None, "leads": None}
_ult = {"metricas": 0.0, "clima": 0.0, "leads": 0.0}
_TTL = {"metricas": 15, "clima": 900, "leads": 300}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _desc_clima(c):
    if c == 0: return "céu limpo"
    if c in (1, 2): return "poucas nuvens"
    if c == 3: return "nublado"
    if c in (45, 48): return "neblina"
    if 51 <= c <= 57: return "garoa"
    if 61 <= c <= 67: return "chuva"
    if 71 <= c <= 77: return "neve"
    if 80 <= c <= 82: return "pancadas de chuva"
    if c in (85, 86): return "pancadas de neve"
    if c >= 95: return "trovoada"
    return "tempo variável"


def clima():
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": float(os.getenv("CLIMA_LAT", "-23.55")), "longitude": float(os.getenv("CLIMA_LON", "-46.63")),
        "current": "temperature_2m,weather_code", "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": os.getenv("TZ", "America/Sao_Paulo"), "forecast_days": 1})
    r.raise_for_status()
    d = r.json()
    return {"local": os.getenv("CLIMA_LOCAL", "São Paulo"), "temp": round(d["current"]["temperature_2m"]),
            "descricao": _desc_clima(d["current"]["weather_code"]), "max": round(d["daily"]["temperature_2m_max"][0]),
            "min": round(d["daily"]["temperature_2m_min"][0]), "chuva": int(d["daily"]["precipitation_probability_max"][0] or 0)}


def clima_texto():
    c = clima()
    return (f"{c['local']}: {c['temp']} graus, {c['descricao']}. Máxima de {c['max']} e mínima de {c['min']}, "
            f"chance de chuva de {c['chuva']} por cento.")


def metricas():
    m = {"ram": F.ram_pct(), "disco": F.disco_pct(), "temp": F._temp(), "bateria": None, "carregando": None,
         "ia_usos": F.usos_hoje(), "ia_limite": int(os.getenv("LIMITE_DIARIO", "200") or 200)}
    if A.disponivel():
        try:
            b = A.bateria()
            m["bateria"] = b.get("percentage")
            m["carregando"] = b.get("plugged", "UNPLUGGED") != "UNPLUGGED"
        except Exception:
            pass
    return m


def leads_painel():
    """Quantidade e nomes dos leads das últimas 24 h (None se o Supabase não está configurado)."""
    if not (os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))):
        return None
    L = F._leads_desde((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).isoformat(), limite=50)
    return {"n": len(L), "nomes": [str(x.get("nome", ""))[:40] for x in L[-3:]]}


def atualizar_painel(forcar=False):
    """Atualiza o cache que o painel lê (rodado em segundo plano: o painel nunca espera a rede)."""
    agora = time.time()
    for chave, fn in (("metricas", metricas), ("clima", clima), ("leads", leads_painel)):
        if forcar or agora - _ult[chave] >= _TTL[chave]:
            try:
                PAINEL[chave] = fn()
                _ult[chave] = agora
            except Exception:
                _ult[chave] = agora - _TTL[chave] + 60  # tenta de novo em 1 minuto; mantém o último valor bom


def laco_painel():
    while True:
        atualizar_painel()
        time.sleep(5)


# ---------- fala ----------
def hora_falada(d=None):
    d = d or dt.datetime.now()
    h, m = d.hour, d.minute
    if m == 0 and h in (0, 12):
        return "meia-noite" if h == 0 else "meio-dia"
    base = "meia-noite" if h == 0 else f"{h} {'hora' if h == 1 else 'horas'}"
    return f"{base} em ponto" if m == 0 else f"{base} e {m} {'minuto' if m == 1 else 'minutos'}"


def saudacao(d=None):
    h = (d or dt.datetime.now()).hour
    return "Boa madrugada" if h < 5 else "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def _uptime(seg):
    seg = int(seg)
    if seg < 90:
        return f"{seg} segundos"
    if seg < 5400:
        return f"{seg // 60} minutos"
    h, m = seg // 3600, seg % 3600 // 60
    if h >= 48:
        return f"{h // 24} dias"
    return f"{h} horas" + (f" e {m} minutos" if m else "")


def briefing(agora=None):
    """Briefing falado, sem usar a IA: hora, clima, agenda, leads e saúde dos sistemas."""
    agora = agora or dt.datetime.now()
    t = F.tratamento()
    p = [f"{saudacao(agora)}, {t}. São {hora_falada(agora)} de {F.DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]}."]
    c = PAINEL.get("clima")
    if c is None:
        try:
            c = clima()
        except Exception:
            c = None
    if c:
        p.append(f"Lá fora, {c['temp']} graus e {c['descricao']}; máxima de {c['max']}, mínima de {c['min']}"
                 + (f", com {c['chuva']} por cento de chance de chuva." if c["chuva"] >= 30 else "."))
    lem = F.lembretes_lista()
    if lem:
        p.append(f"Você tem {len(lem)} {'lembrete' if len(lem) == 1 else 'lembretes'}: " + "; ".join(f"{h}, {x}" for h, x in lem[:3]) + ".")
    else:
        p.append("Sua agenda está livre, sem lembretes pendentes.")
    try:
        L = leads_painel()
    except Exception:
        L = None
    if L is not None:
        if L["n"]:
            p.append(f"{L['n']} {'lead novo' if L['n'] == 1 else 'leads novos'} nas últimas 24 horas: {', '.join(L['nomes'])}.")
        else:
            p.append("Nenhum lead novo nas últimas 24 horas.")
    m = metricas()
    alertas = []
    if m["bateria"] is not None:
        p.append(f"Bateria do celular em {m['bateria']} por cento" + (", carregando." if m["carregando"] else "."))
        if m["bateria"] <= 20 and not m["carregando"]:
            alertas.append("bateria baixa")
    if (m["disco"] or 0) >= 90:
        alertas.append("disco quase cheio")
    if not B.verificar_auditoria()[0]:
        alertas.append("a trilha de auditoria falhou na verificação de integridade")
    p.append("Atenção: " + ", ".join(alertas) + "." if alertas else "Todos os sistemas operacionais.")
    return " ".join(p)


def relatorio():
    t = F.tratamento()
    ok, n = B.verificar_auditoria()
    m = metricas()
    p = [f"Relatório de sistemas, {t}.", f"Núcleo online há {_uptime(time.time() - INICIO)}.",
         f"Corretor ativo com {len(B.FERRAMENTAS)} ferramentas; auditoria {'íntegra' if ok else 'COMPROMETIDA'}, com {n} eventos registrados."]
    if m["bateria"] is not None:
        p.append(f"Bateria em {m['bateria']} por cento" + (", carregando." if m["carregando"] else "."))
    if m["ram"] is not None:
        p.append(f"Memória em {m['ram']} por cento, disco em {m['disco']} por cento.")
    p.append(f"Inteligência: modo {MODO_IA['v']}, {F.usos_hoje()} de {os.getenv('LIMITE_DIARIO', '200')} chamadas hoje.")
    if F.silencio_ativo():
        p.append(f"Modo foco ativo por mais {F.silencio_ativo() // 60 + 1} minutos.")
    p.append("Sem alertas." if ok else "Atenção: verifique a auditoria.")
    return " ".join(p)
