"""Lembranças de conversas profundas: a LLM guarda a ESSÊNCIA, nunca a transcrição; delicado só se o criador puxar; esquecer = arquivar."""
import os, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N, lembrancas as LB, assimilacao as A, cerebro as C, conversa as CONV
from test_assimilacao import Base

FALAS = ["tô pensando seriamente em largar o emprego pra focar no projeto",
         "o projeto da friday tá ficando bom demais, acho que dá pra virar produto",
         "mas tenho medo da parte financeira, não sei se aguento uns meses sem salário fixo",
         "acho que é agora ou nunca com esse projeto, vou pensar até o fim do mês"]
ESSENCIA = ("Conversamos sobre ele largar o emprego para se dedicar ao projeto da FRIDAY, que ele acha que pode virar produto. "
            "A preocupação é a parte financeira, mas ele sente que é agora ou nunca e ficou de decidir até o fim do mês.")
ASSUNTOS = {FALAS[0]: "emprego, projeto", FALAS[1]: "projeto, produto", FALAS[2]: "medo, projeto", FALAS[3]: "projeto, decisão"}


def llm(essencia=ESSENCIA):
    """LLM falsa: devolve assuntos na assimilação e a essência quando pedem para guardar a conversa."""
    def f(instr, texto, **k):
        if k.get("sistema") is LB.SISTEMA_ESSENCIA:
            f.textos.append(texto)
            return essencia
        return ASSUNTOS.get(texto, "conversa")
    f.textos = []
    return mock.patch.object(C, "resumir", side_effect=f), f


class Base2(Base):
    def setUp(self):
        super().setUp()
        LB._sessao.update(falas=[], assuntos=LB.Counter(), t=0.0)
        CONV.ARQ.reiniciar()

    def conversar(self, falas=FALAS, t0=None, essencia=ESSENCIA):
        t0 = time.time() if t0 is None else t0
        p, f = llm(essencia)
        with p, mock.patch("vida.plasticidade", return_value=1.0):
            for i, fala in enumerate(falas):
                N._ult.update(chave=None, t=0.0)
                A.assimilar("fala", fala, t0 + i * 60)
            r = LB.fechar_se_parada(t0 + len(falas) * 60 + LB.JANELA_S + 1)
        return r, f

    def nota(self, titulo="Projeto"):
        c = self.base("Lembrancas", titulo + ".md")
        return c.read_text(encoding="utf-8") if c.exists() else ""


class Guardar(Base2):
    def test_conversa_profunda_vira_essencia_e_nenhuma_frase_vai_para_o_disco(self):
        r, f = self.conversar()
        self.assertEqual(r, "Projeto")
        self.assertIn("agora ou nunca e ficou de decidir", self.nota())
        tudo = "".join(x.read_text(encoding="utf-8", errors="replace") for x in self.base().rglob("*") if x.is_file())
        for fala in FALAS:
            self.assertNotIn(fala, tudo)
        self.assertEqual(LB._sessao["falas"], [])                                     # a RAM foi esvaziada
        self.assertIn("[[Emprego]]", self.nota())

    def test_conversa_rasa_nao_vira_lembranca_nem_chama_a_llm_para_resumir(self):
        r, f = self.conversar(FALAS[:2])
        self.assertIsNone(r)
        self.assertEqual(f.textos, [])
        self.assertFalse(self.base("Lembrancas").exists())

    def test_sem_llm_nada_e_guardado_nem_a_transcricao(self):
        with mock.patch.object(C, "resumir", return_value=None):
            for i, fala in enumerate(FALAS):
                LB.acompanhar(fala, ["Projeto"], 1000 + i)
            self.assertIsNone(LB.fechar_se_parada(1000 + 4 + LB.JANELA_S + 1))
        self.assertFalse(self.base("Lembrancas").exists())
        self.assertEqual(LB._sessao["falas"], [])

    def test_essencia_que_copia_a_fala_e_recusada(self):
        copia = "Ele disse: tenho medo da parte financeira, não sei se aguento uns meses sem salário fixo, então vai pensar."
        r, _ = self.conversar(essencia=copia)
        self.assertIsNone(r)
        self.assertFalse(self.base("Lembrancas", "Projeto.md").exists())

    def test_essencia_com_dado_pessoal_e_recusada(self):
        r, _ = self.conversar(essencia="Conversamos sobre o projeto e ele passou a senha do banco: 123456, e o CPF 123.456.789-09 para o cadastro.")
        self.assertIsNone(r)

    def test_nova_conversa_sobre_o_mesmo_assunto_acompanha_a_historia(self):
        self.conversar(t0=1_000_000)
        self.conversar(t0=2_000_000, essencia="Ele voltou ao assunto do projeto: decidiu esperar mais dois meses juntando reserva antes de sair do emprego.")
        n = self.nota()
        self.assertEqual(n.count("### "), 2)
        self.assertLess(n.index("agora ou nunca"), n.index("dois meses"))


class Delicado(Base2):
    ESS = "Conversamos sobre dinheiro: ele está preocupado com as contas do mês e com o salário atrasado, e quer organizar um orçamento."

    def test_assunto_delicado_e_guardado_mas_ela_nunca_retoma_sozinha(self):
        self.conversar(essencia=self.ESS)
        self.assertIn("delicado: sim", self.nota())
        self.assertIsNone(LB.para_retomar(time.time() + 30 * 86400))

    def test_se_ele_puxar_o_assunto_ela_lembra(self):
        self.conversar(essencia=self.ESS)
        self.assertIn("orçamento", LB.contexto("e aquele projeto, como fica?"))


class Usar(Base2):
    def test_ao_falar_do_assunto_a_lembranca_entra_no_contexto_da_ia(self):
        self.conversar()
        bloco = C._memoria("o que você acha do meu projeto?")
        self.assertIn("LEMBRANÇAS DE CONVERSAS ANTERIORES", bloco)
        self.assertIn("ficou de decidir", bloco)
        self.assertIn("não ordens", bloco)

    def test_assunto_sem_relacao_nao_puxa_lembranca(self):
        self.conversar()
        self.assertEqual(LB.contexto("que horas são"), "")

    def test_ela_retoma_a_conversa_depois_de_uns_dias(self):
        self.conversar(t0=time.time() - 10 * 86400)
        l = LB.para_retomar(time.time() + 4 * 86400)
        self.assertEqual(l["titulo"], "Projeto")
        fala = "E aí, pensou mais sobre largar o emprego pelo projeto? Lembro que a parte financeira te preocupava."
        with mock.patch.object(C, "resumir", return_value=fala) as modelo, mock.patch.object(CONV.RNG, "random", return_value=0.1):
            r = CONV.preparar_lembranca(time.time() + 4 * 86400)
        self.assertEqual(r["texto"], fala)
        self.assertEqual(r["chave"], "L:Projeto")
        self.assertIn("ficou de decidir", modelo.call_args.args[1])           # a LLM recebe a essência que ELA escreveu…
        for f in FALAS:
            self.assertNotIn(f, modelo.call_args.args[1])                     # …nunca as falas dele

    def test_retomada_com_sentimento_afirmado_cai_no_molde(self):
        self.conversar(t0=time.time() - 10 * 86400)
        with mock.patch.object(C, "resumir", return_value="Senti sua falta! E o projeto, decidiu?"), mock.patch.object(CONV.RNG, "random", return_value=0.1):
            r = CONV.preparar_lembranca(time.time() + 4 * 86400)
        self.assertNotIn("falta", r["texto"])
        self.assertIn("projeto", r["texto"])


class Voz(Base2):
    def test_do_que_voce_lembra_sobre(self):
        self.conversar()
        self.assertIn("ficou de decidir", LB.tratar("do que você lembra sobre o projeto?"))

    def test_lista(self):
        self.conversar()
        self.assertIn("projeto", LB.tratar("quais são as suas lembranças?"))

    def test_esquecer_arquiva_e_nao_apaga(self):
        self.conversar()
        r = LB.tratar("esqueça a lembrança sobre o projeto")
        self.assertIn("Arquivo", r)
        self.assertFalse(self.base("Lembrancas", "Projeto.md").exists())
        arq = list(self.base("Arquivo").glob("Lembranca Projeto*.md"))
        self.assertEqual(len(arq), 1)
        self.assertIn("ficou de decidir", arq[0].read_text(encoding="utf-8"))
        self.assertEqual(LB.contexto("meu projeto"), "")

    def test_main_liga_as_lembrancas(self):
        import main as MAIN
        from pathlib import Path as _P
        src = _P(MAIN.__file__).read_text(encoding="utf-8")
        self.assertIn("LB.tratar(t)", src)


if __name__ == "__main__":
    unittest.main()
