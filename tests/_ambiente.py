"""Ambiente isolado de teste: tudo em pasta temporária, nada toca o projeto real. Importe ANTES dos módulos da FRIDAY."""
import os, sys, stat, tempfile

TMP = tempfile.mkdtemp(prefix="friday-teste-")
os.environ.setdefault("FUNDO_INTERVALO_S", "0")   # testes não esperam a vez do trabalho de fundo
os.environ.setdefault("FUNDO_DONO_S", "0")
os.environ.update(
    FRIDAY_DB=os.path.join(TMP, "t.db"), FRIDAY_AUDITORIA=os.path.join(TMP, "aud.jsonl"), FRIDAY_PIN="4321",
    RELES="luz:17:1,portao:27:3,tomada:22:2", FRIDAY_PLATAFORMA="android", FRIDAY_DOCS=os.path.join(TMP, "docs"),
    FRIDAY_TOKEN_ARQ=os.path.join(TMP, "token"), FRIDAY_AUTONOMIA_ARQ=os.path.join(TMP, "autonomia.json"), FRIDAY_DIAG_ARQ=os.path.join(TMP, "diagnostico.txt"), FRIDAY_HEARTBEAT=os.path.join(TMP, "hb"),
    FRIDAY_LAB=os.path.join(TMP, "lab"), FRIDAY_MAE_ARQ=os.path.join(TMP, "mae.json"),
    CONTATOS="mae:+5511999990001,Sócio:(11) 98888-0002", SILENCIO="", DESCANSO="", OBSIDIAN_VAULT=os.path.join(TMP, "cofre"),
    FRIDAY_VIDA="0", VISAO_FONTE="off",  # estado interno e câmera desligados por padrão nos testes (os números mudam com o tempo); test_vida liga
    CEREBRO_RAG="0", CEREBRO_RAG_DIR=os.path.join(TMP, "rag"),  # busca semântica desligada e isolada: sem rede/Ollama e sem escrever no projeto durante os testes
    IA_MODO="", IA_PROVEDOR="")  # neutraliza o .env real: main.py faz load_dotenv e, como ele não sobrescreve o que já existe, os testes ficam imunes a um .env de produção (ex.: IA_MODO=local)
for k in ("ANTHROPIC_API_KEY", "NTFY_URL", "NTFY_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "BRAVE_API_KEY"):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "friday"))

_CANNED = {
    "battery-status": '{"percentage": 80, "status": "DISCHARGING", "plugged": "UNPLUGGED", "temperature": 29.5}',
    "wifi-connectioninfo": '{"supplicant_state": "COMPLETED", "ssid": "casa"}',
    "location": '{"latitude": -23.55052, "longitude": -46.63331, "accuracy": 20.0}',
    "speech-to-text": "que horas são",
}
_NOMES = ["battery-status", "wifi-connectioninfo", "location", "torch", "vibrate", "tts-speak", "notification", "sms-send",
          "telephony-call", "share", "open-url", "speech-to-text", "wake-lock", "media-player"]


def termux_falso():
    """Cria comandos termux-* de mentira que anotam o que receberam em $TERMUX_LOG. Devolve (pasta, arquivo_de_log)."""
    d = os.path.join(TMP, "bin")
    os.makedirs(d, exist_ok=True)
    log = os.path.join(TMP, "termux.log")
    for n in _NOMES:
        saida = _CANNED.get(n, "")
        p = os.path.join(d, "termux-" + n)
        with open(p, "w") as f:
            f.write('#!/usr/bin/env bash\n{ echo "CMD $(basename "$0") $*"; s=$(cat); [ -n "$s" ] && echo "STDIN $s"; } >> "$TERMUX_LOG"\n'
                    + (f'[ -n "${{TERMUX_{n.upper().replace("-", "_")}:-}}" ] && echo "${{TERMUX_{n.upper().replace("-", "_")}}}" || echo \'{saida}\'\n' if saida else "")
                    + 'exit "${TERMUX_FALHA:-0}"\n')
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    open(log, "w").close()
    return d, log


def ler_log(log):
    with open(log, encoding="utf-8") as f:
        return f.read()
