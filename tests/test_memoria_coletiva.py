"""Testes da memória coletiva persistente e da reconstrução de contexto."""
import json
import os
import tempfile
import unittest
import _ambiente
from pre_cortex.memoria_coletiva import MemoriaColetiva, projetar_evento
import pre_cortex.hub as HB
import pre_cortex.config as CF

class MemoriaColetivaTest(unittest.TestCase):
    def test_nao_persiste_texto_livre_ou_segredos(self):
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d)
            m.registrar({"seq": 1, "objetivo": "pc0001", "tipo": "fase_concluida", "fase": "planejamento", "ciclo": 1, "texto": "segredo", "token": "abc", "estado": "ok"})
            m.flush()
            with open(os.path.join(d, "memoria_coletiva.json"), encoding="utf-8") as f:
                bruto = f.read()
            self.assertNotIn("segredo", bruto); self.assertNotIn("abc", bruto)
            self.assertEqual(m.resumo()["tipos"]["fase_concluida"], 1)
            m.encerrar()

    def test_aprende_transicoes_sem_mudar_politicas(self):
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d)
            m.registrar({"seq": 1, "objetivo": "pc0001", "tipo": "fase_iniciada"})
            m.registrar({"seq": 2, "objetivo": "pc0001", "tipo": "fase_concluida"})
            self.assertEqual(m.resumo()["transicoes"]["fase_iniciada->fase_concluida"], 1)
            m.encerrar()

    def test_mapeia_conexoes_reais_entre_neuronios(self):
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d)
            m.registrar({"seq": 1, "objetivo": "pc0003", "tipo": "mensagem_enviada", "para": "percepcao"})
            m.registrar({"seq": 2, "objetivo": "pc0003", "tipo": "mensagem_enviada", "para": "planejamento"})
            self.assertEqual(m.resumo()["conexoes_neuronios"]["percepcao->planejamento"], 1)
            m.encerrar()

    def test_hub_reconstroi_contexto_local_apos_reiniciar(self):
        with tempfile.TemporaryDirectory() as d:
            h1 = HB.Hub(CF.Config({"modo": "local"}), pasta=d, vigia=False)
            h1._evento({"id": "pc0001", "fase": "planejamento", "ciclo": 1},
                       "fase_concluida", estado="ok", texto="não distribuir")
            h1.encerrar()
            h2 = HB.Hub(CF.Config({"modo": "local"}), pasta=d, vigia=False)
            try:
                neuronios = [n for w in h2.trabalhadores.values() for n in w.neuronios.values()]
                self.assertTrue(any(any(e["evento"] == "fase_concluida" for e in n.eventos_recentes(32)) for n in neuronios))
                self.assertTrue(all("texto" not in e["dados"] for n in neuronios for e in n.eventos_recentes(32)))
            finally:
                h2.encerrar()

    def test_worker_distribuido_recebe_replay_quando_pid_muda(self):
        class DestinoFake:
            tipo = "fake"
            nome = "cognicao"
            def __init__(self):
                self.pid = 111
                self.enviadas = []
            def saude(self):
                return {"pid": self.pid, "iniciado_em": self.pid, "neuronios": {}}
            def enviar(self, msg, timeout_s):
                self.enviadas.append(msg)
                return {"ok": True}
            def cancelar(self, correlacao):
                return 0
        with tempfile.TemporaryDirectory() as d:
            h = HB.Hub(CF.Config({"modo": "local"}), pasta=d, vigia=False)
            try:
                h._evento({"id": "pc0004", "fase": "percepcao", "ciclo": 1}, "fase_concluida", estado="ok")
                fake = DestinoFake()
                h.destinos["cognicao"] = fake
                h.rot.destinos["cognicao"] = fake
                for nome, destino in list(h.rot.rotas.items()):
                    if destino.nome == "cognicao":
                        h.rot.rotas[nome] = fake
                h.atualizar_saude()
                primeiro = len(fake.enviadas)
                self.assertGreater(primeiro, 0)
                h.atualizar_saude()
                self.assertEqual(len(fake.enviadas), primeiro)
                fake.pid = 222
                h.atualizar_saude()
                self.assertGreater(len(fake.enviadas), primeiro)
            finally:
                h.encerrar()

    def test_recarrega_agregados(self):
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d); m.registrar({"seq": 4, "objetivo": "pc0002", "tipo": "recuperado"})
            m.flush()
            n = MemoriaColetiva(d)
            self.assertEqual(n.resumo()["tipos"]["recuperado"], 1)
            n.encerrar()

    def test_projecao_remove_campos_nao_permitidos(self):
        e = projetar_evento({"tipo": "fase_concluida", "texto": "não", "dados": {"estado": "ok", "plano": "não", "acao": "avaliar"}})
        self.assertEqual(e["dados"], {"estado": "ok", "acao": "avaliar"})

if __name__ == "__main__": unittest.main()
