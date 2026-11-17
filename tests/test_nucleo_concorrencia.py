"""O núcleo é observacional: jamais serializa a execução distribuída."""
import threading
import unittest
from unittest import mock
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "friday"))
import nucleo as NC


class NucleoConcorrencia(unittest.TestCase):
    def setUp(self):
        NC.zerar_para_teste()

    def tearDown(self):
        NC.zerar_para_teste()

    def test_impulsos_independentes_nao_bloqueiam_uns_aos_outros(self):
        barreira = threading.Barrier(3)
        resultados = []

        def executar(nome):
            with NC.agir(nome):
                resultados.append((nome, NC.liberar(nome), NC.liberar("outro")))
                barreira.wait(timeout=2)

        ts = [threading.Thread(target=executar, args=(n,)) for n in ("estudar", "conversar")]
        for t in ts:
            t.start()
        barreira.wait(timeout=2)
        for t in ts:
            t.join(timeout=2)
        self.assertTrue(all(not t.is_alive() for t in ts))
        self.assertEqual(len(resultados), 2)
        self.assertTrue(all(pode and outro_pode for _, pode, outro_pode in resultados))

    def test_nucleo_nao_cria_fila_global_apos_atividade(self):
        with NC.agir("estudar"):
            self.assertTrue(NC.liberar("conversar"))
            self.assertTrue(NC.liberar("olhar"))
        self.assertTrue(NC.liberar("sonhar"))

    def test_atencao_registra_sinal_sem_guardar_texto_do_usuario(self):
        s = NC.perceber("fala", "pedido", "pedido recebido", chave="fala:pedido", agora=1000)
        self.assertTrue(s["notado"])
        self.assertEqual(s["resumo"], "pedido recebido")
        self.assertNotIn("texto", s)

    def test_nucleo_desligado_nao_adiciona_sinais_ao_foco(self):
        with mock.patch.dict("os.environ", {"NUCLEO": "0"}):
            s = NC.perceber("fala", "pedido", "pedido recebido", chave="desligado", agora=1000)
        self.assertFalse(s["notado"])
        self.assertEqual(NC.foco(1000), [])


if __name__ == "__main__":
    unittest.main()


class SistemaDistribuidoDentroDoNucleo(unittest.TestCase):
    """Pedido do dono: o sistema distribuído nasce junto com o núcleo, sempre ligado; o ciclo autônomo gira, mas só age com a autonomia total ligada."""
    def setUp(self):
        self.antes = dict(NC._ini)
        NC._ini.update(feito=False, hub=None, erro="")
        self.addCleanup(lambda: NC._ini.update(self.antes))

    def test_iniciar_sobe_o_hub_e_o_ciclo_uma_vez_so(self):
        import pre_cortex.fachada as PC
        with mock.patch.object(PC, "hub") as hub, mock.patch.object(NC.threading, "Thread") as linha:
            r = NC.iniciar()
            NC.iniciar()
        hub.assert_called_once()
        linha.assert_called_once()
        self.assertEqual(linha.call_args.kwargs["target"], NC._laco_autonomo)
        self.assertTrue(r["hub"])
        self.assertTrue(NC.painel()["distribuido"]["hub"])

    def test_erro_no_hub_nao_derruba_a_partida(self):
        import pre_cortex.fachada as PC
        with mock.patch.object(PC, "hub", side_effect=RuntimeError("sem pasta")), mock.patch.object(NC.threading, "Thread"):
            r = NC.iniciar()
        self.assertFalse(r["hub"])
        self.assertIn("sem pasta", NC.painel()["distribuido"]["erro"])

    def test_assinar_duas_vezes_nao_duplica(self):
        NC.zerar_para_teste()
        recebidos = []
        f = recebidos.append
        NC.assinar(ao_entrar=f); NC.assinar(ao_entrar=f)
        NC.perceber("fala", "pedido", chave="x:1")
        self.assertEqual(len(recebidos), 1)
        NC.zerar_para_teste()
