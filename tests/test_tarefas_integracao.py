"""Fase 2 — as tarefas ligadas ao resto: laço da IA (nuvem e local), voz (`main.processar`) e painel.

A IA continua só PROPONDO: cada chamada de ferramenta dela passa pelo corretor como sempre. A diferença é que, se a ação muda algo, o efeito é conferido e,
quando a ferramenta disse «feito» e o efeito não existe, a IA recebe o aviso na resposta da própria ferramenta — antes de falar com o usuário.
"""
import json, os, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import cerebro as C, ferramentas as F, main as MAIN, tarefas as T
from test_neuronios import Cerebro as BaseCofre, BIN, LOG

SEGREDO = "zq-conteudo-particular-3310"


def resultados_de_ferramenta(chamada):
    """O que a IA recebeu como resultado de ferramenta numa chamada à API (a lista de mensagens é a mesma que o laço foi enchendo, então varre tudo)."""
    msgs = chamada.kwargs["json"]["messages"]
    return [b["content"] for m in msgs if isinstance(m["content"], list) for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]


def resposta(corpo):
    return mock.Mock(json=mock.Mock(return_value=corpo), raise_for_status=mock.Mock())


def uso_de_ferramenta(nome, entrada, id_="t1"):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": id_, "name": nome, "input": entrada}]}


FIM = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Certo, chefe."}]}


class Base(BaseCofre):
    def setUp(self):
        super().setUp()
        T.reiniciar()
        self.addCleanup(T.reiniciar)
        C.HIST.clear()
        self.m_lemb = F.marca_lembretes()

    def lembretes(self, texto=SEGREDO):
        return [r for r in F.lembretes_depois(self.m_lemb) if r[1] == texto]

    def nuvem(self, *respostas):
        """Roda uma pergunta pelo laço da nuvem com as respostas simuladas; devolve (texto, o que a IA recebeu na 2ª chamada)."""
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x", "IA_MODO": "nuvem"}), mock.patch("requests.post", side_effect=[resposta(r) for r in respostas]) as p:
            texto = C.responder("pedido de teste")
        return texto, p


class LacoDaNuvem(Base):
    def test_efeito_confirmado_a_ia_recebe_o_texto_de_sempre(self):
        texto, p = self.nuvem(uso_de_ferramenta("criar_lembrete", {"minutos": 5, "texto": SEGREDO}), FIM)
        self.assertEqual(resultados_de_ferramenta(p.call_args_list[1]), ["Lembrete criado para daqui a 5 minutos."])
        self.assertEqual(len(self.lembretes()), 1)
        self.assertEqual([t["estado"] for t in T.listar() if t["contexto"]["origem"] == "ia"], [T.CONCLUIDA])

    def test_ferramenta_mente_a_ia_recebe_o_aviso(self):
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 5 minutos."}):
            texto, p = self.nuvem(uso_de_ferramenta("criar_lembrete", {"minutos": 5, "texto": SEGREDO}), FIM)
        recebido = resultados_de_ferramenta(p.call_args_list[1])[0]
        self.assertIn("Lembrete criado", recebido)
        self.assertIn("NÃO encontrei", recebido)
        self.assertEqual(self.lembretes(), [])
        self.assertEqual([t["estado"] for t in T.listar() if t["contexto"]["origem"] == "ia"], [T.FALHOU])

    def test_leitura_nao_cria_tarefa(self):
        self.nuvem(uso_de_ferramenta("hora_data", {}), FIM)
        self.assertEqual(T.listar(), [])

    def test_a_trilha_do_corretor_continua_a_mesma(self):
        self.nuvem(uso_de_ferramenta("criar_lembrete", {"minutos": 5, "texto": SEGREDO}), FIM)
        with open(B.AUDITORIA, encoding="utf-8") as f:
            txt = f.read()
        self.assertNotIn(SEGREDO, txt)
        self.assertEqual(B.verificar_auditoria(), (True, 1), "uma ação, uma linha: a tarefa não executa nada por fora do corretor")

    def test_acao_sensivel_proposta_pela_ia_espera_o_dono(self):
        sms0 = E.ler_log(LOG).count("CMD termux-sms-send")
        self.nuvem(uso_de_ferramenta("enviar_sms", {"contato": "mae", "texto": SEGREDO}), FIM)
        tarefa = [t for t in T.listar() if t["contexto"]["origem"] == "ia"][-1]
        self.assertEqual(tarefa["estado"], T.BLOQUEADA)
        for fala in ("sim", "pode", "isso mesmo"):
            MAIN.processar(fala)
        self.assertEqual(E.ler_log(LOG).count("CMD termux-sms-send"), sms0, "resposta vaga nunca executa")
        MAIN.processar("confirmo")
        self.assertEqual(E.ler_log(LOG).count("CMD termux-sms-send"), sms0 + 1)
        self.assertEqual(T.obter(tarefa["id"])["estado"], T.EXECUTADA_SEM_VERIFICACAO)


class LacoLocal(Base):
    def test_modelo_local_tambem_passa_pelo_registro(self):
        r1 = {"message": {"content": "", "tool_calls": [{"function": {"name": "criar_lembrete", "arguments": {"minutos": 5, "texto": SEGREDO}}}]}}
        r2 = {"message": {"content": "Certo, chefe."}}
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 5 minutos."}), \
                mock.patch("requests.post", side_effect=[resposta(r1), resposta(r2)]) as p:
            self.assertEqual(C._local([], "pedido"), "Certo, chefe.")
        recebido = p.call_args_list[1].kwargs["json"]["messages"][-1]["content"]
        self.assertIn("NÃO encontrei", recebido)
        self.assertEqual([t["estado"] for t in T.listar() if t["contexto"]["origem"] == "ia"], [T.FALHOU])


class ExperienciasNaVozENoPainel(Base):
    def setUp(self):
        super().setUp()
        import experiencias as X
        X.reiniciar()
        self.addCleanup(X.reiniciar)

    def test_a_pergunta_chega_nas_experiencias_antes_da_ia(self):
        with mock.patch("cerebro.responder", side_effect=AssertionError("não devia chamar a IA")):
            self.assertIn("Ainda não tenho", MAIN.processar("o que você aprendeu com as tarefas?"))
            tid = T.criar("lembrar de beber água", passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": SEGREDO}}])
            T.executar(tid)
            fala = MAIN.processar("minhas experiências")
        self.assertIn("1 experiência", fala)
        self.assertNotIn(SEGREDO, fala)

    def test_painel_mostra_so_contagens_de_experiencias(self):
        tid = T.criar("lembrar de beber água", passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": SEGREDO}}])
        T.executar(tid)
        r = MAIN.estado_completo(painel=False)["experiencias"]
        self.assertEqual((r["total"], r["sucesso"]), (1, 1))
        self.assertNotIn(SEGREDO, json.dumps(r))


class ObjetivosNaVozENoPainel(Base):
    """Objetivos que ELA propõe: aparecem na voz e no painel; só a frase explícita do dono aprova e a IA nunca é consultada para isso."""

    def setUp(self):
        super().setUp()
        import experiencias as X, objetivos as O
        self.O = O
        X.reiniciar(), O.reiniciar()
        self.addCleanup(X.reiniciar)
        self.addCleanup(O.reiniciar)

    def duas_falhas(self):
        for _ in range(2):
            with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": lambda **kw: "Guardei."}):
                tid = T.criar("guardar uma coisa", passos=[{"descricao": "guardar", "ferramenta": "guardar_memoria", "args": {"texto": SEGREDO}}])
                T.executar(tid)

    def test_a_pergunta_e_a_decisao_chegam_antes_da_ia(self):
        with mock.patch("cerebro.responder", side_effect=AssertionError("não devia chamar a IA")):
            self.assertIn("nenhum objetivo", MAIN.processar("quais objetivos você propõe?"))
            self.duas_falhas()
            fala = MAIN.processar("quais objetivos você propõe?")
            self.assertIn("guardar_memoria", fala)
            self.assertNotIn(SEGREDO, fala)
            self.assertEqual(self.O.obter("o01")["estado"], "proposto")
            self.assertIn("Pronto", MAIN.processar("aprova o objetivo 1"))
        self.assertEqual(self.O.obter("o01")["estado"], "concluido")

    def test_sim_ou_pode_nao_aprovam_e_vao_para_a_ia_como_conversa(self):
        self.duas_falhas()
        with mock.patch("cerebro.responder", return_value="Certo, chefe.") as ia:
            for frase in ("sim", "pode", "pode fazer"):
                self.assertEqual(MAIN.processar(frase), "Certo, chefe.")
        self.assertEqual(ia.call_count, 3)
        self.assertEqual(self.O.obter("o01")["estado"], "proposto")
        self.assertEqual([t for t in T.listar() if t["contexto"]["origem"] == "propria"], [])

    def test_painel_mostra_so_contagens_de_objetivos(self):
        self.duas_falhas()
        r = MAIN.estado_completo(painel=False)["objetivos"]
        self.assertEqual((r["propostas"], r["executando"], r["concluidos"]), (1, 0, 0))
        self.assertNotIn(SEGREDO, json.dumps(r))


class Coordenacao(Base):
    """Fase 5 — o coordenador chega pela voz e pelo painel, e a reserva está ligada (importar `main` liga `T.RESERVAS`)."""

    def test_a_reserva_esta_ligada_ao_importar_main(self):
        import coordenador as CO
        self.assertIs(T.RESERVAS["reservar"], CO.reservar)
        self.assertIs(T.RESERVAS["liberar"], CO.liberar)

    def test_a_pergunta_chega_antes_da_ia_e_so_le(self):
        import coordenador as CO
        CO.reiniciar()
        self.addCleanup(CO.reiniciar)
        with mock.patch("cerebro.responder", side_effect=AssertionError("não devia chamar a IA")):
            self.assertIn("Não coordenei nada", MAIN.processar("o que você está coordenando?"))
            CO.avaliar([{"id": "t0001", "modulo": "tarefas", "relevancia": 1, "urgencia": 1, "custo": 0, "risco": 0, "incerteza": 0, "depende_de": ["t0000"]}])
            fala = MAIN.processar("O que você está coordenando?")
        self.assertIn("t0001: esperar", fala)
        self.assertIn("t0000", fala)

    def test_painel_mostra_so_contagens(self):
        import coordenador as CO
        CO.reiniciar()
        self.addCleanup(CO.reiniciar)
        CO.reservar("t0001", "enviar_sms", {"contato": SEGREDO, "texto": "oi"})
        r = MAIN.estado_completo(painel=False)["coordenacao"]
        self.assertEqual(r, {"reservas": 1, "erros": 0})
        self.assertNotIn(SEGREDO, json.dumps(MAIN.estado_completo(painel=False)["coordenacao"]))


class Retomada(Base):
    """Fase 6 — a retomada chega pela voz e pelo painel, e roda uma vez ao ligar."""

    def test_a_pergunta_e_o_comando_chegam_antes_da_ia(self):
        with mock.patch("cerebro.responder", side_effect=AssertionError("não devia chamar a IA")):
            self.assertIn("Não achei nada interrompido", MAIN.processar("retoma o que ficou pendente"))
            self.assertIn("0 tarefa(s) paradas no meio", MAIN.processar("o que ficou interrompido?"))
            tid = T.criar("lembrar", passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": SEGREDO}}])
            fala = MAIN.processar("continua de onde parou")
        self.assertIn("retomei 1", fala)
        self.assertNotIn(SEGREDO, fala)
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA, "o efeito do lembrete foi conferido por fora")

    def test_painel_mostra_so_contagens(self):
        import retomada as RET
        T.criar("lembrar de beber água " + SEGREDO, passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": "zzz"}}])
        RET.retomar_pendentes()
        r = MAIN.estado_completo(painel=False)["retomada"]
        self.assertEqual(set(r), {"interrompidas", "ultima", "erros"})
        self.assertNotIn(SEGREDO, json.dumps(r))

    def test_ao_ligar_retoma_e_depois_reconcilia_os_objetivos(self):
        ordem = []
        with mock.patch("retomada.ao_iniciar", side_effect=lambda f: ordem.append("retomada")), mock.patch("objetivos.conciliar", side_effect=lambda: ordem.append("conciliar")):
            MAIN._retomar_ao_iniciar()
        self.assertEqual(ordem, ["retomada", "conciliar"])

    def test_ao_ligar_falha_na_conciliacao_nao_derruba(self):
        with mock.patch("retomada.ao_iniciar"), mock.patch("objetivos.conciliar", side_effect=RuntimeError("x")):
            MAIN._retomar_ao_iniciar()

    def test_o_dono_pode_desligar_a_retomada_automatica_no_env(self):
        with open(MAIN.__file__, encoding="utf-8") as f:
            fonte = f.read()
        self.assertIn('os.getenv("FRIDAY_RETOMADA", "1")', fonte)
        self.assertIn("RET.tratar(t)", fonte, "e por voz continua disponível")


class PorVoz(Base):
    def test_o_comando_chega_nas_tarefas_antes_da_ia(self):
        with mock.patch("cerebro.responder", side_effect=AssertionError("não devia chamar a IA")):
            self.assertEqual(MAIN.processar("quais são as minhas tarefas"), "Nenhuma tarefa pendente.")
            tid = T.criar("lembrar de beber água", passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": SEGREDO}}])
            self.assertIn("beber água", MAIN.processar("minhas tarefas"))
            self.assertIn("Cancelei", MAIN.processar(f"cancela a tarefa {int(tid[1:])}"))
        self.assertEqual(T.obter(tid)["estado"], T.CANCELADA)

    def test_painel_mostra_so_contagens(self):
        T.criar("lembrar de beber água " + SEGREDO)
        r = MAIN.estado_completo(painel=False)["tarefas"]
        self.assertEqual(r["abertas"], 1)
        self.assertNotIn(SEGREDO, json.dumps(r))


if __name__ == "__main__":
    unittest.main()
