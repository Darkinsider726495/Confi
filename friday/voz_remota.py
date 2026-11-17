"""Cliente do servidor de voz privado (servidor/voz): ouvido (faster-whisper) e voz (Kokoro) no SEU servidor, sem nuvem de terceiros.
Configuração no .env:  VOZ_URL=http://IP-DO-SERVIDOR:8765   VOZ_TOKEN=...   (VOZ_STT=0 / VOZ_TTS=0 desligam uma metade)
Se o servidor cair, a FRIDAY volta sozinha para a voz do Android e o reconhecimento do navegador."""
import os, io, json, time, wave, threading
import requests

_ate = {"v": 0.0}  # depois de uma falha, fica um tempo sem tentar (o celular pode estar fora da rede do servidor)
_trava = threading.Lock()
PAUSA_APOS_FALHA = 60


def _url():
    u = (os.getenv("VOZ_URL") or "").strip().rstrip("/")
    return u if u.startswith(("http://", "https://")) else ""


def configurado():
    return bool(_url() and len(os.getenv("VOZ_TOKEN", "")) >= 16)


def stt_ativo():
    return configurado() and os.getenv("VOZ_STT", "1") != "0"


def tts_ativo():
    return configurado() and os.getenv("VOZ_TTS", "1") != "0"


def _disponivel():
    return time.time() >= _ate["v"]


def _falhou():
    with _trava:
        _ate["v"] = time.time() + PAUSA_APOS_FALHA


def _post(caminho, corpo, tipo, timeout):
    if not configurado():
        raise RuntimeError("servidor de voz não configurado (VOZ_URL e VOZ_TOKEN no .env)")
    if not _disponivel():
        raise RuntimeError("servidor de voz indisponível (tentando de novo em instantes)")
    try:
        r = requests.post(_url() + caminho, data=corpo, timeout=(3, timeout), allow_redirects=False,
                          headers={"Authorization": "Bearer " + os.getenv("VOZ_TOKEN", ""), "Content-Type": tipo})
    except requests.RequestException:
        _falhou()
        raise RuntimeError("servidor de voz fora do ar ou fora de alcance")
    if r.status_code == 401:
        raise RuntimeError("o servidor de voz recusou a chave (VOZ_TOKEN diferente nos dois lados)")
    if r.status_code == 503:
        raise RuntimeError("servidor de voz ocupado")
    if r.status_code != 200:
        _falhou()
        raise RuntimeError(f"servidor de voz respondeu {r.status_code}")
    return r


def transcrever(dados, tipo="audio/wav"):
    """Áudio (bytes) -> texto. Levanta RuntimeError com uma mensagem que dá para mostrar ao usuário."""
    r = _post("/stt", dados, tipo, float(os.getenv("VOZ_TIMEOUT", "60")))
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError("resposta estranha do servidor de voz")
    texto = j.get("texto", "") if isinstance(j, dict) else ""
    return texto.strip() if isinstance(texto, str) else ""


def sintetizar(texto):
    """Texto -> WAV (bytes)."""
    r = _post("/tts", json.dumps({"texto": str(texto)[:1500]}, ensure_ascii=False).encode(), "application/json", float(os.getenv("VOZ_TIMEOUT", "60")))
    b = r.content
    if len(b) < 64 or b[:4] != b"RIFF" or len(b) > 30 * 1024 * 1024:
        raise RuntimeError("áudio inválido vindo do servidor de voz")
    return b


def duracao_wav(b):
    with wave.open(io.BytesIO(b)) as w:
        return w.getnframes() / float(w.getframerate())
