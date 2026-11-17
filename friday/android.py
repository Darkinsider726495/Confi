"""Ponte com o Android via Termux:API (apps Termux e Termux:API, ambos da F-Droid).
Nada aqui usa shell: os comandos são listas de argumentos, e o texto vai pela entrada padrão, nunca na linha de comando.
Tudo passa por _run(), que os testes substituem por comandos simulados."""
import os, re, json, time, shutil, tempfile, subprocess, unicodedata


def disponivel():
    return shutil.which("termux-battery-status") is not None


def ativo():
    """Registra as ferramentas do celular se o Termux:API existe (ou se forçado por FRIDAY_PLATAFORMA=android)."""
    return disponivel() or os.getenv("FRIDAY_PLATAFORMA") == "android"


def _run(args, entrada=None, timeout=15):
    try:
        p = subprocess.run(args, input=entrada, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL if entrada is None else None)
    except FileNotFoundError:
        raise RuntimeError(f"{args[0]} não encontrado: instale o app Termux:API e rode 'pkg install termux-api'.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{args[0]} não respondeu em {timeout}s. O app Termux:API está instalado e com permissão?")
    if p.returncode != 0:
        raise RuntimeError(f"{args[0]} falhou: {(p.stderr or p.stdout).strip()[:200]}")
    return p.stdout


def _json(args, timeout=15):
    out = _run(args, timeout=timeout).strip()
    try:
        return json.loads(out) if out else {}
    except ValueError:
        raise RuntimeError(f"{args[0]} devolveu algo inesperado")


# ---------- leitura ----------
def bateria():
    return _json(["termux-battery-status"])


def status_celular():
    b = bateria()
    estado = {"CHARGING": "carregando", "DISCHARGING": "descarregando", "FULL": "cheia", "NOT_CHARGING": "conectada, sem carregar"}.get(b.get("status"), "estado desconhecido")
    s = f"Bateria {b.get('percentage')}%, {estado}, {b.get('temperature', '?')} graus."
    try:
        w = _json(["termux-wifi-connectioninfo"])
        s += " Wi-Fi conectado." if w.get("supplicant_state") == "COMPLETED" or w.get("ssid") not in (None, "", "<unknown ssid>") else " Sem Wi-Fi."
    except RuntimeError:
        pass
    return s


def localizacao():
    d = _json(["termux-location", "-p", "network", "-r", "once"], timeout=40)
    if "latitude" not in d:
        raise RuntimeError("não consegui a localização (permissão de localização do Termux:API ligada?)")
    return f"Latitude {d['latitude']:.5f}, longitude {d['longitude']:.5f}, precisão de {d.get('accuracy', 0):.0f} metros."


# ---------- ações no aparelho ----------
def lanterna(ligar):
    _run(["termux-torch", "on" if ligar else "off"])
    return "Lanterna ligada." if ligar else "Lanterna desligada."


def vibrar(ms=300):
    ms = max(50, min(int(ms), 2000))
    _run(["termux-vibrate", "-d", str(ms), "-f"])
    return "Vibrei."


def dizer(texto, silencioso=False):
    """Fala pelo alto-falante do celular (TTS do Android). Em horário de silêncio, só notifica."""
    texto = str(texto).strip()[:1500]
    if not texto:
        return
    if silencioso:
        notificar_local("FRIDAY", texto)
    else:
        a = ["termux-tts-speak", "-l", "pt", "-n", "BR"]
        for var, flag in (("TTS_VELOCIDADE", "-r"), ("TTS_TOM", "-p")):  # voz mais grave e pausada soa mais "JARVIS"
            try:
                v = float(os.getenv(var, ""))
                a += [flag, f"{max(0.3, min(v, 3.0)):g}"]
            except ValueError:
                pass
        # canal de MÍDIA por padrão: o padrão do termux-tts-speak é o de notificação, que fica mudo com o celular no silencioso/vibrar
        motor = os.getenv("TTS_MOTOR", "").strip()           # outro motor de voz instalado no Android (veja: termux-tts-engines)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+", motor):
            a += ["-e", motor]
        canal = os.getenv("TTS_CANAL", "MUSIC").strip().upper()
        if canal in ("MUSIC", "NOTIFICATION", "ALARM", "RING", "SYSTEM", "VOICE_CALL"):
            a += ["-s", canal]
        _run(a, entrada=texto, timeout=90)


def tocar_wav(wav, duracao):
    """Toca um WAV (bytes) no alto-falante pelo termux-media-player e espera terminar (para o painel saber que ela ainda fala)."""
    pasta = os.environ.get("FRIDAY_AUDIO_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "friday-audio")
    os.makedirs(pasta, exist_ok=True)
    fd, caminho = tempfile.mkstemp(suffix=".wav", dir=pasta)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav)
        _run(["termux-media-player", "play", caminho], timeout=10)
        time.sleep(min(max(duracao, 0.0) + 0.4, 120))
    finally:
        try:
            _run(["termux-media-player", "stop"], timeout=5)
        except RuntimeError:
            pass
        try:
            os.remove(caminho)
        except OSError:
            pass


def notificar_local(titulo, texto, botoes=(), abrir=None, id="friday"):
    """botoes: [(rótulo, comando)]. O comando roda no Termux quando você toca no botão."""
    a = ["termux-notification", "--id", str(id), "--priority", "high", f"--title={titulo}"[:120], f"--content={texto}"[:500]]
    for i, (rotulo, cmd) in enumerate(list(botoes)[:3], 1):
        a += [f"--button{i}", rotulo, f"--button{i}-action", cmd]
    if abrir:
        a += ["--action", abrir]
    _run(a)
    return "Notificação mostrada no celular."


def ouvir_uma_vez():
    """Reconhecimento de voz nativo do Android (uma frase). Devolve o texto ou ''."""
    out = _run(["termux-speech-to-text"], timeout=30)
    linhas = [l.strip() for l in out.splitlines() if l.strip()]
    return linhas[-1] if linhas else ""


def abrir_url(url):
    if not re.match(r"^https?://", url):
        raise ValueError("só abro links http(s)")
    _run(["termux-open-url", url])


def compartilhar(caminho):
    _run(["termux-share", "-a", "send", caminho])


def wake_lock():
    try:
        _run(["termux-wake-lock"])
    except RuntimeError:
        pass


# ---------- contatos: SÓ os da lista do .env (CONTATOS=nome:+55119...,outro:+55...) ----------
def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower().strip()) if not unicodedata.combining(c))


def contatos():
    r = {}
    for p in os.getenv("CONTATOS", "").split(","):
        n, _, num = p.strip().partition(":")
        num = re.sub(r"[\s\-()]", "", num)
        if n and re.fullmatch(r"\+?\d{10,15}", num):
            r[_norm(n)] = num
    return r


def numero_de(nome):
    c = contatos()
    n = c.get(_norm(nome))
    if not n:
        raise ValueError(f"Não tenho '{nome}' na lista de contatos permitidos. Disponíveis: {', '.join(c) or 'nenhum (defina CONTATOS no .env)'}.")
    return n


def enviar_sms(contato, texto):
    n = numero_de(contato)
    texto = str(texto).strip()
    if not texto or len(texto) > 300:
        raise ValueError("A mensagem precisa ter de 1 a 300 caracteres.")
    _run(["termux-sms-send", "-n", n], entrada=texto, timeout=30)
    return f"SMS enviado para {contato}."


def ligar(contato):
    _run(["termux-telephony-call", numero_de(contato)], timeout=20)
    return f"Ligando para {contato}."


def preparar_whatsapp(contato, texto):
    """Abre o WhatsApp com a mensagem pronta. Quem toca em 'enviar' é você."""
    from urllib.parse import quote
    n = numero_de(contato).lstrip("+")
    abrir_url(f"https://wa.me/{n}?text={quote(str(texto)[:500])}")
    return f"Abri o WhatsApp com a mensagem para {contato}. Falta só você tocar em enviar."
