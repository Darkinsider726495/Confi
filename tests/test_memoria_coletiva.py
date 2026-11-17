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

    def test_falha_na_gravacao_nao_apaga_nada_e_preserva_o_indice(self):
        """Regra «nunca apague»: se gravar falhar, o índice anterior continua válido e nenhum arquivo some."""
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d)
            m.registrar({"seq": 1, "objetivo": "pc0001", "tipo": "fase_iniciada"})
            self.assertTrue(m.flush())
            arq = os.path.join(d, "memoria_coletiva.json")
            with open(arq, encoding="utf-8") as f:
                antes = f.read()
            m.registrar({"seq": 2, "objetivo": "pc0001", "tipo": "fase_concluida"})
            with mock.patch("pre_cortex.memoria_coletiva.os.replace", side_effect=OSError("disco cheio")), \
                 mock.patch("os.unlink") as unlink, mock.patch("os.remove") as remove:
                self.assertFalse(m.flush())
            unlink.assert_not_called(); remove.assert_not_called()
            self.assertGreaterEqual(m.erros, 1)   # o gravador de fundo também pode ter tentado durante a falha
            self.assertIn("disco cheio", m.ultimo_erro)
            with open(arq, encoding="utf-8") as f:
                self.assertEqual(f.read(), antes)
            self.assertTrue(m.flush())          # a próxima gravação sobrescreve o .tmp e conclui
            self.assertEqual(json.load(open(arq, encoding="utf-8"))["tipos"]["fase_concluida"], 1)
            m.encerrar()

    def test_gravacoes_concorrentes_nao_corrompem_o_indice(self):
        """Gravador de fundo + flush explícito de várias threads: o arquivo final é JSON válido e completo."""
        import threading
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d)
            def trabalho(base):
                for i in range(50):
                    m.registrar({"seq": base + i, "objetivo": f"pc{base}", "tipo": "fase_concluida"})
                    m.flush()
            ts = [threading.Thread(target=trabalho, args=(k * 1000,)) for k in range(4)]
            for t in ts: t.start()
            for t in ts: t.join()
            self.assertTrue(m.flush())
            self.assertEqual(m.erros, 0)
            with open(os.path.join(d, "memoria_coletiva.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["tipos"]["fase_concluida"], 200)
            m.encerrar()

    def test_estado_por_objetivo_nao_cresce_sem_fim_e_contagens_ficam(self):
        with tempfile.TemporaryDirectory() as d:
            m = MemoriaColetiva(d, max_objetivos=50)
            for i in range(200):
                m.registrar({"seq": 2 * i + 1, "objetivo": f"pc{i:04d}", "tipo": "fase_iniciada"})
                m.registrar({"seq": 2 * i + 2, "objetivo": f"pc{i:04d}", "tipo": "fase_concluida"})
            self.assertEqual(len(m._ultimos), 50)
            self.assertIn("pc0199", m._ultimos); self.assertNotIn("pc0000", m._ultimos)       # ficam os mais recentes
            r = m.resumo()
            self.assertEqual(r["tipos"]["fase_concluida"], 200)                                # o aprendido não se perde
            self.assertEqual(r["transicoes"]["fase_iniciada->fase_concluida"], 200)
            self.assertTrue(m.flush()); m.encerrar()
            m2 = MemoriaColetiva(d, max_objetivos=50)                                           # recarrega na mesma ordem de recência
            self.assertEqual(list(m2._ultimos)[-1], "pc0199")
            self.assertEqual(len(m2._ultimos), 50)
            m2.encerrar()

    def test_projecao_leva_seq_para_deduplicar(self):
        e = projetar_evento({"seq": 42, "objetivo": "pc1", "tipo": "fase_concluida", "texto": "segredo"})
        self.assertEqual(e["seq"], 42)
        self.assertNotIn("segredo", json.dumps(e))

    def test_neuronio_nao_duplica_evento_vindo_ao_vivo_e_pelo_replay(self):
        from pre_cortex.neuronio import Neuronio
        n = Neuronio.__new__(Neuronio)
        ev = {"evento": "fase_concluida", "fase": "x", "ciclo": 1, "dados": {}, "emitido_em": 1.0, "seq": 7}
        n.receber_evento(dict(ev), None)        # ao vivo
        n.receber_evento(dict(ev), None)        # replay do mesmo evento
        n.receber_evento(dict(ev, seq=8), None)
        n.receber_evento({"evento": "sem_seq"}, None)   # evento antigo sem seq continua aceito
        n.receber_evento({"evento": "sem_seq"}, None)
        self.assertEqual([e.get("seq") for e in n.eventos_recentes(10)], [7, 8, None, None])

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
