#!/usr/bin/env python3
"""A FRIDAY dentro do Termux, em modo texto: o estado dela, a torre da mente com os números reais e uma conversa.

    python scripts/terminal.py            abre (conversa com a FRIDAY que já está rodando; não sobe outra)
    python scripts/terminal.py --estado   só mostra o estado e sai

Na conversa:  /estado  /mente  /sair   (qualquer outra coisa vai para ela, como se você tivesse digitado no painel)
Usa a chave do painel que já está no aparelho (friday/.token); nada sai do celular. Ela também fala em voz alta, se a voz estiver ligada.
"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTA = os.getenv("HUD_PORTA", "8080")
URL = f"http://127.0.0.1:{PORTA}"
C = {"az": "\033[96m", "vd": "\033[92m", "am": "\033[93m", "rx": "\033[95m", "vm": "\033[91m", "ci": "\033[90m", "b": "\033[1m", "x": "\033[0m"}
if not sys.stdout.isatty() or os.getenv("NO_COLOR"):
    C = {k: "" for k in C}


def token():
    arq = os.environ.get("FRIDAY_TOKEN_ARQ") or ROOT / "friday" / ".token"
    try:
        return Path(arq).read_text().strip()
    except OSError:
        return ""


def api(caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(URL + caminho, data=dados, method="POST" if dados else "GET",
                               headers={"X-Friday-Token": token(), "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())


def barra(pct, n=12):
    if pct is None:
        return C["ci"] + "·" * n + C["x"]
    k = max(0, min(n, round(pct * n / 100)))
    return C["az"] + "█" * k + C["ci"] + "░" * (n - k) + C["x"]


def estado():
    s = api("/state")
    m = s.get("metricas") or {}
    mem = s.get("memoria") or {}
    v = s.get("vida") or {}
    print(f"\n{C['b']}{C['az']}  F R I D A Y{C['x']}  {C['ci']}·{C['x']} {s.get('estado', '?')}  {C['ci']}· IA:{C['x']} {s.get('ia', '—')}")
    num = lambda k: "—" if m.get(k) is None else f"{m[k]}%"
    print(f"  bateria {barra(m.get('bateria'))} {num('bateria')}   memória {barra(m.get('ram'))} {num('ram')}   disco {barra(m.get('disco'))} {num('disco')}")
    print(f"  {mem.get('neuronios', 0)} neurônios · {mem.get('sinapses', 0)} sinapses · humor {v.get('humor', '—') if isinstance(v, dict) else '—'}"
          f" · {s.get('ferramentas', 0)} ferramentas sob o corretor\n")
    return s


def mente():
    try:
        m = api("/mente/dados")
    except urllib.error.HTTPError:
        m = {}
    s = api("/state")
    sig, rot, llm = m.get("significado", {}), m.get("rotina", {}), m.get("llm", {})
    mem = s.get("memoria") or {}
    pc = (s.get("precortex") or {})
    rot_txt = (f"próxima hora: " + ", ".join(f"{p['rotulo']} {round(p['chance'] * 100)}%" for p in rot.get("previsao", []))
               if rot.get("confiavel") else ("aprendendo" if rot.get("treinada") else f"juntando dados ({rot.get('status', '')})"))
    andares = [
        ("vm", "◇", "Saída", "voz e ações que o corretor deixou passar"),
        ("vm", "⬡", "Corretor", f"{s.get('ferramentas', 0)} ferramentas · nível 4 não existe"),
        ("rx", "●", "Linguagem · LLM", f"{llm.get('provedor', '')} · {llm.get('modelo', '')}"),
        ("vd", "◎", "Núcleo · 9 neurônios", f"{pc.get('ativos', '') or 'distribuídos'}"),
        ("am", "◌", "Rotina · GRU", rot_txt),
        ("vd", "✺", "Memória", f"{mem.get('neuronios', 0)} neurônios · {mem.get('sinapses', 0)} sinapses"),
        ("rx", "≡", "Significado · Transformer", f"{sig.get('motor', '')} · {sig.get('camadas', 0)} camadas · {sig.get('indexadas', 0)} notas"),
        ("az", "▭", "Pré-córtex · registro", f"fila: {m.get('fila_assimilacao', 0)}"),
        ("az", "◯", "Sentidos", "voz/texto · câmera · mãos · sistema · internet · ela mesma"),
    ]
    print()
    for i, (cor, s_, nome, real) in enumerate(andares):
        print(f"  {C[cor]}{s_}{C['x']} {C['b']}{nome:<27}{C['x']} {C['ci']}{real}{C['x']}")
        if i < len(andares) - 1:
            print(f"  {C['ci']}│{C['x']}")
    print(f"\n  {C['ci']}(de baixo para cima: o caminho de um pedido seu pelo código dela){C['x']}\n")


def main():
    if not token():
        print("Não achei a chave do painel (friday/.token). A FRIDAY já foi ligada alguma vez neste aparelho?")
        return 1
    try:
        estado()
    except urllib.error.HTTPError as e:
        print("A FRIDAY recusou a chave." if e.code == 401 else f"Erro {e.code}.")
        return 1
    except (urllib.error.URLError, OSError):
        print("A FRIDAY não está rodando. Ligue com:  nohup bash termux/supervisor.sh >/dev/null 2>&1 &")
        return 1
    if "--estado" in sys.argv:
        return 0
    print(f"{C['ci']}  Converse com ela. Comandos: /estado  /mente  /sair{C['x']}\n")
    while True:
        try:
            t = input(f"{C['b']}você ›{C['x']} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not t:
            continue
        if t in ("/sair", "/q", "sair"):
            return 0
        try:
            if t == "/estado":
                estado()
                continue
            if t == "/mente":
                mente()
                continue
            r = api("/falar", {"texto": t[:900]})
            print(f"{C['az']}friday ›{C['x']} {r.get('resposta') or r.get('msg', '')}\n")
        except urllib.error.HTTPError as e:
            print(f"{C['vm']}erro {e.code}{C['x']}")
        except (urllib.error.URLError, OSError):
            print(f"{C['vm']}perdi a conexão com ela (ela está rodando?){C['x']}")


if __name__ == "__main__":
    raise SystemExit(main())
