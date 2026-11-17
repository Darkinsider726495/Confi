#!/usr/bin/env python3
"""Servidor de voz privado da FRIDAY: ouvido (faster-whisper) e voz (Kokoro). Roda no SEU servidor/PC; o áudio não vai para a nuvem.
  POST /stt   corpo = áudio (WAV, WebM, MP3...)           -> {"ok": true, "texto": "..."}
  POST /tts   {"texto": "..."}                            -> áudio WAV (24 kHz, mono)
  GET  /saude (sem chave)                                 -> {"ok": true, "stt": ..., "tts": ...}
Toda rota de voz exige o cabeçalho  Authorization: Bearer <VOZ_TOKEN>.
  python servidor_voz.py             sobe o servidor
  python servidor_voz.py --testar    fala uma frase e a reconhece de volta (confere a instalação)
Variáveis: veja servidor/voz/README.md."""
import os, io, sys, json, time, wave, hmac, threading, http.server

LIM_AUDIO = int(os.getenv("VOZ_MAX_AUDIO", str(8 * 1024 * 1024)))
LIM_TEXTO = 1500
# frases que o Whisper "inventa" quando ouve só ruído ou silêncio
ALUCINACOES = ("legendas pela comunidade", "obrigado por assistir", "inscreva-se", "legendado por", "amara.org", "tchau, tchau")


def _limpar(texto):
    t = " ".join(str(texto).split())
    if len(t) < 70 and any(a in t.lower() for a in ALUCINACOES):
        return ""
    return t


class MotorSTT:
    """faster-whisper (CTranslate2). O modelo só é carregado na primeira chamada; o primeiro uso baixa o modelo."""

    def __init__(self):
        self._m, self._trava = None, threading.Lock()

    def _modelo(self):
        with self._trava:
            if self._m is None:
                from faster_whisper import WhisperModel
                self._m = WhisperModel(os.getenv("STT_MODELO", "small"), device=os.getenv("STT_DEVICE", "auto"),
                                       compute_type=os.getenv("STT_COMPUTE", "auto"), download_root=os.getenv("VOZ_MODELOS") or None)
            return self._m

    def transcrever(self, dados):
        segs, info = self._modelo().transcribe(io.BytesIO(dados), language=os.getenv("STT_IDIOMA", "pt"), beam_size=int(os.getenv("STT_BEAM", "3")),
                                               vad_filter=True, condition_on_previous_text=False)
        partes = [s.text.strip() for s in segs if getattr(s, "no_speech_prob", 0.0) < 0.6]  # a lista só roda aqui: segs é um gerador
        return _limpar(" ".join(p for p in partes if p)), float(getattr(info, "duration", 0.0) or 0.0)


class MotorTTS:
    """Kokoro-82M. pt-BR = lang_code 'p'; vozes pt: pm_alex (padrão), pf_dora, pm_santa (veja a página do modelo)."""
    SR = 24000

    def __init__(self):
        self._p, self._trava = None, threading.Lock()

    def _pipeline(self):
        with self._trava:
            if self._p is None:
                from kokoro import KPipeline
                self._p = KPipeline(lang_code=os.getenv("KOKORO_IDIOMA", "p"), repo_id="hexgrad/Kokoro-82M")
            return self._p

    def sintetizar(self, texto):
        pedacos = []
        for r in self._pipeline()(texto, voice=os.getenv("KOKORO_VOZ", "pm_alex"), speed=float(os.getenv("KOKORO_VELOCIDADE", "1.0")), split_pattern=r"\n+"):
            a = r.audio if hasattr(r, "audio") else r[2]
            if a is not None:
                pedacos.append(a)
        return wav_bytes(pedacos, self.SR)


def wav_bytes(pedacos, sr):
    """Junta trechos de áudio (listas, arrays ou tensores de floats entre -1 e 1) em um WAV de 16 bits."""
    import numpy as np
    if not pedacos:
        raise RuntimeError("sem áudio")
    x = np.concatenate([np.asarray(p.detach().cpu().numpy() if hasattr(p, "detach") else p, dtype=np.float32).ravel() for p in pedacos])
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


class Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, endereco, token, stt, tts):
        super().__init__(endereco, Handler)
        self.token, self.stt, self.tts = token, stt, tts
        self.vez = threading.Lock()  # uma inferência por vez (CPU/GPU compartilhados); as outras esperam um pouco


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 30
    server_version = "FridayVoz"

    def _resp(self, corpo, tipo="application/json", codigo=200):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, o, codigo=200):
        self._resp(json.dumps(o).encode(), codigo=codigo)

    def _auth(self):
        h = self.headers.get("Authorization", "")
        return h.startswith("Bearer ") and hmac.compare_digest(h[7:].encode(), self.server.token.encode())

    def do_GET(self):
        if self.path.split("?")[0] == "/saude":
            return self._json({"ok": True, "stt": self.server.stt is not None, "tts": self.server.tts is not None})
        self._json({"ok": False}, 404)

    def do_POST(self):
        if not self._auth():
            return self._json({"ok": False, "msg": "sem chave"}, 401)
        p = self.path.split("?")[0]
        if p not in ("/stt", "/tts"):
            return self._json({"ok": False}, 404)
        motor = self.server.stt if p == "/stt" else self.server.tts
        if motor is None:
            return self._json({"ok": False, "msg": "desligado neste servidor"}, 501)
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = -1
        limite = LIM_AUDIO if p == "/stt" else 8192
        if n <= 0 or n > limite:
            return self._json({"ok": False, "msg": "tamanho inválido"}, 413 if n > limite else 400)
        corpo = self.rfile.read(n)
        if not self.server.vez.acquire(timeout=120):
            return self._json({"ok": False, "msg": "ocupado"}, 503)
        t0 = time.time()
        try:
            if p == "/stt":
                texto, dur = motor.transcrever(corpo)
                print(f"stt {n} bytes, {dur:.1f}s de áudio, {time.time() - t0:.1f}s", flush=True)  # nunca registra o conteúdo
                return self._json({"ok": True, "texto": texto, "duracao": round(dur, 2)})
            try:
                texto = json.loads(corpo).get("texto")
            except (ValueError, AttributeError):
                texto = None
            if not isinstance(texto, str) or not texto.strip() or len(texto) > LIM_TEXTO:
                return self._json({"ok": False, "msg": "texto inválido"}, 400)
            wav = motor.sintetizar(texto.strip())
            print(f"tts {len(texto)} letras, {time.time() - t0:.1f}s", flush=True)
            return self._resp(wav, "audio/wav")
        except Exception as e:
            print(f"falha em {p}: {type(e).__name__}", flush=True)
            return self._json({"ok": False, "msg": "falha no motor de voz"}, 500)
        finally:
            self.server.vez.release()

    def log_message(self, *a):
        pass


def criar(bind, porta, token, stt, tts):
    if len(token or "") < 16:
        raise ValueError("VOZ_TOKEN precisa ter ao menos 16 caracteres")
    return Servidor((bind, porta), token, stt, tts)


def testar():
    """Fala uma frase, reconhece de volta e mostra os tempos. Baixa os modelos na primeira vez."""
    frase = "Olá, chefe. Todos os sistemas operacionais."
    t0 = time.time()
    wav = MotorTTS().sintetizar(frase)
    t1 = time.time()
    texto, dur = MotorSTT().transcrever(wav)
    t2 = time.time()
    print(f"Fala: {len(wav) // 1024} KB de áudio em {t1 - t0:.1f}s (inclui carregar o modelo)")
    print(f"Ouvido: {texto!r} em {t2 - t1:.1f}s (inclui carregar o modelo)")
    ok = "sistemas" in texto.lower()
    print("✔ ida e volta funcionou" if ok else "✖ o texto reconhecido não bate: confira os modelos e o espeak-ng")
    return 0 if ok else 1


def main():
    if "--testar" in sys.argv:
        sys.exit(testar())
    token = os.getenv("VOZ_TOKEN", "")
    bind, porta = os.getenv("VOZ_BIND", "127.0.0.1"), int(os.getenv("VOZ_PORTA", "8765"))
    stt = None if os.getenv("VOZ_STT", "1") == "0" else MotorSTT()
    tts = None if os.getenv("VOZ_TTS", "1") == "0" else MotorTTS()
    try:
        srv = criar(bind, porta, token, stt, tts)
    except ValueError as e:
        sys.exit(f"{e}. Gere uma com:  python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    print(f"Servidor de voz em http://{bind}:{porta} (ouvido: {'sim' if stt else 'não'}, voz: {'sim' if tts else 'não'})", flush=True)
    if bind not in ("127.0.0.1", "localhost", "::1"):
        print("Aviso: fora do 127.0.0.1 só use um IP privado (Tailscale/LAN) e nunca exponha esta porta à internet.", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
