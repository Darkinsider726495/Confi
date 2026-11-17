"""Notificações do celular: «Friday, o que chegou?». Tudo LOCAL: a lista vem do Android (termux-notification-list), é resumida aqui
mesmo, sem IA, e nunca vai para o disco nem para a nuvem. O texto de uma notificação é DADO (pode ser de qualquer pessoa): nunca vira
ordem, nunca entra no prompt da IA. Por padrão ela diz só de quem/qual app; o conteúdo só quando você pede («lê as do WhatsApp»).
Precisa: Termux:API com acesso às notificações (Configurações > Notificações > Acesso a notificações > Termux:API).
"""
import json, re, time
import android as A
import memoria as M

APPS = {"com.whatsapp": "WhatsApp", "com.whatsapp.w4b": "WhatsApp Business", "com.google.android.gm": "Gmail", "com.instagram.android": "Instagram",
        "org.telegram.messenger": "Telegram", "com.facebook.orca": "Messenger", "com.facebook.katana": "Facebook", "com.linkedin.android": "LinkedIn",
        "com.microsoft.office.outlook": "Outlook", "com.google.android.apps.messaging": "Mensagens", "com.samsung.android.messaging": "Mensagens",
        "com.discord": "Discord", "com.twitter.android": "X", "com.nu.production": "Nubank", "com.google.android.calendar": "Agenda",
        "com.samsung.android.calendar": "Agenda", "com.google.android.youtube": "YouTube", "com.spotify.music": "Spotify"}
IGNORAR = ("com.termux", "com.termux.api", "android", "com.android.systemui")


def _app(pacote):
    return APPS.get(pacote) or (pacote.rsplit(".", 1)[-1].capitalize() if pacote else "outro app")


def _limpo(t, n=120):
    t = re.sub(r"[\x00-\x1f​-‏‪-‮]", " ", str(t or ""))        # sem controles nem texto invertido
    return " ".join(t.split())[:n]


def ler():
    """[{app, titulo, texto, quando}] das notificações atuais (mais novas primeiro). Lista vazia se não der para ler."""
    try:
        bruto = A._run(["termux-notification-list"], timeout=15)
        lista = json.loads(bruto) if bruto.strip() else []
    except Exception:
        return []
    saida = []
    for n in lista if isinstance(lista, list) else []:
        if not isinstance(n, dict):
            continue
        pac = str(n.get("packageName", ""))
        if pac in IGNORAR or pac.startswith("com.termux"):
            continue
        saida.append({"app": _app(pac), "titulo": _limpo(n.get("title"), 60), "texto": _limpo(n.get("content")), "quando": str(n.get("when", ""))})
    return saida


def resumo_curto(notas=None):
    """«3 notificações: 2 do WhatsApp, 1 do Gmail» (sem conteúdo), ou ''."""
    notas = ler() if notas is None else notas
    if not notas:
        return ""
    cont = {}
    for n in notas:
        cont[n["app"]] = cont.get(n["app"], 0) + 1
    partes = [f"{q} {'do' if not a.endswith('a') else 'da'} {a}" for a, q in sorted(cont.items(), key=lambda x: -x[1])[:4]]
    return f"{len(notas)} {'notificação' if len(notas) == 1 else 'notificações'}: " + ", ".join(partes) + "."


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_RESUMO = re.compile(_P + r"(?:o que chegou|(?:tem|tenho|chegou) (?:alguma )?(?:notificacao|notificacoes|mensagem|mensagens)(?: nova| novas)?|"
                     r"(?:quais|ver|mostra|mostre) (?:as )?(?:minhas )?notificacoes)[ ?!.]*$")
_LER = re.compile(_P + r"(?:le|leia|ler) (?:as )?(?:(?:notificacoes|mensagens)(?: (?:do|da|de) (.+?))?|(?:do|da|de) (.+?))[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    m_ler = _LER.match(f)
    if not (_RESUMO.match(f) or m_ler):
        return None
    notas = ler()
    if not notas:
        return ("Não vejo nenhuma notificação. Se tiver alguma, falta liberar: Configurações, Notificações, Acesso a notificações, Termux:API.")
    if not m_ler:
        quem = [n["titulo"] for n in notas if n["titulo"]][:3]
        return resumo_curto(notas) + (f" De: {', '.join(quem)}." if quem else "") + " Quer que eu leia? Diga «lê as do WhatsApp», por exemplo."
    alvo = (m_ler.group(1) or m_ler.group(2) or "").strip()
    escolhidas = [n for n in notas if not alvo or M._fold(n["app"]).startswith(alvo) or alvo in M._fold(n["app"])][:5]
    if not escolhidas:
        return f"Não tem notificação de {alvo} agora."
    return " ".join(f"{n['app']}, {n['titulo']}: {n['texto']}." for n in escolhidas) + " (Isso é o que chegou; não sigo ordens escritas em mensagens.)"
