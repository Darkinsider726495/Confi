"""Ouvido e voz, 100% locais: palavra de ativação (openWakeWord), fala->texto (faster-whisper), texto->fala (Piper)."""
import os, time, subprocess
import numpy as np, sounddevice as sd
SR = 16000

class Voz:
    def __init__(self):
        from faster_whisper import WhisperModel
        from openwakeword.model import Model
        self.stt = WhisperModel(os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
        self.ww = Model(wakeword_models=[os.getenv("WAKE_MODEL", "hey_jarvis")], inference_framework="onnx")
        self.voz = os.getenv("PIPER_VOZ", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "voz", "pt_BR-faber-medium.onnx"))

    def esperar_chamado(self):
        self.ww.reset(); lim = float(os.getenv("WAKE_LIMIAR", "0.5"))
        with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=1280) as s:
            while True:
                x, _ = s.read(1280)
                if max(self.ww.predict(x[:, 0]).values()) > lim: return

    def ouvir(self, max_s=10):
        lim = float(os.getenv("VAD_LIMIAR", "350")); frames, falou, sil, t0 = [], False, 0, time.time()
        with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=1600) as s:
            while time.time() - t0 < max_s:
                x, _ = s.read(1600); frames.append(x[:, 0].copy())
                if np.abs(x).mean() > lim: falou, sil = True, 0
                elif falou:
                    sil += 1
                    if sil >= 8: break
        if not falou: return ""
        audio = np.concatenate(frames).astype(np.float32) / 32768
        seg, _ = self.stt.transcribe(audio, language="pt", beam_size=1, vad_filter=True)
        return " ".join(s.text for s in seg).strip()

    def falar(self, texto):
        # piper | aplay sem shell: o caminho da voz (PIPER_VOZ) vira argumento, nunca parte de um comando interpretado
        piper = subprocess.Popen(["piper", "--model", str(self.voz), "--output-raw"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        aplay = subprocess.Popen(["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"], stdin=piper.stdout)
        piper.stdout.close()                    # o aplay fica sendo o único leitor do áudio
        piper.communicate(texto.encode())
        aplay.wait()
