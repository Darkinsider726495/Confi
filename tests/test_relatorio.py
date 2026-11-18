"""Relatório de evolução: números de verdade, comparação com ontem, investigação do que deu errado, nada pessoal."""
import json, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import relatorio as R, memoria as MEM, curiosidade as CUR
from test_assimilacao import Base, ia
import assimilacao as A


class Relatorio(Base):
    def test_numeros_e_comparacao_com_ontem(self):
        ontem = {"dia": "2000-01-01", "neuronios": 0, "sinapses": 0, "estudos": 0}
        R._arq().parent.mkdir(parents=True, exist_ok=True)
        R._arq().write_text(json.dumps(ontem) + "\n", encoding="utf-8")
        with ia("banco de dados, prova, joins"):
            A.assimilar("fala", "amanhã tenho prova de banco de dados com joins")
        MEM.guardar_estudo("fases do sono", "O sono tem fases que se repetem durante a noite. A fase profunda ajuda a memória.", ["sono.example"])
        n = R.registrar()
        self.assertGreater(n["neuronios"], 0)
        txt = R.relatorio(n)
        self.assertIn(f"Neurônios: {n['neuronios']} (+{n['neuronios']})", txt)
        self.assertIn("Estudos: 1 (+1)", txt)
        self.assertTrue(self.base("Eu", "Evolução.md").exists())
        self.assertEqual(len(R.historico()), 2)
        R.registrar()
        self.assertEqual(len(R.historico()), 2)                      # um registro por dia (o de hoje é atualizado)

    def test_investiga_o_que_deu_errado(self):
        p = R.investigar({"estudos_falhas": 3, "ia_hoje": 195, "ia_limite": 200, "backup_dias": None, "rotina": "aprendendo", "curiosidade": False})
        txt = " ".join(p)
        for pedaco in ("3 estudos seguidos falharam", "195 de 200", "faça um backup", "jeito simples", "curiosidade está desligada"):
            self.assertIn(pedaco, txt)
        self.assertEqual(R.investigar({"estudos_falhas": 0, "ia_hoje": 1, "ia_limite": 200, "backup_dias": 1, "rotina": "confiavel", "curiosidade": True}), [])

    def test_nada_pessoal_no_registro(self):
        with ia("banco de dados"):
            A.assimilar("fala", "meu CPF é 123.456.789-09 e a prova de banco de dados é amanhã")
        R.registrar()
        disco = R._arq().read_text(encoding="utf-8") + self.base("Eu", "Evolução.md").read_text(encoding="utf-8")
        self.assertNotIn("123.456", disco)
        self.assertNotIn("prova", disco.lower())

    def test_por_voz_e_uma_vez_por_dia(self):
        self.assertIn("Relatório de evolução", R.tratar("Friday, como você evoluiu?"))
        R._feito["dia"] = ""
        with mock.patch.object(R, "registrar") as reg:
            R.gancho(); R.gancho()
        self.assertEqual(reg.call_count, 1)
        import inspect
        self.assertNotIn("registrar(\"", inspect.getsource(R).replace("def registrar(", ""))   # o relatório não cria ferramenta da IA


if __name__ == "__main__":
    unittest.main()
