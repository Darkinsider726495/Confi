"""Ações da FRIDAY. O LLM NÃO as chama direto: passam pelo corretor (broker.py), registradas em catalogo.py."""
import os, time, shutil, sqlite3, threading, datetime as dt
from contextlib import closing
import requests
import android as A

DB = os.environ.get("FRIDAY_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "friday.db")
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
_reles = {}


def _db():
    c = sqlite3.connect(DB)
    c.execute("create table if not exists notas(id integer primary key, ts text, texto text)")
    c.execute("create table if not exists lembretes(id integer primary key, quando real, texto text, feito integer default 0)")
    c.execute("create table if not exists uso(dia text primary key, n integer)")
    c.execute("create table if not exists kv(chave text primary key, valor text)")
    return c


def _kv_get(chave, padrao=None):
    with closing(_db()) as c:
        r = c.execute("select valor from kv where chave=?", (chave,)).fetchone()
    return r[0] if r else padrao


def _kv_set(chave, valor):
    with closing(_db()) as c:
        if valor is None:
            c.execute("delete from kv where chave=?", (chave,))
        else:
            c.execute("insert into kv(chave,valor) values(?,?) on conflict(chave) do update set valor=excluded.valor", (chave, str(valor)))
        c.commit()


def tratamento():
    """Como ela chama você (TRATAMENTO no .env). Padrão: chefe."""
    return (os.getenv("TRATAMENTO") or "chefe").strip()[:20] or "chefe"


def usos_hoje():
    with closing(_db()) as c:
        r = c.execute("select n from uso where dia=?", (dt.date.today().isoformat(),)).fetchone()
    return r[0] if r else 0


def contar_llm(limite):
    """Limite diário de chamadas à IA na nuvem (evita custo descontrolado)."""
    dia = dt.date.today().isoformat()
    with closing(_db()) as c:
        c.execute("insert or ignore into uso(dia,n) values(?,0)", (dia,))
        if c.execute("select n from uso where dia=?", (dia,)).fetchone()[0] >= limite:
            return False
        c.execute("update uso set n=n+1 where dia=?", (dia,))
        c.commit()
    return True


def hora_data():
    d = dt.datetime.now()
    return f"{DIAS[d.weekday()]}, {d:%d/%m/%Y}, {d:%H:%M}"


def criar_lembrete(minutos, texto):
    m = max(0.1, min(float(minutos), 60 * 24 * 30))
    with closing(_db()) as c:
        c.execute("insert into lembretes(quando,texto) values(?,?)", (time.time() + m * 60, str(texto)[:200]))
        c.commit()
    return f"Lembrete criado para daqui a {m:g} minutos."


def lembretes_lista():
    with closing(_db()) as c:
        rows = c.execute("select quando,texto from lembretes where feito=0 order by quando").fetchall()
    return [(f"{dt.datetime.fromtimestamp(q):%d/%m %H:%M}", t) for q, t in rows]


def listar_lembretes():
    return "; ".join(f"{h} - {t}" for h, t in lembretes_lista()) or "Nenhum lembrete pendente."


def marca_lembretes():
    """Maior id de lembrete hoje (0 se não há). Quem confere o efeito de criar_lembrete guarda isto ANTES e olha só o que veio depois."""
    with closing(_db()) as c:
        return c.execute("select coalesce(max(id),0) from lembretes").fetchone()[0]


def lembretes_depois(marca):
    """[(quando, texto, feito)] dos lembretes com id maior que `marca` (só leitura)."""
    with closing(_db()) as c:
        return c.execute("select quando,texto,feito from lembretes where id>? order by id", (int(marca),)).fetchall()


def marca_notas():
    with closing(_db()) as c:
        return c.execute("select coalesce(max(id),0) from notas").fetchone()[0]


def notas_depois(marca):
    """[texto] das notas com id maior que `marca` (só leitura)."""
    with closing(_db()) as c:
        return [r[0] for r in c.execute("select texto from notas where id>? order by id", (int(marca),)).fetchall()]


def anotar(texto):
    with closing(_db()) as c:
        c.execute("insert into notas(ts,texto) values(?,?)", (dt.datetime.now().isoformat(timespec="minutes"), str(texto)[:1000]))
        c.commit()
    return "Anotado."


def ler_notas(limite=5):
    with closing(_db()) as c:
        rows = c.execute("select ts,texto from notas order by id desc limit ?", (max(1, min(int(limite), 20)),)).fetchall()
    return "; ".join(f"{t[:10]}: {x}" for t, x in rows) or "Nenhuma nota ainda."


def _temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000
    except Exception:
        return None


def _carga():
    try:
        return f"{os.getloadavg()[0]:.1f}"
    except OSError:  # o Android bloqueia /proc/loadavg
        return "indisponível"


def ram_pct():
    try:
        with open("/proc/meminfo") as f:
            m = dict(l.split(":") for l in f.read().splitlines())
        return 100 - int(m["MemAvailable"].split()[0]) * 100 // int(m["MemTotal"].split()[0])
    except Exception:
        return None


def disco_pct():
    d = shutil.disk_usage("/")
    return d.used * 100 // d.total


def status_sistema():
    t = _temp()
    r = ram_pct()
    ram = f"{r}% de uso" if r is not None else "indisponível"
    temp = f"{t:.0f} graus" if t else "indisponível"
    out = f"Temperatura {temp}; memória {ram}; disco {disco_pct()}% cheio; carga {_carga()}."
    if A.disponivel():
        try:
            out += " " + A.status_celular()
        except Exception:
            pass
    return out


def _leads_desde(iso, limite=10):
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        raise RuntimeError("Supabase não configurado")
    r = requests.get(f"{url}/rest/v1/leads", timeout=10, headers={"apikey": key, "Authorization": f"Bearer {key}"},
                     params={"select": "nome,servico,empresa,created_at", "created_at": f"gte.{iso}", "order": "created_at.asc", "limit": str(limite)})
    r.raise_for_status()
    return r.json()


def leads_novos(horas=24):
    h = max(1, min(float(horas), 24 * 30))
    L = _leads_desde((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=h)).isoformat())
    return "; ".join(f"{x['nome']} ({x.get('servico') or 'sem serviço'})" for x in L) or "Nenhum lead novo nesse período."


def resumo_do_dia():
    p = [f"Hoje é {hora_data()}.", f"Lembretes: {listar_lembretes()}"]
    try:
        p.append("Leads nas últimas 24 horas: " + leads_novos(24))
    except Exception:
        pass
    return " ".join(p + [status_sistema()])


def notificar(texto):
    """Aviso no próprio celular (Android) e/ou push pelo ntfy, conforme o que estiver configurado."""
    feito = []
    if A.disponivel():
        try:
            A.notificar_local("FRIDAY", str(texto)[:400])
            feito.append("celular")
        except Exception:
            pass
    url = os.getenv("NTFY_URL")
    if url:
        h = {"Title": "FRIDAY"}
        if os.getenv("NTFY_TOKEN"):
            h["Authorization"] = "Bearer " + os.getenv("NTFY_TOKEN")
        requests.post(url, data=str(texto)[:500].encode(), headers=h, timeout=10).raise_for_status()
        feito.append("push")
    return "Notificação enviada." if feito else "Push não configurado (NTFY_URL)."


def silencio_ativo():
    """Segundos que faltam do modo foco (0 se não está ativo)."""
    try:
        return max(0, int(float(_kv_get("silencio_ate", "0")) - time.time()))
    except ValueError:
        return 0


def silenciar(minutos):
    m = max(1, min(float(minutos), 60 * 24))
    _kv_set("silencio_ate", time.time() + m * 60)
    return f"Modo foco ativo por {m:g} minutos: avisos só por notificação."


def voltar_a_falar():
    _kv_set("silencio_ate", None)
    return "Voltei a falar normalmente."


def _na_janela(janela, agora=None):
    try:
        a, b = (x.strip() for x in janela.split("-"))
        h = (agora or dt.datetime.now()).strftime("%H:%M")
        return (a <= h < b) if a <= b else (h >= a or h < b)
    except ValueError:
        return False


def janela_descanso():
    """Horário em que ela 'dorme' (DESCANSO=02:00-05:00; vazio ou 'off' desliga). Devolve (inicio, fim) ou None."""
    j = os.environ.get("DESCANSO")
    j = "02:00-05:00" if j is None else j.strip()
    if j.lower() in ("", "off", "0", "nao", "não"):
        return None
    try:
        a, b = (x.strip() for x in j.split("-"))
        for x in (a, b):
            dt.datetime.strptime(x, "%H:%M")
        return a, b
    except ValueError:
        return None


def em_descanso(agora=None):
    """Dentro da janela de descanso: ela fica quieta (só notificação) e é a hora de consolidar a memória."""
    j = janela_descanso()
    return bool(j) and _na_janela(f"{j[0]}-{j[1]}", agora)


def em_silencio(agora=None):
    """Não fala em voz alta (só notifica): dentro de SILENCIO=22:00-07:00, do descanso dela (DESCANSO) ou durante o modo foco."""
    if silencio_ativo() > 0 or em_descanso(agora):
        return True
    j = os.getenv("SILENCIO", "")
    try:
        a, b = (x.strip() for x in j.split("-"))
        h = (agora or dt.datetime.now()).strftime("%H:%M")
        return (a <= h < b) if a <= b else (h >= a or h < b)
    except ValueError:
        return False


def _reles_cfg():
    cfg = {}
    for p in os.getenv("RELES", "").split(","):
        a = p.strip().split(":")
        if len(a) >= 2 and a[1].isdigit():
            cfg[a[0]] = (int(a[1]), int(a[2]) if len(a) > 2 and a[2].isdigit() else 2)
    return cfg


def nivel_rele(nome):
    c = _reles_cfg().get(nome)
    return c[1] if c else 0


def rele(nome, ligar):
    """Relés só em pinos listados em RELES (nome:pino:nivel). Dispositivos de nível 2+ desligam sozinhos (TTL)."""
    c = _reles_cfg().get(nome)
    if not c:
        return f"Não conheço o dispositivo {nome}. Disponíveis: {', '.join(_reles_cfg()) or 'nenhum'}."
    from gpiozero import OutputDevice
    pino, nivel = c
    d = _reles.setdefault(nome, OutputDevice(pino, initial_value=False))
    if not ligar:
        d.off()
        return f"{nome} desligado."
    d.on()
    ttl = int(os.getenv("RELE_TTL_CRITICO", "600")) if nivel >= 2 else int(os.getenv("RELE_TTL", "0"))
    if ttl > 0:
        t = threading.Timer(ttl, d.off)
        t.daemon = True
        t.start()
        return f"{nome} ligado por {ttl} segundos."
    return f"{nome} ligado."


HEARTBEAT = os.environ.get("FRIDAY_HEARTBEAT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".heartbeat")
GANCHOS = []  # funções sem argumentos que devolvem uma lista de frases para a FRIDAY falar por iniciativa própria
_bat = {"prox": 0.0}


def gancho_bateria():
    """Avisa quando a bateria do celular está baixa e fora do carregador."""
    if time.time() < _bat["prox"]:
        return []
    b = A.bateria()
    p = b.get("percentage", 100)
    if b.get("plugged", "UNPLUGGED") == "UNPLUGGED" and p <= 15:
        _bat["prox"] = time.time() + (900 if p <= 5 else 1800)
        return [f"Bateria do celular em {p} por cento. Coloque para carregar."]
    _bat["prox"] = time.time() + 120
    return []


def _batida():
    try:
        with open(HEARTBEAT, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def proativo(falar):
    """Fala sozinha: lembretes, leads novos (5 min), alerta de temperatura e briefing matinal (HORA_BRIEFING)."""
    ult = dt.datetime.now(dt.timezone.utc)
    prox = prox_t = 0
    brief_dia = None
    while True:
        time.sleep(5)
        _batida()
        for g in list(GANCHOS):
            try:
                for m in g():
                    falar(m)
            except Exception:
                pass
        try:
            agora = time.time()
            hoje = dt.date.today()
            with closing(_db()) as c:
                vencidos = c.execute("select id,texto from lembretes where feito=0 and quando<=?", (agora,)).fetchall()
                for i, _ in vencidos:
                    c.execute("update lembretes set feito=1 where id=?", (i,))
                c.commit()
            for _, t in vencidos:
                falar(f"Lembrete: {t}")
            hb = os.getenv("HORA_BRIEFING", "08:00")
            if hb and dt.datetime.now().strftime("%H:%M") == hb and brief_dia != hoje:
                brief_dia = hoje
                import telemetria as T
                falar(T.briefing())
            t = _temp()
            if t and t > 80 and agora >= prox_t:
                prox_t = agora + 600
                falar(f"Atenção: temperatura em {t:.0f} graus.")
            if os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")) and agora >= prox:
                prox = agora + 300
                novos = _leads_desde(ult.isoformat())
                ult = dt.datetime.now(dt.timezone.utc)
                for n in novos:
                    falar(f"Novo lead: {n['nome']}, interessado em {n.get('servico') or 'um serviço'}.")
        except Exception:
            pass
