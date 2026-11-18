"""Modo vigia: ela PROTEGE e AVISA, nunca ataca. Só olha o que é seu (este celular, as portas dela, a sua rede atual) e só fala com você.

O que ela vigia (sem root, só o que o Android deixa ver):
  - chave errada no painel ou na sincronização (alguém tentando entrar) → avisa na hora, com quantas tentativas;
  - Wi-Fi novo (nome de rede que ela nunca viu) → avisa; se a sincronização com o PC estiver ligada, lembra de desligar fora de casa;
  - portas dela: o painel tem que estar só no próprio celular; a sincronização só aberta quando você ligou;
  - apps instalados (se o Android deixar listar): app novo desde a última vez → avisa o nome do pacote.
Nada é bloqueado, apagado ou desligado sozinho: ela só avisa, e você decide. Só o dono liga/desliga: «liga o modo vigia» / «desliga o modo vigia».
Não há ferramenta da IA para o vigia (nem para «escanear» outros aparelhos).
"""
import json, os, re, subprocess, threading, time
import memoria as M

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(BASE, ".vigia.json")
INTERVALO_S = 300                    # confere a cada 5 min (as tentativas de chave são avisadas na hora)
_trava = threading.Lock()
_tent = {"painel": 0, "sync": 0}     # tentativas com chave errada desde o último aviso
_ult = {"t": 0.0}


def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(d):
    with _trava:
        tmp = ARQ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, ARQ)


def ligado():
    v = _ler().get("ligado")
    return (os.getenv("VIGIA", "1") != "0") if v is None else bool(v)


def tentativa_errada(onde):
    """Chamado pelo painel / pela sincronização quando chega uma chave errada. Só conta; o aviso sai no gancho."""
    if onde in _tent:
        _tent[onde] += 1


# ---------------------------------------------------------------- o que ela olha
def _wifi():
    try:
        import android as A
        if not A.disponivel():
            return None
        w = A._json(["termux-wifi-connectioninfo"])
        nome = str(w.get("ssid", "")).strip('"')
        return nome if nome and nome not in ("<unknown ssid>", "") else None
    except Exception:
        return None


def _apps():
    """Pacotes instalados (set) ou None se o Android não deixar listar."""
    try:
        r = subprocess.run(["pm", "list", "packages", "-3"], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        return {l.split(":", 1)[1].strip() for l in r.stdout.splitlines() if l.startswith("package:")}
    except (OSError, subprocess.SubprocessError):
        return None


def _portas():
    """Problemas nas portas dela (lista de frases)."""
    out = []
    host = os.getenv("HUD_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        out.append(f"o painel está aberto para a rede ({host}); o seguro é só no próprio celular (HUD_HOST=127.0.0.1)")
    try:
        import sincronia as S
        if S.ligada():
            out.append(f"a sincronização com o PC está ligada (porta {S.PORTA}, só rede local e com chave)")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- conferir e avisar
def conferir(agora=None, wifi=None, apps=None):
    """Uma rodada. Devolve a lista de avisos (frases) e atualiza o que ela conhece."""
    agora = time.time() if agora is None else agora
    d = _ler()
    avisos = []
    for onde, nome in (("painel", "no painel"), ("sync", "na sincronização")):
        n, _tent[onde] = _tent[onde], 0
        if n:
            avisos.append(f"Alerta: {n} tentativa{'s' if n > 1 else ''} com chave errada {nome}. Se não foi você, alguém na sua rede está tentando entrar.")
    w = _wifi() if wifi is None else wifi
    if w:
        conhecidas = d.setdefault("wifis", [])
        if w not in conhecidas:
            primeira = not conhecidas
            conhecidas.append(w)
            if not primeira:
                frase = f"Você entrou numa rede Wi-Fi nova: «{w}»."
                try:
                    import sincronia as S
                    if S.ligada():
                        frase += " A sincronização com o PC está ligada: se não for a sua casa, diga «desliga a sincronização»."
                except Exception:
                    pass
                avisos.append(frase)
    a = _apps() if apps is None else apps
    if a is not None:
        antes = set(d.get("apps", []))
        novos = sorted(a - antes) if antes else []
        d["apps"] = sorted(a)
        if novos:
            avisos.append("App novo instalado: " + ", ".join(novos[:5]) + ". Se não foi você, vale conferir.")
    d["ult"] = agora
    d["ult_avisos"] = avisos[-5:] or d.get("ult_avisos", [])
    _gravar(d)
    return avisos


def gancho(agora=None):
    """Para o laço proativo (roda a cada 5 s): tentativa de chave errada avisa logo; o resto, a cada 5 min."""
    if not ligado():
        return []
    agora = time.time() if agora is None else agora
    if not any(_tent.values()) and agora - _ult["t"] < INTERVALO_S:
        return []
    _ult["t"] = agora
    try:
        return conferir(agora)
    except Exception:
        return []


def relatorio():
    d = _ler()
    if not ligado():
        return "O modo vigia está desligado. Diga «liga o modo vigia»."
    partes = [f"Modo vigia ligado: conheço {len(d.get('wifis', []))} rede(s) Wi-Fi"]
    partes.append(f"e {len(d.get('apps', []))} apps instalados" if d.get("apps") else "(o Android não deixa eu listar os apps)")
    p = _portas()
    txt = " ".join(partes) + ". " + ("Portas: " + "; ".join(p) + "." if p else "O painel está só no celular e a sincronização está fechada.")
    ult = d.get("ult_avisos") or []
    return txt + (" Últimos avisos: " + " ".join(ult) if ult else " Nenhum alerta até agora.")


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_LIGA = re.compile(_P + r"(?:liga|ligue|ative|ativa) o (?:modo )?vigia[ .!]*$")
_DESLIGA = re.compile(_P + r"(?:desliga|desligue|desative|desativa) o (?:modo )?vigia[ .!]*$")
_VER = re.compile(_P + r"(?:como esta a (?:minha )?seguranca|relatorio de seguranca|alguma ameaca|tem alguma ameaca|o que o vigia viu)[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _LIGA.match(f):
        d = _ler(); d["ligado"] = True; _gravar(d)
        return "Modo vigia ligado. Eu aviso se alguém errar a chave, se você entrar num Wi-Fi novo ou se aparecer app novo. Só aviso: quem decide é você."
    if _DESLIGA.match(f):
        d = _ler(); d["ligado"] = False; _gravar(d)
        return "Modo vigia desligado."
    if _VER.match(f):
        return relatorio()
    return None
