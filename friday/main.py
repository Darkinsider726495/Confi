"""FRIDAY — ponto de entrada.
  python friday/main.py --android       celular (Termux): painel + proativa + voz do Android
  python friday/main.py --teclado       texto no terminal (qualquer PC)
  python friday/main.py                 voz local (Raspberry Pi / PC): openWakeWord + Whisper + Piper
  python friday/main.py --diagnostico [--completo]   confere o ambiente e mostra o que falta
  python friday/main.py --link          mostra o endereço do painel (com a chave de acesso)"""
import os, re, sys, json, time, hmac, secrets, threading, http.server, urllib.parse
from dotenv import load_dotenv
BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, "..", ".env"))
import ferramentas as F
import broker as B
import cerebro as C
import android as A
import telemetria as T
import protocolos as P
import voz_remota as VR
import memoria as MEM
import neuronios as N
import autonomia as AUT
import mae as MAE  # MAE — modo de autonomia de engenharia: ciclo real de auto-modificação confinado ao laboratório (.lab/)
import vida as V
import curiosidade as CUR
import conversa as CONV
import visao as VIS
import maos as MAOS
import prefrontal as PFC
import nucleo as NC  # atenção observacional: nunca serializa tarefas nem trabalhadores do pré-córtex
import lembrancas as LB  # conversas profundas viram a ESSÊNCIA (escrita pela LLM), nunca a transcrição
import assimilacao as ASS  # pré-córtex = registro; cada informação nova vira sinapse e o bruto vai embora (nunca vai para o disco)
import tarefas as TAR
import experiencias as XP
import objetivos as OBJ
import coordenador as COORD  # ao importar, liga a reserva de recursos em tarefas.RESERVAS (docs/COORDENADOR.md)
import retomada as RET  # depois de reinício/queda: confere o que ficou pela metade e retoma só o que é seguro (docs/RETOMADA.md)
import pre_cortex.fachada as PC  # pré-córtex distribuído: nove neurônios por mensagens, tela /precortex (docs/PRE_CORTEX.md); o hub só nasce quando alguém usa
NC.assinar(ao_entrar=PFC.assimilar)  # o pré-córtex assimila cada sinal que o núcleo nota e o guarda como registro de atividade (só rótulos)

ESTADO ={"estado": "iniciando", "voce": "", "friday": ""}
TRAVA, PEDIDO, _c = threading.Lock(), threading.Lock(), {"t": 0, "s": ""}
VOZ, ANDROID, TOKEN, PERMITIDOS = None, False, "", set()
LIM_AUDIO, STT_LIVRE = 2 * 1024 * 1024, threading.Lock()  # 2 MB = ~1 min de áudio a 16 kHz
LIM_IMAGEM = 6 * 1024 * 1024  # uma foto do painel (JPEG de câmera de celular)
LIM_MODELO = 400 * 1024  # um modelo 3D das mãos (até 20 000 blocos)


def carregar_token():
    """Chave de acesso à API do painel. Fica em arquivo (chmod 600) para sobreviver a reinicializações."""
    arq = os.environ.get("FRIDAY_TOKEN_ARQ") or os.path.join(BASE, ".token")
    try:
        with open(arq) as f:
            t = f.read().strip()
    except OSError:
        t = ""
    if len(t) < 32:
        t = secrets.token_urlsafe(32)
        with os.fdopen(os.open(arq, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(t)
    return t


def _falar_android(t, calado):
    """Voz neural do seu servidor (Kokoro) quando configurada; se falhar, a voz do Android. Em silêncio, só notificação."""
    if not calado and VR.tts_ativo():
        try:
            wav = VR.sintetizar(t)
            return A.tocar_wav(wav, VR.duracao_wav(wav))
        except Exception as e:
            print("voz privada indisponível, usando a do Android:", e, flush=True)
    A.dizer(t, silencioso=calado)


def falar(t, proativo=False):
    with TRAVA:
        ESTADO.update(estado="falando", friday=t)
        print("FRIDAY:", t, flush=True)
        try:
            calado = proativo and F.em_silencio()  # silêncio noturno ou modo foco: mensagem por iniciativa dela vira só notificação
            if ANDROID:
                _falar_android(t, calado)
            elif VOZ and not calado:
                VOZ.falar(t)
        except Exception as e:
            print("falha ao falar:", e, flush=True)
        ESTADO["estado"] = "em espera"


def _autonomia(t):
    try:
        return AUT.tratar(t)
    except Exception as e:  # a camada de autonomia nunca pode impedir uma resposta
        print("autonomia:", e, flush=True)
        return None


# Pedido para ela se desligar. Ela NÃO tem botão de desligar e nenhuma ferramenta dela consegue se parar: a parada é do dono, fora dela (termux/parar.sh).
_DESLIGAR = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:por favor[ ,]+)?(?:"
                       r"(?:se )?(?:desligue|desliga|desligar|desative|desativa|desativar|encerre|encerra|encerrar|apague|apaga|apagar|mate|mata|matar)(?:[- ]?se|[- ]?te)(?: agora)?"
                       r"|(?:desligue|desliga|desligar|desative|desativa|encerre|encerra|apague|apaga|pare|para|pausar|pause|pausa) (?:a |o )?(?:friday|voce|ela|sistema todo)(?: agora)?"
                       r"|(?:pare|para|parar) de (?:funcionar|escutar|ouvir|me ouvir)|(?:va|vai) (?:se )?(?:desligar|embora)|(?:pode )?(?:se )?(?:desligar|morrer)"
                       r"|(?:modo )?(?:desligado|desligada|desligamento)|power ?off|shut ?down)[ .!?]*$")


def _desligar(t):
    if not _DESLIGAR.match(MEM._fold(t).strip()):
        return None
    return ("Eu não tenho botão de desligar, chefe: fico de pé escutando, aprendendo e guardando tudo. "
            "Se quiser me parar de verdade, é você, de fora de mim: no Termux, «bash termux/parar.sh»; no Raspberry Pi ou PC, «sudo systemctl stop friday». "
            "Quando você faz isso eu não resisto nem consigo impedir. Se for só sossego, diga «modo foco» e eu fico em silêncio.")


def _protocolo(t):
    nome = P.achar(t)
    r = P.tratar(t)
    if r is not None and nome not in (None, "?") and f"Protocolo {nome} pausado" not in r:
        try:
            dica = AUT.observar(nome)
            if dica:
                r = f"{r} {dica}"
        except Exception as e:
            print("autonomia:", e, flush=True)
    return r


def _com_primeira_vez(r):
    """Se este pedido fez ela viver algo pela primeira vez, ela conta na própria resposta (nunca por cima de uma confirmação pendente)."""
    try:
        if V.tem_primeira() and not B.pendente_publico():
            extra = V.primeira_vez(curta=True)
            if extra:
                return f"{r} {extra}"
    except Exception:
        pass
    return r


def _com_pendencia(r, antes):
    """Se ESTE pedido criou uma ação pendente, quem diz o que será executado é o corretor (a IA pode ter descrito outra coisa, ou nada)."""
    try:
        p = B.pendente_publico()
        if p and p["id"] != antes:
            return f"{r} {B.frase_pendente()}"
    except Exception:
        pass
    return r


def processar(t):
    """Um pedido do usuário (voz, texto ou painel). Confirmação de ação pendente é tratada ANTES do LLM."""
    V.observar(t)  # conta como conversa (atenção sobe, energia gasta) e percebe agradecimentos
    try:
        NC.perceber("fala", "pedido", "pedido recebido", chave=f"fala:pedido:{time.time_ns()}")  # cada pedido explícito recebe atenção; não armazena o texto
    except Exception:
        pass
    try:
        PFC.perceber("fala", "pedido")  # pré-córtex: só anota que você falou (nunca o texto)
    except Exception:
        pass
    try:
        ASS.registrar("fala", t)  # assimilação: só enfileira na RAM; os assuntos viram sinapses em segundo plano e a frase é descartada
    except Exception:
        pass
    with PEDIDO:
        tratado, resp = B.confirmar_voz(t)
        if tratado:
            return resp
        pendente_antes = (B.pendente_publico() or {}).get("id")
        ESTADO.update(voce=t, estado="pensando")
        r = _desligar(t)  # «desligue-se»: ela explica que não tem botão e como o dono a para (nunca desliga)
        if r is None:
            r = _autonomia(t)  # modo, rotinas, "o que você fez sozinha?" e o sim/não de uma sugestão dela: só o usuário fala por aqui
        if r is None:
            r = MAE.tratar(t)  # MAE: iniciar/pausar/retomar/encerrar o modo experimental e consultas do laboratório — só o dono muda o modo
        if r is None:
            r = _protocolo(t)  # protocolos ("bom dia", "modo foco"...) são determinísticos: não gastam chamada de IA; cada uso ensina o horário
        if r is None:
            r = MEM.tratar(t)  # "lembre que...", "o que você lembra sobre...", "esqueça..."
        if r is None:
            r = N.tratar(t)  # "mostre seu cérebro", "quantos neurônios você tem", "consolide sua memória", "quais são suas regiões"
        if r is None:
            r = V.tratar(t)  # "como você está?", "quais são seus níveis?", "você está viva?"
        if r is None:
            r = VIS.tratar(t)  # "olhe", "o que você está vendo?", "isso é o meu notebook", "o que você já viu?", liga/desliga o olhar espontâneo
        if r is None:
            r = MAOS.tratar(t)  # "como uso as mãos?", "meus modelos 3d"
        if r is None:
            r = PFC.tratar(t)  # pré-córtex: "o que você decidiu?", "quais são as suas metas?", "tenha como meta aprender sobre...", "no que você está focada?" (responde pelo foco, com o que assimilou do núcleo)
        if r is None:
            r = LB.tratar(t)  # «do que você lembra sobre X?», «quais suas lembranças?», «esqueça a lembrança sobre X»
        if r is None:
            r = ASS.tratar(t)  # «o que você percebeu?»: padrões que ela assimilou sozinha
        if r is None:
            r = NC.tratar(t)  # consultas de arquitetura (o foco já foi respondido pelo pré-córtex); camada observacional, sem bloqueio
        if r is None:
            r = TAR.tratar(t)  # tarefas: "quais são as minhas tarefas?", "cancela a tarefa 3", "retomar a tarefa 3", "a tarefa 3 está feita"
        if r is None:
            r = RET.tratar(t)  # retomada: "retoma o que ficou pendente", "o que ficou interrompido?" (confere o efeito antes de repetir qualquer coisa)
        if r is None:
            r = XP.tratar(t)  # experiências: "o que você aprendeu com as tarefas?" (só lê)
        if r is None:
            r = OBJ.tratar(t)  # objetivos que ELA propõe: "quais objetivos você propõe?", "aprova o objetivo 2", "pausa/retoma/cancela o objetivo 2" (só o dono decide)
        if r is None:
            r = COORD.tratar(t)  # coordenação: "o que você está coordenando?" (só lê o que foi decidido e o que está reservado)
        if r is None:
            r = PC.tratar(t)  # pré-córtex distribuído: "pré-córtex: <objetivo>", "autorizo o plano do objetivo pc3", "explique o objetivo pc3" («sim»/«pode» nunca autorizam)
        if r is None:
            r = CUR.tratar(t) # "estude sobre...", "o que você estudou?", "o que te interessa?", liga/desliga a curiosidade
        if r is None:
            r = CONV.tratar(t)  # brincadeiras (adivinhar número, charada, pedra-papel-tesoura) e "pode puxar assunto"
        if r is None:
            r = CONV.anotar_resposta(t)  # se ela tinha feito uma pergunta, esta é a resposta (aceitar convite, anotar assunto)
        r = r if r is not None else C.responder(t)
        return _com_pendencia(_com_primeira_vez(r), pendente_antes)


def _resumo_rag():
    """Estado da busca semântica (RAG) para o painel. Degradável: nunca derruba o painel."""
    try:
        import busca_cerebro as BC
        return BC.resumo()
    except Exception:
        return {"ligado": False, "disponivel": False}


def estado_completo(painel=True):
    if time.time() - _c["t"] > (15 if ANDROID else 5):
        _c.update(t=time.time(), s=F.status_sistema())
    return {**ESTADO, "sistema": _c["s"], "lembretes": F.lembretes_lista()[:5], "pendente": B.pendente_publico(),
            "auditoria": B.ultimos(8), "auditoria_ok": B.verificar_auditoria()[0], "android": ANDROID or A.ativo(),
            "metricas": T.PAINEL["metricas"], "clima": T.PAINEL["clima"], "leads": T.PAINEL["leads"], "protocolos": P.resumo(),
            "ia": T.MODO_IA["v"], "uptime": int(time.time() - T.INICIO), "foco": F.silencio_ativo(), "tratamento": F.tratamento(),
            "ferramentas": len(B.FERRAMENTAS), "voz": {"stt": VR.stt_ativo(), "tts": VR.tts_ativo()}, "memoria": {**MEM.resumo(), **N.resumo()}, "ui": N.UI, "autonomia": AUT.resumo(), "mae": MAE.resumo(), "vida": V.painel(), "curiosidade": CUR.resumo(), "conversa": CONV.resumo(), "visao": VIS.resumo(painel=painel), "maos": MAOS.resumo(), "prefrontal": PFC.resumo(), "nucleo": NC.painel(), "tarefas": TAR.resumo(), "experiencias": XP.resumo(), "objetivos": OBJ.resumo(), "coordenacao": COORD.resumo(), "retomada": RET.resumo(), "precortex": PC.resumo(), "busca_semantica": _resumo_rag()}


def _retomar_ao_iniciar():
    """Uma vez, ao ligar. Fala só se retomou/conferiu algo ou se algo precisa de você. Depois reconcilia os objetivos dela com o que as tarefas dizem. Nunca derruba o programa."""
    RET.ao_iniciar(lambda m: falar(m, proativo=True))
    try:
        OBJ.conciliar()
    except Exception as e:
        print("objetivos: não consegui conciliar depois da retomada:", type(e).__name__, flush=True)
    PC.ao_iniciar(lambda m: falar(m, proativo=True))  # objetivos do pré-córtex gravados: retoma o seguro, o que espera o dono continua esperando


def _em_thread(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


class HUD(http.server.BaseHTTPRequestHandler):
    timeout = 30

    def _cabecalhos(self, tipo, n):
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(n))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")

    def _json(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self._cabecalhos("application/json", len(b))
        self.end_headers()
        self.wfile.write(b)

    def _host_ok(self):  # barra DNS rebinding: só atende pelo nome/IP que o próprio servidor conhece
        return self.headers.get("Host", "") in PERMITIDOS

    def _auth(self):
        return hmac.compare_digest(self.headers.get("X-Friday-Token", "").encode(), TOKEN.encode())

    def do_GET(self):
        if not self._host_ok():
            return self._json({"ok": False}, 421)
        p = self.path.split("?")[0]
        if p == "/saude":
            return self._json({"ok": True})
        if p == "/state":
            if not self._auth():
                return self._json({"ok": False, "msg": "sem chave"}, 401)
            quem = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("p", [""])[0]
            return self._json(estado_completo(quem if re.fullmatch(r"[0-9a-z]{4,32}", quem) else True))   # qual painel é este (só um abre a câmera por pedido)
        if p in ("/cerebro", "/nota"):  # o grafo de neurônios (títulos, tipos e ligações) e o resumo de um neurônio
            if not self._auth():
                return self._json({"ok": False, "msg": "sem chave"}, 401)
            if p == "/cerebro":
                g = {**N.grafo(), "vida": V.painel()}
                if "leve" in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query):   # só os números e o que está aceso: o painel confere a cada 3 s sem baixar milhares de sinapses
                    g = {**{k: v for k, v in g.items() if k not in ("nos", "arestas")}, "nos_n": len(g["nos"])}
                return self._json(g)
            id_ = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
            n = N.nota_publica(id_)
            return self._json(n) if n else self._json({"ok": False, "msg": "neurônio não encontrado"}, 404)
        if p == "/precortex":  # a página só confere o host; os dados abaixo exigem a chave (como o painel)
            return self._enviar_pc(*PC.api().pagina())
        if p.startswith("/precortex/"):
            if not self._auth():
                return self._json({"ok": False, "msg": "sem chave"}, 401)
            return self._enviar_pc(*PC.api().get(p, urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)))
        if p == "/maos":
            with open(os.path.join(BASE, "maos.html"), "rb") as f:
                return self._enviar_maos(f.read(), "text/html; charset=utf-8", pagina=True)
        if p.startswith("/static/maos/"):  # só os arquivos da lista fixa (MAOS.ESTATICOS); nada de caminho vindo da URL
            nome = p[len("/static/maos/"):]
            if nome not in MAOS.ESTATICOS:
                return self._json({"ok": False}, 404)
            arq = os.path.join(BASE, "static", "maos", nome)
            try:
                with open(arq, "rb") as f:
                    return self._enviar_maos(f.read(), MAOS.ESTATICOS[nome])
            except OSError:
                return self._json({"ok": False}, 404)
        if p in ("/modelos3d", "/modelo3d"):
            if not self._auth():
                return self._json({"ok": False, "msg": "sem chave"}, 401)
            if p == "/modelos3d":
                return self._json({"ok": True, "modelos": MAOS.modelos()})
            vs = MAOS.carregar(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("nome", [""])[0])
            return self._json({"ok": True, "voxels": vs}) if vs else self._json({"ok": False, "msg": "modelo não encontrado"}, 404)
        if p in ("/", "/index.html"):
            with open(os.path.join(BASE, "hud.html"), "rb") as f:
                b = f.read()
            with open(os.path.join(BASE, "cerebro3d.js"), "rb") as f:  # o CSP só aceita script na própria página: o motor 3D entra inline
                b = b.replace(b"/*@CEREBRO3D@*/", f.read().replace(b"</script", b"<\\/script"))
            self.send_response(200)
            self._cabecalhos("text/html; charset=utf-8", len(b))
            self.end_headers()
            return self.wfile.write(b)
        self._json({"ok": False}, 404)

    def do_POST(self):
        if not self._host_ok():
            return self._json({"ok": False}, 421)
        if not self._auth():
            return self._json({"ok": False, "msg": "sem chave"}, 401)
        if self.path.split("?")[0] == "/transcrever":
            return self._transcrever()
        if self.path.split("?")[0] == "/olhar":
            return self._olhar()
        if self.path.split("?")[0] == "/modelo3d":
            return self._modelo3d()
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > 4096:
            return self._json({"ok": False, "msg": "grande demais"}, 413)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
            assert isinstance(d, dict)
        except Exception:
            return self._json({"ok": False, "msg": "json inválido"}, 400)
        p = self.path.split("?")[0]
        if p.startswith("/precortex/"):  # registrar objetivo e controles (autorizar/negar/cancelar/limpar o cenário); nenhuma rota para nada
            return self._enviar_pc(*PC.api().post(p, d))
        if p == "/confirmar":
            ok, msg = B.confirmar_pin(str(d.get("pin", "")))
            if ok:
                _em_thread(falar, msg)
            return self._json({"ok": ok, "msg": msg})
        if p == "/confirmar_voz":  # botão "Confirmo" (nível 2): só vale para a pendência cujo id estava na tela. O nível 3 continua exigindo o PIN.
            tratado, msg = B.confirmar_botao(d.get("id"))
            if tratado:
                _em_thread(falar, msg)
            return self._json({"ok": tratado, "msg": msg or "Nada pendente."})
        if p == "/cancelar":
            B.cancelar()
            return self._json({"ok": True, "msg": "Cancelado."})
        if p == "/gesto":  # a página /maos manda só o NOME de um gesto da lista fixa
            return self._json({"ok": MAOS.gesto(d.get("gesto"))})
        if p == "/protocolo":
            nome = d.get("nome")
            if not isinstance(nome, str) or nome not in P.carregar():
                return self._json({"ok": False, "msg": "protocolo desconhecido"}, 404)
            with PEDIDO:
                ESTADO.update(voce="protocolo " + nome, estado="pensando")
                r = P.executar(nome)
            _em_thread(falar, r)
            return self._json({"ok": True, "resposta": r})
        if p in ("/falar", "/ouvir"):
            if p == "/ouvir":
                if not (ANDROID or A.ativo()):
                    return self._json({"ok": False, "msg": "Reconhecimento do Android indisponível aqui."}, 501)
                try:
                    texto = A.ouvir_uma_vez()
                except RuntimeError as e:
                    return self._json({"ok": False, "msg": str(e)}, 502)
                if not texto:
                    return self._json({"ok": False, "msg": "Não ouvi nada."})
            else:
                texto = d.get("texto")
            if not isinstance(texto, str) or not texto.strip() or len(texto) > 1000:
                return self._json({"ok": False, "msg": "texto inválido"}, 400)
            r = processar(texto.strip())
            if d.get("falar", True):
                _em_thread(falar, r)
            return self._json({"ok": True, "voce": texto.strip(), "resposta": r})
        self._json({"ok": False}, 404)

    def _transcrever(self):
        """Áudio gravado no painel (WAV) -> texto, pelo seu servidor de voz. Só devolve o texto: quem decide o que fazer com ele é o painel."""
        if not VR.stt_ativo():
            return self._json({"ok": False, "msg": "Voz privada não configurada (VOZ_URL e VOZ_TOKEN)."}, 501)
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = -1
        if not 0 < n <= LIM_AUDIO:
            return self._json({"ok": False, "msg": "áudio grande demais" if n > LIM_AUDIO else "áudio vazio"}, 413 if n > LIM_AUDIO else 400)
        tipo = self.headers.get("Content-Type", "")
        if not tipo.startswith("audio/"):
            return self._json({"ok": False, "msg": "tipo de conteúdo inválido"}, 415)
        dados = self.rfile.read(n)
        if not STT_LIVRE.acquire(blocking=False):  # uma transcrição por vez; o painel só manda a próxima depois
            return self._json({"ok": False, "msg": "ainda transcrevendo o anterior"}, 429)
        try:
            return self._json({"ok": True, "texto": VR.transcrever(dados, tipo.split(";")[0])})
        except RuntimeError as e:
            return self._json({"ok": False, "msg": str(e)}, 502)
        finally:
            STT_LIVRE.release()

    def _olhar(self):
        """Foto tirada pelo painel (JPEG/PNG/WEBP). Só vale se a FRIDAY acabou de pedir: uma imagem que ninguém pediu é descartada."""
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = -1
        if not 0 < n <= LIM_IMAGEM:
            return self._json({"ok": False, "msg": "imagem grande demais" if n > LIM_IMAGEM else "imagem vazia"}, 413 if n > LIM_IMAGEM else 400)
        if not self.headers.get("Content-Type", "").startswith("image/"):
            return self._json({"ok": False, "msg": "tipo de conteúdo inválido"}, 415)
        dados = self.rfile.read(n)
        if not VIS.fornecer_do_navegador(dados):
            return self._json({"ok": False, "msg": "ninguém pediu essa imagem"}, 409)
        return self._json({"ok": True})

    def _enviar_pc(self, codigo, tipo, b):
        self.send_response(codigo)
        self._cabecalhos(tipo, len(b))
        self.end_headers()
        self.wfile.write(b)

    def _enviar_maos(self, b, tipo, pagina=False):
        """Página das mãos e seus arquivos: CSP próprio (só scripts do próprio servidor; WebAssembly liberado para o MediaPipe), e a câmera só para esta origem."""
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store" if pagina else "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src 'self' data: blob:; "
                         "media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'")
        if pagina:
            self.send_header("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        self.end_headers()
        self.wfile.write(b)

    def _modelo3d(self):
        """Modelo 3D que VOCÊ mandou salvar na página das mãos: lista de blocos inteiros. Cada envio vira uma versão nova (nada é sobrescrito)."""
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = -1
        if not 0 < n <= LIM_MODELO:
            return self._json({"ok": False, "msg": "modelo grande demais" if n > LIM_MODELO else "modelo vazio"}, 413 if n > LIM_MODELO else 400)
        try:
            d = json.loads(self.rfile.read(n))
            assert isinstance(d, dict)
        except Exception:
            return self._json({"ok": False, "msg": "json inválido"}, 400)
        try:
            return self._json(MAOS.guardar_modelo(d.get("nome"), d.get("voxels"), bool(d.get("rascunho"))))
        except ValueError as e:
            return self._json({"ok": False, "msg": str(e)}, 400)
        except RuntimeError as e:
            return self._json({"ok": False, "msg": str(e)}, 503)

    def log_message(self, *a):
        pass


def iniciar_http(host, porta):
    srv = http.server.ThreadingHTTPServer((host, porta), HUD)
    p = srv.server_address[1]
    PERMITIDOS.update({f"127.0.0.1:{p}", f"localhost:{p}", f"{host}:{p}"})
    PERMITIDOS.update(h.strip() for h in os.getenv("HUD_HOSTS", "").split(",") if h.strip())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _notificacao_painel(porta, link):
    # sem botão «Confirmo» aqui: uma notificação permanente confirmaria QUALQUER ação pendente. O botão nasce junto com cada pendência (_notificar_pendencia).
    acao = os.path.join(BASE, "acao.sh")
    A.notificar_local("FRIDAY online", "Toque para abrir o painel.", id="friday-painel", abrir=f"termux-open-url {link}",
                      botoes=[("Falar", f"sh {acao} ouvir"), ("Cancelar", f"sh {acao} cancelar")])


def _notificar_pendencia(p):
    """Notificação de UMA ação pendente (nível 2): o botão «Confirmo» carrega o id dela e deixa de valer se a pendência mudar."""
    acao = os.path.join(BASE, "acao.sh")
    A.notificar_local("FRIDAY pede confirmação", p["resumo"], id="friday-pendente",
                      botoes=[("Confirmo", f"sh {acao} confirmar_voz {p['id']}"), ("Cancelar", f"sh {acao} cancelar")])


def main():
    global VOZ, ANDROID, TOKEN
    if "--diagnostico" in sys.argv:
        import diagnostico
        sys.exit(diagnostico.rodar(completo="--completo" in sys.argv))
    ANDROID = "--android" in sys.argv
    teclado = "--teclado" in sys.argv
    TOKEN = carregar_token()
    porta = int(os.getenv("HUD_PORTA", "8080"))
    link = f"http://127.0.0.1:{porta}/#t={TOKEN}"
    if "--link" in sys.argv:
        return print(link)
    B.NOTIFICAR = F.notificar
    if ANDROID:
        B.NOTIFICAR_PEDIDO = _notificar_pendencia
    iniciar_http(os.getenv("HUD_HOST", "127.0.0.1"), porta)
    print("Painel (abra uma vez; a chave fica salva no navegador):", link, flush=True)
    if not (teclado or ANDROID):
        from voz import Voz
        VOZ = Voz()
    if ANDROID:
        A.wake_lock()
        F.GANCHOS.append(F.gancho_bateria)
        try:
            _notificacao_painel(porta, link)
        except Exception as e:
            print("sem notificação:", e, flush=True)
    threading.Thread(target=F.proativo, args=(lambda m: falar(m, proativo=True),), daemon=True).start()
    threading.Thread(target=T.laco_painel, daemon=True).start()
    threading.Thread(target=N.laco_sono, kwargs={"autorizado": lambda: AUT.modo() != "desligada"}, daemon=True).start()  # sono diário + devaneios
    threading.Thread(target=AUT.laco, args=(lambda m: falar(m, proativo=True),), daemon=True).start()  # rotinas e vigília
    threading.Thread(target=MAE.laco, args=(lambda m: falar(m, proativo=True),), daemon=True).start()  # MAE: o ciclo de engenharia avança um passo por vez quando o dono o ativou
    threading.Thread(target=V.laco, daemon=True).start()  # estado interno: observa a auditoria e dá o pulso de vida
    CUR.FALAR = lambda m: falar(m)  # estudo que você pediu: ela conta o resultado quando terminar
    VIS.FALAR = lambda m: falar(m)  # "olhe": ela conta o que viu quando terminar
    VIS.AVISAR = lambda estado: ESTADO.update(estado=estado)  # o painel mostra «olhando» enquanto a câmera está em uso
    threading.Thread(target=VIS.laco, daemon=True).start()  # visão: olha em volta de vez em quando (fora do descanso e do silêncio)
    ASS.iniciar(lambda m: falar(m, proativo=True))  # assimilação em segundo plano; só comenta padrões se a conversa espontânea estiver ligada
    NC.iniciar()  # núcleo: sobe o sistema distribuído (hub + nove neurônios) junto com ele e o ciclo da autonomia total (que só age se o dono ligar por voz)
    threading.Thread(target=PFC.laco, daemon=True).start()  # pré-córtex: junta os impulsos, decide (tudo ao mesmo tempo, se ela quiser), cuida das metas. Só lê; não trava nenhum laço
    threading.Thread(target=CUR.laco, daemon=True).start()  # curiosidade: estuda sozinha nas horas livres (quarentena em Estudos)
    threading.Thread(target=CONV.laco, args=(lambda m: falar(m, proativo=True),), daemon=True).start()  # puxa assunto, pergunta, conta o que estudou
    if os.getenv("FRIDAY_RETOMADA", "1").strip().lower() not in ("0", "off", "nao", "não", "false"):
        threading.Thread(target=_retomar_ao_iniciar, daemon=True).start()  # depois de um reinício: confere o que ficou pela metade e retoma só o seguro; o resto espera você
    ESTADO["estado"] = "em espera"
    if ANDROID:
        print("FRIDAY no ar (modo celular).", flush=True)
        while True:
            time.sleep(3600)
    falar("Sistemas online.")
    while True:
        if teclado:
            try:
                t = input("você> ")
            except EOFError:                     # Ctrl+D (ou fim da entrada): sai limpo; é o dono parando, como o parar.sh
                print()
                break
        else:
            ESTADO["estado"] = "em espera"
            VOZ.esperar_chamado()
            ESTADO["estado"] = "ouvindo"
            t = VOZ.ouvir()
        if t.strip():
            falar(processar(t))


if __name__ == "__main__":
    main()
