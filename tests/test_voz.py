"""Servidor de voz (faster-whisper + Kokoro) e cliente do celular. Os modelos de verdade não rodam aqui (precisam baixar GBs);
os motores são trocados por falsos, e a chamada às bibliotecas é conferida contra a assinatura real (se instaladas)."""
import os, io, sys, json, wave, time, types, threading, importlib.util, http.client, unittest
import numpy  # noqa: F401  (importar antes dos mocks de sys.modules: o numpy não pode ser carregado duas vezes)
from unittest import mock
import _ambiente as E  # noqa: F401

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location("servidor_voz", os.path.join(RAIZ, "servidor", "voz", "servidor_voz.py"))
SV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SV)
TOKEN = "t" * 32


def wav_falso(seg=0.5, sr=16000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(b"\x00\x00" * int(sr * seg))
    return b.getvalue()


class STTFalso:
    def __init__(self, texto="que horas são"):
        self.texto, self.vistos, self.ativos, self.max_ativos, self.erro = texto, [], 0, 0, None

    def transcrever(self, dados):
        self.ativos += 1
        self.max_ativos = max(self.max_ativos, self.ativos)
        try:
            time.sleep(0.15)
            if self.erro:
                raise self.erro
            self.vistos.append(dados)
            return self.texto, 0.5
        finally:
            self.ativos -= 1


class TTSFalso:
    def __init__(self):
        self.textos = []

    def sintetizar(self, texto):
        self.textos.append(texto)
        return SV.wav_bytes([[0.0, 0.5, -0.5, 0.0] * 600], 24000)


def chamar(srv, metodo, caminho, corpo=None, token=TOKEN, tipo="application/octet-stream", cl=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Content-Type": tipo}
    if token:
        h["Authorization"] = "Bearer " + token
    if cl is not None:  # declara um tamanho sem mandar o corpo: o servidor tem de recusar antes de ler
        c.putrequest(metodo, caminho)
        for k, v in {**h, "Content-Length": str(cl)}.items():
            c.putheader(k, v)
        c.endheaders()
    else:
        c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.getheader("Content-Type"), r.read()


class Rotas(unittest.TestCase):
    def setUp(self):
        self.stt, self.tts = STTFalso(), TTSFalso()
        self.srv = SV.criar("127.0.0.1", 0, TOKEN, self.stt, self.tts)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def test_saude_sem_chave(self):
        s, _, b = chamar(self.srv, "GET", "/saude", token=None)
        self.assertEqual((s, json.loads(b)), (200, {"ok": True, "stt": True, "tts": True}))

    def test_sem_chave_ou_chave_errada_e_recusado(self):
        for tk in (None, "errada" * 8, TOKEN[:-1]):
            for rota in ("/stt", "/tts"):
                with self.subTest(tk=tk, rota=rota):
                    self.assertEqual(chamar(self.srv, "POST", rota, b"x", token=tk)[0], 401)
        self.assertEqual(self.stt.vistos, [])

    def test_token_curto_nao_sobe(self):
        with self.assertRaises(ValueError):
            SV.criar("127.0.0.1", 0, "curto", None, None)

    def test_stt_devolve_o_texto(self):
        audio = wav_falso()
        s, tipo, b = chamar(self.srv, "POST", "/stt", audio, tipo="audio/wav")
        j = json.loads(b)
        self.assertEqual((s, j["ok"], j["texto"]), (200, True, "que horas são"))
        self.assertEqual(self.stt.vistos, [audio])  # o servidor entrega os bytes exatos ao motor

    def test_stt_tamanhos(self):
        self.assertEqual(chamar(self.srv, "POST", "/stt", b"")[0], 400)
        self.assertEqual(chamar(self.srv, "POST", "/stt", cl=SV.LIM_AUDIO + 1)[0], 413)
        self.assertEqual(chamar(self.srv, "POST", "/tts", cl=9000)[0], 413)

    def test_tts_devolve_wav(self):
        s, tipo, b = chamar(self.srv, "POST", "/tts", json.dumps({"texto": "Olá, chefe."}).encode(), tipo="application/json")
        self.assertEqual((s, tipo), (200, "audio/wav"))
        with wave.open(io.BytesIO(b)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 24000))
            self.assertGreater(w.getnframes(), 1000)
        self.assertEqual(self.tts.textos, ["Olá, chefe."])

    def test_tts_entradas_invalidas(self):
        for corpo in (b"nao json", b"[]", b'{"texto": ""}', b'{"texto": 5}', json.dumps({"texto": "a" * (SV.LIM_TEXTO + 1)}).encode()):
            with self.subTest(corpo=corpo[:20]):
                self.assertEqual(chamar(self.srv, "POST", "/tts", corpo)[0], 400)
        self.assertEqual(self.tts.textos, [])

    def test_erro_do_motor_vira_500_sem_vazar_detalhes_e_o_servidor_segue(self):
        self.stt.erro = RuntimeError("caminho secreto /home/x/modelo")
        s, _, b = chamar(self.srv, "POST", "/stt", wav_falso())
        self.assertEqual(s, 500)
        self.assertNotIn(b"secreto", b)
        self.stt.erro = None
        self.assertEqual(chamar(self.srv, "POST", "/stt", wav_falso())[0], 200)

    def test_motor_desligado_da_501(self):
        srv = SV.criar("127.0.0.1", 0, TOKEN, None, self.tts)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.assertEqual(chamar(srv, "POST", "/stt", b"x")[0], 501)
        self.assertEqual(json.loads(chamar(srv, "GET", "/saude", token=None)[2])["stt"], False)

    def test_uma_inferencia_por_vez(self):
        res = []
        ts = [threading.Thread(target=lambda: res.append(chamar(self.srv, "POST", "/stt", wav_falso())[0])) for _ in range(4)]
        [t.start() for t in ts]; [t.join(15) for t in ts]
        self.assertEqual(res, [200] * 4)
        self.assertEqual(self.stt.max_ativos, 1)

    def test_rota_desconhecida(self):
        self.assertEqual(chamar(self.srv, "POST", "/outra", b"x")[0], 404)
        self.assertEqual(chamar(self.srv, "GET", "/stt", token=None)[0], 404)


class Motores(unittest.TestCase):
    def test_limpa_alucinacoes_do_whisper(self):
        self.assertEqual(SV._limpar("  que   horas são  "), "que horas são")
        self.assertEqual(SV._limpar("Legendas pela comunidade Amara.org"), "")
        self.assertEqual(SV._limpar("Obrigado por assistir!"), "")
        longo = "Hoje eu falei sobre o inscreva-se do canal e " * 4  # frase longa de verdade não é cortada
        self.assertEqual(SV._limpar(longo), longo.strip())

    def test_wav_aceita_lista_array_e_tensor(self):
        import numpy as np

        class Tensor:  # imita torch.Tensor: .detach().cpu().numpy()
            def __init__(s, a): s.a = np.array(a, dtype=np.float32)
            def detach(s): return s
            def cpu(s): return s
            def numpy(s): return s.a
        w = SV.wav_bytes([[0.1, -0.1], np.array([0.2, 2.5, -9.0]), Tensor([0.0, 0.3])], 24000)
        with wave.open(io.BytesIO(w)) as f:
            self.assertEqual(f.getnframes(), 7)
            amostras = np.frombuffer(f.readframes(7), dtype="<i2")
        self.assertEqual(int(amostras[3]), 32767)   # 2.5 foi limitado a 1.0
        self.assertEqual(int(amostras[4]), -32767)  # -9.0 foi limitado a -1.0
        with self.assertRaises(RuntimeError):
            SV.wav_bytes([], 24000)

    def test_stt_chama_o_faster_whisper_do_jeito_certo(self):
        chamadas = {}

        class Seg:
            def __init__(s, t, nsp): s.text, s.no_speech_prob = t, nsp

        class WhisperModel:
            def __init__(s, nome, **kw): chamadas["init"] = (nome, kw)
            def transcribe(s, audio, **kw):
                chamadas["transcribe"] = (audio, kw)
                return (x for x in [Seg(" Friday,", 0.1), Seg("ruído", 0.9), Seg("que horas são?", 0.2)]), types.SimpleNamespace(duration=2.5)

        fake = types.ModuleType("faster_whisper")
        fake.WhisperModel = WhisperModel
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}), mock.patch.dict(os.environ, {"STT_MODELO": "base", "STT_DEVICE": "cpu", "STT_COMPUTE": "int8"}):
            m = SV.MotorSTT()
            texto, dur = m.transcrever(b"RIFFxxxx")
            m.transcrever(b"RIFFyyyy")
        self.assertEqual((texto, dur), ("Friday, que horas são?", 2.5))  # trecho com no_speech_prob alto foi descartado
        self.assertEqual(chamadas["init"][0], "base")
        self.assertEqual((chamadas["init"][1]["device"], chamadas["init"][1]["compute_type"]), ("cpu", "int8"))
        audio, kw = chamadas["transcribe"]
        self.assertIsInstance(audio, io.BytesIO)
        self.assertEqual((kw["language"], kw["vad_filter"], kw["condition_on_previous_text"]), ("pt", True, False))

    def test_tts_chama_o_kokoro_do_jeito_certo(self):
        vistos = {"n": 0}

        class Res:  # resultado novo do Kokoro (atributo .audio)
            audio = [0.1] * 100

        class KPipeline:
            def __init__(s, lang_code, repo_id=None, **kw): vistos["init"] = (lang_code, repo_id); vistos["n"] += 1
            def __call__(s, texto, voice, speed, split_pattern):
                vistos["call"] = (texto, voice, speed)
                yield Res()
                yield ("graf", "fon", [0.2] * 50)  # formato antigo (tupla)

        fake = types.ModuleType("kokoro")
        fake.KPipeline = KPipeline
        with mock.patch.dict(sys.modules, {"kokoro": fake}):
            m = SV.MotorTTS()
            w = m.sintetizar("Olá, chefe.")
            m.sintetizar("de novo")
        self.assertEqual(vistos["init"], ("p", "hexgrad/Kokoro-82M"))
        self.assertEqual(vistos["n"], 1)  # o modelo carrega uma vez só
        self.assertEqual(vistos["call"][1], "pm_alex")
        with wave.open(io.BytesIO(w)) as f:
            self.assertEqual((f.getframerate(), f.getnframes()), (24000, 150))

    def test_assinatura_real_do_faster_whisper(self):
        """Se o faster-whisper estiver instalado, confere que os argumentos que usamos existem de verdade."""
        try:
            import inspect
            import faster_whisper
        except ImportError:
            self.skipTest("faster-whisper não instalado neste ambiente")
        init = set(inspect.signature(faster_whisper.WhisperModel.__init__).parameters)
        self.assertTrue({"device", "compute_type", "download_root"} <= init)
        tr = set(inspect.signature(faster_whisper.WhisperModel.transcribe).parameters)
        self.assertTrue({"language", "beam_size", "vad_filter", "condition_on_previous_text"} <= tr)


# ---------------------------------------------------------------- celular: cliente, rota do painel e reprodução
import broker as B
import android as A
import voz_remota as VR
import main as M

BIN, LOG = E.termux_falso()
ENV_VOZ = {"VOZ_URL": "http://10.0.0.5:8765", "VOZ_TOKEN": "k" * 24, "PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG}


def resp(status=200, jsn=None, conteudo=b""):
    r = mock.Mock(status_code=status, content=conteudo)
    r.json.return_value = jsn
    return r


class Cliente(unittest.TestCase):
    def setUp(self):
        VR._ate["v"] = 0.0
        p = mock.patch.dict(os.environ, ENV_VOZ)
        p.start()
        self.addCleanup(p.stop)

    def test_configuracao(self):
        self.assertTrue(VR.configurado() and VR.stt_ativo() and VR.tts_ativo())
        for env, esperado in (({"VOZ_URL": ""}, False), ({"VOZ_URL": "ftp://x"}, False), ({"VOZ_URL": "javascript:alert(1)"}, False), ({"VOZ_TOKEN": "curto"}, False)):
            with mock.patch.dict(os.environ, env):
                self.assertEqual(VR.configurado(), esperado, env)
        with mock.patch.dict(os.environ, {"VOZ_STT": "0"}):
            self.assertFalse(VR.stt_ativo())
            self.assertTrue(VR.tts_ativo())
        with mock.patch.dict(os.environ, {"VOZ_TTS": "0"}):
            self.assertFalse(VR.tts_ativo())

    def test_transcrever_manda_chave_e_nao_segue_redirecionamento(self):
        with mock.patch("requests.post", return_value=resp(jsn={"ok": True, "texto": "  que horas são "})) as p:
            self.assertEqual(VR.transcrever(b"RIFF....", "audio/wav"), "que horas são")
        a, kw = p.call_args
        self.assertEqual(a[0], "http://10.0.0.5:8765/stt")
        self.assertEqual(kw["headers"]["Authorization"], "Bearer " + "k" * 24)
        self.assertFalse(kw["allow_redirects"])
        self.assertEqual(kw["data"], b"RIFF....")

    def test_chave_recusada_explica_e_nao_pausa(self):
        with mock.patch("requests.post", return_value=resp(401)):
            with self.assertRaisesRegex(RuntimeError, "recusou a chave"):
                VR.transcrever(b"x")
        with mock.patch("requests.post", return_value=resp(jsn={"texto": "ok"})) as p:
            self.assertEqual(VR.transcrever(b"x"), "ok")  # sem pausa: o erro era de configuração, não de rede
            self.assertEqual(p.call_count, 1)

    def test_servidor_fora_do_ar_pausa_por_um_minuto(self):
        import requests
        with mock.patch("requests.post", side_effect=requests.ConnectionError) as p:
            with self.assertRaisesRegex(RuntimeError, "fora do ar"):
                VR.sintetizar("oi")
            with self.assertRaisesRegex(RuntimeError, "indisponível"):
                VR.sintetizar("oi")  # nem tenta de novo: ela não fica esperando o tempo limite a cada frase
            self.assertEqual(p.call_count, 1)
        VR._ate["v"] = 0.0
        with mock.patch("requests.post", return_value=resp(500)):
            with self.assertRaises(RuntimeError):
                VR.transcrever(b"x")
        self.assertGreater(VR._ate["v"], time.time())

    def test_sintetizar_valida_o_audio(self):
        wav = wav_falso(0.2, 24000)
        with mock.patch("requests.post", return_value=resp(conteudo=wav)) as p:
            self.assertEqual(VR.sintetizar("Olá"), wav)
        self.assertEqual(json.loads(p.call_args[1]["data"]), {"texto": "Olá"})
        for ruim in (b"", b"<html>" + b"x" * 100, b"RIFF"):
            with mock.patch("requests.post", return_value=resp(conteudo=ruim)):
                with self.assertRaisesRegex(RuntimeError, "inválido"):
                    VR.sintetizar("Olá")
        self.assertAlmostEqual(VR.duracao_wav(wav), 0.2, places=2)


class TocarWav(unittest.TestCase):
    def test_toca_e_apaga_o_arquivo(self):
        pasta = os.path.join(E.TMP, "audio")
        with mock.patch.dict(os.environ, {**ENV_VOZ, "FRIDAY_AUDIO_DIR": pasta}):
            open(LOG, "w").close()
            A.tocar_wav(wav_falso(0.05, 24000), 0.05)
            log = E.ler_log(LOG)
        self.assertIn("CMD termux-media-player play " + pasta, log)
        self.assertIn("CMD termux-media-player stop", log)
        self.assertEqual(os.listdir(pasta), [])  # não deixa áudio da conversa guardado


class FalarNoCelular(unittest.TestCase):
    def setUp(self):
        VR._ate["v"] = 0.0
        p = mock.patch.dict(os.environ, ENV_VOZ)
        p.start()
        self.addCleanup(p.stop)

    def test_usa_a_voz_do_servidor(self):
        wav = wav_falso(0.1, 24000)
        with mock.patch("voz_remota.sintetizar", return_value=wav) as s, mock.patch("android.tocar_wav") as t, mock.patch("android.dizer") as d:
            M._falar_android("Olá, chefe.", calado=False)
        s.assert_called_once_with("Olá, chefe.")
        self.assertEqual(t.call_args[0][0], wav)
        d.assert_not_called()

    def test_se_o_servidor_falha_cai_na_voz_do_android(self):
        with mock.patch("voz_remota.sintetizar", side_effect=RuntimeError("fora do ar")), mock.patch("android.tocar_wav") as t, mock.patch("android.dizer") as d:
            M._falar_android("Olá", calado=False)
        t.assert_not_called()
        d.assert_called_once_with("Olá", silencioso=False)

    def test_em_silencio_so_notifica_e_nao_manda_nada_ao_servidor(self):
        with mock.patch("voz_remota.sintetizar") as s, mock.patch("android.dizer") as d:
            M._falar_android("Olá", calado=True)
        s.assert_not_called()
        d.assert_called_once_with("Olá", silencioso=True)

    def test_sem_servidor_configurado_e_como_antes(self):
        with mock.patch.dict(os.environ, {"VOZ_URL": ""}), mock.patch("voz_remota.sintetizar") as s, mock.patch("android.dizer") as d:
            M._falar_android("Olá", calado=False)
        s.assert_not_called()
        d.assert_called_once_with("Olá", silencioso=False)


class RotaTranscrever(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        M.TOKEN = "t" * 40
        cls.srv = M.iniciar_http("127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        VR._ate["v"] = 0.0
        p = mock.patch.dict(os.environ, ENV_VOZ)
        p.start()
        self.addCleanup(p.stop)

    def post(self, corpo=b"RIFFxxxxWAVE", tipo="audio/wav", token="t" * 40, host=None, cl=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        c.putrequest("POST", "/transcrever", skip_host=True)
        c.putheader("Host", host if host is not None else f"127.0.0.1:{self.porta}")
        if token:
            c.putheader("X-Friday-Token", token)
        c.putheader("Content-Type", tipo)
        c.putheader("Content-Length", str(len(corpo) if cl is None else cl))
        c.endheaders(corpo if cl is None else b"")
        r = c.getresponse()
        return r.status, json.loads(r.read())

    def test_devolve_o_texto(self):
        with mock.patch("voz_remota.transcrever", return_value="friday que horas são") as t:
            s, j = self.post(b"RIFF....WAVEdados")
        self.assertEqual((s, j), (200, {"ok": True, "texto": "friday que horas são"}))
        self.assertEqual(t.call_args[0], (b"RIFF....WAVEdados", "audio/wav"))

    def test_exige_chave_e_host(self):
        with mock.patch("voz_remota.transcrever") as t:
            self.assertEqual(self.post(token=None)[0], 401)
            self.assertEqual(self.post(token="x" * 40)[0], 401)
            self.assertEqual(self.post(host="evil.example.com")[0], 421)
        t.assert_not_called()

    def test_validacoes(self):
        with mock.patch("voz_remota.transcrever") as t:
            self.assertEqual(self.post(tipo="application/json")[0], 415)
            self.assertEqual(self.post(corpo=b"")[0], 400)
            self.assertEqual(self.post(cl=M.LIM_AUDIO + 1)[0], 413)
        t.assert_not_called()

    def test_sem_voz_privada_configurada(self):
        with mock.patch.dict(os.environ, {"VOZ_URL": ""}):
            s, j = self.post()
        self.assertEqual(s, 501)
        self.assertIn("não configurada", j["msg"])

    def test_erro_do_servidor_de_voz_vira_mensagem(self):
        with mock.patch("voz_remota.transcrever", side_effect=RuntimeError("servidor de voz fora do ar ou fora de alcance")):
            s, j = self.post()
        self.assertEqual((s, j["ok"]), (502, False))
        self.assertIn("fora do ar", j["msg"])

    def test_uma_transcricao_por_vez(self):
        M.STT_LIVRE.acquire()
        try:
            with mock.patch("voz_remota.transcrever") as t:
                self.assertEqual(self.post()[0], 429)
            t.assert_not_called()
        finally:
            M.STT_LIVRE.release()

    def test_estado_informa_se_a_voz_privada_esta_ativa(self):
        self.assertEqual(M.estado_completo()["voz"], {"stt": True, "tts": True})
        with mock.patch.dict(os.environ, {"VOZ_URL": ""}):
            self.assertEqual(M.estado_completo()["voz"], {"stt": False, "tts": False})


if __name__ == "__main__":
    unittest.main(verbosity=2)
