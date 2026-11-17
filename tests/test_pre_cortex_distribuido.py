"""Fase 7 — contrato das mensagens, transporte e o modo DISTRIBUÍDO com processos de verdade.

Mapa (áreas da missão): 6 comunicação entre trabalhadores independentes · 7 tempo esgotado e trabalhador indisponível · 8 mensagens duplicadas · 9 cancelamento ·
13 recuperação (trabalhador que cai e volta) · 18 compatibilidade (o MESMO código do modo local).
Os trabalhadores aqui são processos separados (`python -m friday.pre_cortex.worker`), falando HTTP em 127.0.0.1. Mesma máquina ≠ várias máquinas: isto prova
comunicação entre processos, não entre computadores.
"""
import json, os, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
from test_pre_cortex_fluxo import BasePC, PEDIDO, planos, tipos
import pre_cortex.catalogo_neuronios as K
import pre_cortex.config as CF
import pre_cortex.contrato as C
import pre_cortex.hub as HB
import pre_cortex.transporte as TR
from pre_cortex.neuronio import Neuronio

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "chave-de-teste-" + "x" * 20


class Eco(Neuronio):
    nome = "eco"
    numero = 99
    papel = responsabilidade = entradas = saidas = confianca = "teste"

    def __init__(self, espera=0.0):
        self.chamadas, self.espera = [], espera

    def acao_repetir(self, corpo, ctx):
        self.chamadas.append(ctx.mensagem["id"])
        if self.espera:
            time.sleep(self.espera)
        ctx.conferir_cancelamento()
        return {"eco": corpo.get("x")}


def msg(x=1, **kw):
    return C.criar("hub", "eco", "repetir", {"x": x}, correlacao=kw.pop("correlacao", "pc0001"), **kw)


class Contrato(unittest.TestCase):
    def test_envelope_valido_e_invalidos(self):
        m = msg()
        self.assertEqual(C.validar(m), (True, ""))
        for mexe in (lambda m: m.update(contrato="precortex/0"), lambda m: m.update(id="sem-formato"), lambda m: m.update(corpo=[1]), lambda m: m.update(expira_em=m["criada_em"] - 1),
                     lambda m: m.update(tentativa=0), lambda m: m.update(plano={"id": "x"}), lambda m: m.update(para="Eco!"), lambda m: m.update(corpo={"x": "y" * (C.TAMANHO_MAX + 1)})):
            m2 = msg()
            mexe(m2)
            self.assertFalse(C.validar(m2)[0], m2)
        self.assertFalse(C.validar("não é objeto")[0])

    def test_campos_obrigatorios(self):
        m = msg(plano={"id": "pl-1", "versao": 2})
        for campo in ("contrato", "id", "tipo", "correlacao", "plano", "de", "para", "acao", "criada_em", "expira_em", "timeout_s", "tentativa", "estado", "corpo"):
            self.assertIn(campo, m)
        r = C.resposta(m, de="eco", ok=False, erro=("timeout", "demorou"))
        for campo in ("em_resposta_a", "ok", "erro", "processado_por", "tempos", "duplicada"):
            self.assertIn(campo, r)
        self.assertEqual(r["em_resposta_a"], m["id"])

    def test_modo_local_tambem_passa_pelo_json(self):
        with self.assertRaises(ValueError):
            C.ida_e_volta({"x": object()})
        with self.assertRaises(ValueError):
            C.ida_e_volta({"x": float("nan")})


class Trabalhador(unittest.TestCase):
    def setUp(self):
        self.eco = Eco()
        self.w = TR.Worker("w", [self.eco])
        self.addCleanup(self.w.encerrar_pool)

    def test_duplicata_nao_reprocessa(self):                                                      # área 8
        m = msg()
        r1, r2 = self.w.processar(m), self.w.processar(json.loads(json.dumps(m)))
        self.assertTrue(r1["ok"] and r2["ok"])
        self.assertEqual(r1["corpo"], r2["corpo"])
        self.assertTrue(r2["duplicada"])
        self.assertEqual(len(self.eco.chamadas), 1)

    def test_duplicata_chegando_enquanto_o_original_roda(self):
        self.eco.espera = 0.3
        m = msg()
        res = []
        ts = [threading.Thread(target=lambda: res.append(self.w.processar(dict(m)))) for _ in range(3)]
        [t.start() for t in ts]
        [t.join(5) for t in ts]
        self.assertEqual(len(self.eco.chamadas), 1)
        self.assertTrue(all(r["ok"] for r in res))
        self.assertEqual(sum(1 for r in res if r["duplicada"]), 2)

    def test_mensagem_vencida_cancelada_ou_para_quem_nao_esta_aqui(self):                      # áreas 7 e 9
        velha = msg(agora=time.time() - 100, validade_s=10)
        self.assertEqual(self.w.processar(velha)["erro"]["codigo"], "expirada")
        self.w.cancelar("pc0002")
        self.assertEqual(self.w.processar(msg(correlacao="pc0002"))["erro"]["codigo"], "cancelada")
        outro = msg()
        outro["para"] = "percepcao"
        self.assertEqual(self.w.processar(outro)["erro"]["codigo"], "neuronio_desconhecido")
        self.assertEqual(self.w.processar({"lixo": True})["erro"]["codigo"], "contrato_invalido")
        self.assertEqual(self.eco.chamadas, [])

    def test_tempo_esgotado_responde_timeout_e_o_reenvio_pega_o_resultado(self):                # área 7
        self.eco.espera = 0.4
        m = msg(timeout_s=0.1)
        r1 = self.w.processar(m)
        self.assertEqual((r1["ok"], r1["erro"]["codigo"]), (False, "timeout"))
        time.sleep(0.5)
        r2 = self.w.processar(m)
        self.assertTrue(r2["ok"] and r2["duplicada"])
        self.assertEqual(len(self.eco.chamadas), 1)

    def test_cancelar_o_que_esta_rodando(self):                                                  # área 9
        self.eco.espera = 0.3
        m = msg(correlacao="pc0003")
        res = []
        t = threading.Thread(target=lambda: res.append(self.w.processar(m)))
        t.start()
        time.sleep(0.1)
        self.assertEqual(self.w.cancelar("pc0003"), 1)
        t.join(5)
        self.assertEqual((res[0]["ok"], res[0]["erro"]["codigo"], res[0]["estado"]), (False, "cancelada", "cancelada"))

    def test_saude_por_neuronio(self):
        self.w.processar(msg())
        s = self.w.saude()
        e = s["neuronios"]["eco"]
        self.assertEqual((e["recebidas"], e["concluidas"], e["falhas"]), (1, 1, 0))
        self.assertIsNotNone(e["tempo_medio_ms"])
        self.assertEqual(s["contrato"], C.VERSAO)


class ServidorHTTPDoTrabalhador(unittest.TestCase):
    def setUp(self):
        self.w = TR.Worker("w", [Eco()])
        self.srv = TR.ServidorHTTP(self.w, TOKEN).iniciar()
        self.addCleanup(self.w.encerrar_pool)
        self.addCleanup(self.srv.parar)

    def test_chave_errada_e_recusada(self):
        with self.assertRaises(TR.Recusado):
            TR.DestinoHTTP("w", self.srv.url, "outra-chave-qualquer-123").enviar(msg(), 2)
        with self.assertRaises(TR.Recusado):
            TR.DestinoHTTP("w", self.srv.url, "").saude()

    def test_host_estranho_e_recusado(self):
        req = urllib.request.Request(self.srv.url + "/saude", headers={"Host": "evil.example:80", "X-Precortex-Token": TOKEN})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as e:
            op.open(req, timeout=3)
        e.exception.close()
        self.assertEqual(e.exception.code, 421)

    def test_duplicata_e_cancelamento_pela_rede(self):
        d = TR.DestinoHTTP("w", self.srv.url, TOKEN)
        m = msg()
        self.assertFalse(d.enviar(m, 2)["duplicada"])
        self.assertTrue(d.enviar(m, 2)["duplicada"])
        d.cancelar("pc0007")
        self.assertEqual(d.enviar(msg(correlacao="pc0007"), 2)["erro"]["codigo"], "cancelada")

    def test_porta_fechada_e_indisponivel(self):
        d = TR.DestinoHTTP("w", "http://127.0.0.1:9", TOKEN)
        with self.assertRaises(TR.Indisponivel):
            d.enviar(msg(), 1)


def iniciar_trabalhador(nome, neuronios, porta=0, token=TOKEN):
    env = {k: v for k, v in os.environ.items() if k != "PRECORTEX_TOKEN"}
    if token is not None:
        env["PRECORTEX_TOKEN"] = token
    p = subprocess.Popen([sys.executable, "-m", "friday.pre_cortex.worker", "--nome", nome, "--neuronios", ",".join(neuronios), "--porta", str(porta)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env, cwd=RAIZ)
    linha = p.stdout.readline()
    return p, json.loads(linha or "{}")


def parar(p):
    if p.poll() is None:
        p.terminate()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(5)
    if p.stdout:
        p.stdout.close()


class Distribuido(BasePC):
    """Processos de verdade. Cada teste abre os seus trabalhadores e os fecha no fim."""

    def subir(self, nome, neuronios, porta=0):
        p, info = iniciar_trabalhador(nome, neuronios, porta)
        self.addCleanup(parar, p)
        self.assertIn("url", info, info)
        self.assertNotEqual(info["pid"], os.getpid())
        return p, info

    def hub_distribuido(self, ws, **cfg):
        c = CF.Config()
        c.aplicar({"modo": "distribuido", "workers": {n: {"url": i["url"]} for n, i in ws.items()}, "espera_entre_tentativas_s": 0.05, **cfg}, "teste")
        self.assertEqual(c.avisos, [])
        h = HB.Hub(c, self.pasta, vigia=False, token=TOKEN)
        self.addCleanup(h.encerrar, 2.0)
        return h

    def test_objetivo_completo_com_neuronios_em_outros_processos(self):                         # área 6
        ws = {n: self.subir(n, neur)[1] for n, neur in K.GRUPOS_PADRAO.items()}
        h = self.hub_distribuido(ws)
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual(est, "concluido")
        self.assertEqual(planos(d), [("anotar", "falha_total"), ("anotar_em_partes", "sucesso")])
        quem = {}
        for e in h.eventos(0, pcid, 5000):
            if e["tipo"] == "mensagem_recebida" and e.get("ok"):
                quem.setdefault(e["de"], set()).add(e["pid"])
        for n in ("percepcao", "hipoteses", "planejamento"):
            self.assertEqual(quem[n], {ws["cognicao"]["pid"]}, n)
        for n in ("critica", "verificador"):
            self.assertEqual(quem[n], {ws["revisao"]["pid"]}, n)
        for n in ("contexto", "aprendizagem"):
            self.assertEqual(quem[n], {os.getpid()}, n)
        h.atualizar_saude()
        for nome in ws:
            s = h.ultima_saude["workers"][nome]
            self.assertTrue(s["disponivel"])
            self.assertEqual(s["isolamento"], {"corretor_carregado": False, "tarefas_carregado": False, "catalogo_carregado": False})
        self.assertEqual(h.ultimo_monitor["modo"], "normal")

    def test_trabalhador_que_cai_bloqueia_e_ao_voltar_o_objetivo_continua(self):                # áreas 7 e 13
        procs, ws = {}, {}
        for n, neur in K.GRUPOS_PADRAO.items():
            procs[n], ws[n] = self.subir(n, neur)
        h = self.hub_distribuido(ws, tentativas_msg=2, timeout_msg_s=2.0)
        rev_pid, porta = ws["revisao"]["pid"], ws["revisao"]["porta"]
        parar(procs["revisao"])                                                                     # derruba o processo da revisão (crítica + verificador)
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"], d["bloqueio"]["recuperavel"]), ("bloqueado", "modulo_indisponivel", True))
        self.assertIn(d["bloqueio"]["modulo"], ("critica", "verificador"))
        self.assertEqual(d["execucoes"], {}, "nada foi executado sem a crítica")
        h.atualizar_saude()
        self.assertFalse(h.ultima_saude["workers"]["revisao"]["disponivel"])
        self.assertEqual(h.ultimo_monitor["modo"], "bloqueado")
        estados = {n["nome"]: n["estado"] for n in h.estado()["neuronios"]}
        self.assertEqual((estados["critica"], estados["verificador"]), ("bloqueado", "bloqueado"))
        # volta um processo NOVO na mesma porta: o vigia percebe e retoma
        p2, info2 = self.subir("revisao", K.GRUPOS_PADRAO["revisao"], porta=porta)
        self.assertNotEqual(info2["pid"], rev_pid)
        h.vigiar()
        self.assertEqual(h.esperar(pcid, 60), "concluido")
        self.assertIn("retomada_automatica", tipos(h, pcid))

    def test_chave_errada_nao_conversa(self):
        ws = {n: self.subir(n, neur)[1] for n, neur in K.GRUPOS_PADRAO.items()}
        c = CF.Config()
        c.aplicar({"modo": "distribuido", "workers": {n: {"url": i["url"]} for n, i in ws.items()}}, "teste")
        h = HB.Hub(c, self.pasta, vigia=False, token="chave-errada-mas-comprida-1234")
        self.addCleanup(h.encerrar, 2.0)
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "falha_de_modulo"))
        self.assertIn("recusada", d["bloqueio"]["texto"])

    def test_trabalhador_recusa_neuronio_que_so_roda_no_hub_e_falta_de_chave(self):
        for neur, token in ((["contexto"], TOKEN), (["aprendizagem"], TOKEN), (["percepcao"], None), (["percepcao"], "curta")):
            p, info = iniciar_trabalhador("x", neur, token=token)
            try:
                self.assertIn("erro", info, (neur, token))
                self.assertEqual(p.wait(10), 2)
            finally:
                parar(p)

    def test_os_mesmos_testes_do_contrato_valem_nos_dois_modos(self):                             # área 18 (compatibilidade)
        ws = {n: self.subir(n, neur)[1] for n, neur in K.GRUPOS_PADRAO.items()}
        hd = self.hub_distribuido(ws)
        hl = self.hub(pasta=tempfile.mkdtemp(prefix="pc-", dir=E.TMP))
        _, _, dd = self.rodar_ate(hd, PEDIDO, so_planejar=True)
        _, _, dl = self.rodar_ate(hl, PEDIDO, so_planejar=True)
        pd, pl = dd["planos"][-1]["plano"], dl["planos"][-1]["plano"]
        ign = ("hash", "gerado_em", "id", "objetivo", "escolha")
        self.assertEqual({k: v for k, v in pd.items() if k not in ign}.keys(), {k: v for k, v in pl.items() if k not in ign}.keys())
        self.assertEqual(pd["estrategia"], pl["estrategia"])
        self.assertEqual(pd["criterios_de_sucesso"], pl["criterios_de_sucesso"])


if __name__ == "__main__":
    unittest.main()
