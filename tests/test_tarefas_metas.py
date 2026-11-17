"""Fase 2 — tarefas e metas do pré-córtex (teste H da missão: metas relacionadas com texto DIFERENTE).

A meta fala em «sono»; a tarefa fala em «dormir bem». Nenhuma palavra em comum, e mesmo assim estão ligadas — porque a ligação é por ID, não por texto.
Quem conclui a meta é uma tarefa marcada para isso (`conclui_meta`) que terminou CONCLUÍDA com o efeito conferido. Tarefa que falhou, que foi executada sem
conferência, que ainda anda ou que é de outra meta não conclui nada; só mostra andamento (no máximo 90%).
"""
import unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import prefrontal as PFC, tarefas as T
from test_prefrontal import Base as BasePFC

SEGREDO = "zq-conteudo-particular-5520"


class Base(BasePFC):
    def setUp(self):
        super().setUp()
        T.reiniciar()
        self.addCleanup(T.reiniciar)

    def meta(self, tema="sono"):
        ok, m = PFC.nova_meta("aprender", tema=tema, agora=1000)
        self.assertTrue(ok, m)
        return m["id"]

    def passo(self, texto=SEGREDO):
        return {"descricao": "registrar o que aprendi", "ferramenta": "guardar_memoria", "args": {"texto": f"Aprendi que dormir bem ajuda a lembrar {texto}", "titulo": f"Dormir {texto}"}}

    def pensar(self):
        return PFC.pensar(agora=1100)


class TextosDiferentes(Base):
    def test_tarefa_conferida_conclui_a_meta_sem_palavras_em_comum(self):
        mid = self.meta("sono")
        tid = T.criar("entender como dormir bem ajuda a lembrar", passos=[self.passo()], meta=mid, conclui_meta=True)
        self.assertFalse(set(PFC.chave_tema("sono").split()) & set(PFC.chave_tema(T.obter(tid)["objetivo"]).split()), "nenhuma palavra em comum")
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        self.pensar()
        m = PFC.ARQ.get()["metas"][mid]
        self.assertEqual((m["estado"], m["progresso"]), ("cumprida", 1.0))
        self.assertIn("tarefa conferida", m["nota"])
        self.assertNotIn("estudo", m["nota"], "não foi um estudo, e a nota não finge que foi")

    def test_o_mesmo_texto_em_outra_meta_nao_conta(self):
        a, b = self.meta("sono"), self.meta("memória")
        tid = T.criar("dormir bem", passos=[self.passo()], meta=b, conclui_meta=True)
        T.executar(tid)
        self.pensar()
        metas = PFC.ARQ.get()["metas"]
        self.assertEqual((metas[a]["estado"], metas[b]["estado"]), ("ativa", "cumprida"))


class SoConcluiComEfeitoConferido(Base):
    def test_falso_sucesso_nao_conclui_a_meta(self):
        mid = self.meta()
        tid = T.criar("dormir bem", passos=[self.passo()], meta=mid, conclui_meta=True)
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": lambda **kw: "Guardei na memória."}):
            T.executar(tid)
        self.pensar()
        self.assertEqual(T.obter(tid)["estado"], T.FALHOU)
        self.assertEqual(PFC.ARQ.get()["metas"][mid]["estado"], "ativa")

    def test_executada_sem_conferencia_nao_conclui_a_meta(self):
        B.registrar("acao_cega_meta", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_meta", None)
        mid = self.meta()
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_meta", "args": {}}], meta=mid, conclui_meta=True)
        T.executar(tid)
        self.pensar()
        self.assertEqual(T.obter(tid)["estado"], T.EXECUTADA_SEM_VERIFICACAO)
        self.assertEqual(PFC.ARQ.get()["metas"][mid]["estado"], "ativa")

    def test_so_o_dono_confirmando_a_conferencia_conclui(self):
        B.registrar("acao_cega_meta", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_meta", None)
        mid = self.meta()
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_meta", "args": {}}], meta=mid, conclui_meta=True)
        T.executar(tid)
        T.confirmar_manual(tid)
        self.pensar()
        self.assertEqual(PFC.ARQ.get()["metas"][mid]["estado"], "cumprida")

    def test_tarefa_sem_a_marca_de_concluir_so_mostra_andamento(self):
        mid = self.meta()
        a = T.criar("dormir bem 1", passos=[self.passo("a")], meta=mid)
        T.criar("dormir bem 2", passos=[self.passo("b")], meta=mid)
        T.executar(a)
        self.pensar()
        m = PFC.ARQ.get()["metas"][mid]
        self.assertEqual(m["estado"], "ativa")
        self.assertEqual(m["progresso"], 0.45, "uma de duas tarefas: metade de 0,9")

    def test_andamento_nunca_passa_de_90_por_cento(self):
        mid = self.meta()
        a = T.criar("dormir bem", passos=[self.passo()], meta=mid)
        T.executar(a)
        self.pensar()
        m = PFC.ARQ.get()["metas"][mid]
        self.assertEqual((m["estado"], m["progresso"]), ("ativa", 0.9))

    def test_tarefa_em_andamento_ou_cancelada_nao_conclui(self):
        mid = self.meta()
        T.criar("dormir bem", passos=[self.passo()], meta=mid, conclui_meta=True)           # pronta, nunca executada
        c = T.criar("outra", passos=[self.passo("c")], meta=mid, conclui_meta=True)
        T.cancelar(c)
        self.pensar()
        self.assertEqual(PFC.ARQ.get()["metas"][mid]["estado"], "ativa")

    def test_meta_que_nao_e_de_aprender_nao_e_concluida_por_tarefa(self):
        ok, m = PFC.nova_meta("ver", alvo=10, agora=1000)
        tid = T.criar("x", passos=[self.passo()], meta=m["id"], conclui_meta=True)
        T.executar(tid)
        self.pensar()
        self.assertEqual(PFC.ARQ.get()["metas"][m["id"]]["estado"], "ativa", "«ver» se mede em coisas vistas, não em tarefas")

    def test_sem_tarefas_nada_muda(self):
        mid = self.meta()
        self.pensar()
        m = PFC.ARQ.get()["metas"][mid]
        self.assertEqual((m["estado"], m["progresso"]), ("ativa", 0.0))

    def test_pre_cortex_continua_funcionando_se_as_tarefas_quebram(self):
        mid = self.meta()
        with mock.patch.object(T, "resumo_por_meta", side_effect=OSError("disco")):
            self.pensar()
        self.assertEqual(PFC.ARQ.get()["metas"][mid]["estado"], "ativa")


if __name__ == "__main__":
    unittest.main()
