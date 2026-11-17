"""Pub/sub de metadados: fan-out assíncrono, dedupe e isolamento dos pedidos."""
import time
import unittest
import _ambiente  # adiciona friday/ ao sys.path

import tempfile
import pre_cortex.contrato as C
import pre_cortex.transporte as TR
import pre_cortex.config as CF
import pre_cortex.hub as HB
from pre_cortex.neuronio import Neuronio


class Receptor(Neuronio):
    nome = "receptor"
    numero = 99
    papel = responsabilidade = entradas = saidas = confianca = "teste"


class Eventos(unittest.TestCase):
    def setUp(self):
        self.n = Receptor()
        self.w = TR.Worker("w", [self.n], max_paralelo=2)
        self.addCleanup(self.w.encerrar_pool)

    def evento(self, identificador=None):
        return C.criar("hub", "receptor", "notificar", {
            "evento": "fase_concluida", "fase": "planejamento", "ciclo": 2,
            "dados": {"estado": "ok"}
        }, correlacao="pc0001", tipo="evento", id=identificador)

    def test_evento_e_recebido_sem_bloquear_o_canal_de_pedidos(self):
        m = self.evento()
        r = self.w.processar(m)
        self.assertTrue(r["ok"])
        self.assertTrue(r["corpo"]["aceito"])
        limite = time.time() + 2
        while time.time() < limite and not self.n.eventos_recentes():
            time.sleep(0.01)
        self.assertEqual(self.n.eventos_recentes()[0]["evento"], "fase_concluida")
        self.assertEqual(self.n.eventos_recentes()[0]["dados"]["estado"], "ok")

    def test_evento_duplicado_nao_dispara_duas_vezes(self):
        m = self.evento()
        self.assertTrue(self.w.processar(m)["ok"])
        self.assertTrue(self.w.processar(m)["ok"])
        limite = time.time() + 2
        while time.time() < limite and not self.n.eventos_recentes():
            time.sleep(0.01)
        self.assertEqual(len(self.n.eventos_recentes()), 1)

    def test_eventos_nao_entram_na_cache_de_pedidos(self):
        self.w.processar(self.evento())
        self.assertEqual(len(self.w._vistos), 0)
        self.assertEqual(len(self.w._eventos_vistos), 1)

    def test_evento_atravessa_transporte_http_do_modo_distribuido(self):
        token = "token-de-evento-teste-123456"
        servidor = TR.ServidorHTTP(self.w, token, porta=0).iniciar()
        self.addCleanup(servidor.parar)
        destino = TR.DestinoHTTP("w", servidor.url, token)
        resposta = destino.enviar(self.evento(), 0.5)
        self.assertTrue(resposta["ok"])
        limite = time.time() + 2
        while time.time() < limite and not self.n.eventos_recentes():
            time.sleep(0.01)
        self.assertEqual(self.n.eventos_recentes()[0]["evento"], "fase_concluida")

    def test_hub_publica_metadados_para_todos_os_neuronios_locais(self):
        with tempfile.TemporaryDirectory() as pasta:
            hub = HB.Hub(CF.Config({"modo": "local"}), pasta=pasta, vigia=False)
            self.addCleanup(hub.encerrar)
            d = {"id": "pc0001", "fase": "planejamento", "ciclo": 1}
            hub._evento(d, "fase_concluida", estado="ok", texto="não deve ser distribuído")
            instancias = [n for w in hub.trabalhadores.values() for n in w.neuronios.values()]
            limite = time.time() + 3
            while time.time() < limite and not all(n.eventos_recentes() for n in instancias):
                time.sleep(0.01)
            self.assertEqual(len(instancias), 8)
            self.assertTrue(all(n.eventos_recentes() for n in instancias))
            self.assertTrue(all("texto" not in n.eventos_recentes()[0]["dados"] for n in instancias))


if __name__ == "__main__":
    unittest.main()
