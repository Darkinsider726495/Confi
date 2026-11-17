"""Escuta contínua pelo Android: diga «Friday, …» sem tocar na tela, mesmo com o painel fechado.

Usa o reconhecimento de voz do próprio Android (termux-speech-to-text) em laço: ouve uma frase, e só age se a frase começar
pela palavra de ativação («Friday», «Sexta-feira»…). O resto é ignorado e não fica guardado. Só VOCÊ liga/desliga, por voz:
«fique sempre ouvindo» / «pare de ouvir sempre». Não pausa enquanto ela fala (para não se ouvir). Gasta mais bateria e,
em alguns celulares, o Android dá um bipe a cada escuta — por isso começa desligada (ou ESCUTA_CONTINUA=1 no .env).
"""
import json, os, re, threading, time
import android as A
import memoria as M

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".escuta.json")
WAKE = re.compile(r"\b(friday|fraide|fraidei|fraidey|fraidi|freidei|frai day|fridei|fride|sexta[- ]feira)\b[\s,.:;!?-]*", re.I)
_trava = threading.Lock()


def ligada():
    try:
        with open(ARQ, encoding="utf-8") as f:
            return bool(json.load(f).get("ligada"))
    except (OSError, ValueError):
        return os.getenv("ESCUTA_CONTINUA", "0") == "1"


def _gravar(v):
    with _trava:
        tmp = ARQ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ligada": bool(v), "t": time.time()}, f)
        os.replace(tmp, ARQ)


def depois_da_palavra(frase):
    """O pedido que vem depois de «Friday», '' se só chamou, ou None se a frase não começa por ela (é conversa de outra pessoa)."""
    frase = " ".join(str(frase or "").split())
    m = WAKE.search(frase)
    if not m or m.start() > 12:                     # a palavra tem que vir no começo: «a Friday disse…» no meio de uma conversa não ativa
        return None
    return frase[m.end():].strip()


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_LIGA = re.compile(_P + r"(?:(?:fique|fica) (?:sempre )?(?:ouvindo|escutando)(?: sempre)?|(?:liga|ligue|ative) a escuta (?:continua|sempre)|ouca sempre)[ .!?]*$")
_DESLIGA = re.compile(_P + r"(?:(?:pare|para) de (?:ouvir|escutar) sempre|(?:desliga|desligue|desative) a escuta (?:continua|sempre))[ .!?]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _LIGA.match(f):
        if not A.disponivel():
            return "A escuta contínua precisa do Termux:API no celular."
        _gravar(True)
        return "Certo: fico ouvindo. Comece com «Friday» e eu respondo, mesmo com o painel fechado. Para parar: «pare de ouvir sempre»."
    if _DESLIGA.match(f):
        _gravar(False)
        return "Parei a escuta contínua. Continuo ouvindo pelo painel quando você tocar em Falar."
    return None


def laco(processar, falar, estado, dormir=time.sleep, ouvir=None):
    """Roda numa thread. `estado()` devolve o estado do painel (não escuta enquanto ela fala)."""
    ouvir = ouvir or A.ouvir_uma_vez
    while True:
        try:
            if not ligada() or not A.disponivel():
                dormir(5)
                continue
            if str(estado() or "").startswith("fal"):
                dormir(0.5)
                continue
            frase = ouvir()
            pedido = depois_da_palavra(frase)
            if pedido is None:
                continue
            if not pedido:
                falar("Pode falar.")
                pedido = ouvir()
                if not pedido:
                    continue
            falar(processar(pedido))
        except Exception:
            dormir(3)
