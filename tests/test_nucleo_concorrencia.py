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
