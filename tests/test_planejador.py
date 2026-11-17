"""Fase 4 — planejador (friday/planejador.py): o ciclo de 11 passos, a troca de estratégia e o aprendizado pela experiência.

Mapa dos testes da missão:  C falha e alternativa permitida, com a experiência registrada · E uma experiência anterior relevante muda a estratégia seguinte, com
justificativa que dá para conferir · F (aqui: ação que exige confirmação nunca é escolhida sozinha) · G privacidade · H (a subtarefa conta para a meta por id; ver test_tarefas_metas.py).
"""
import ast, json, os, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import experiencias as X, ferramentas as F, memoria as MEM, planejador as PL, tarefas as T
from test_experiencias import Base, SEGREDO
from test_tarefas import mente, sms_enviados

CICLO = ("1 receber", "2 contexto", "3 saber × descobrir", "4 etapas", "5 estratégia", "6-8 executar, observar, verificar", "9 experiência")


def minha(params=None):
    return {"texto": SEGREDO, **(params or {})}


class Ciclo(Base):
    def test_objetivo_simples_executado_e_conferido(self):
        r = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual((r["decisao"], r["estado"], len(r["tentativas"])), ("concluir", T.CONCLUIDA, 1))
        t = T.obter(r["tarefa"])
        self.assertEqual(t["passos"][0]["estado"], "verificado")
        self.assertEqual(t["passos"][0]["verificacao"]["forca"], "independente")
        self.assertEqual(t["contexto"]["origem"], "usuario")

    def test_os_onze_passos_aparecem_na_ordem(self):
        r = PL.executar_objetivo("registrar_informacao", minha())
        marcas = [l.split(":")[0].split(" (")[0] for l in r["ciclo"]]
        for esperado in CICLO:
            self.assertIn(esperado, marcas)
        posicoes = [marcas.index(c) for c in CICLO]
        self.assertEqual(posicoes, sorted(posicoes), "a ordem do ciclo é a combinada")
        self.assertEqual(r["ciclo"][-1], "11 decisão: concluir")

    def test_a_hipotese_ja_esta_no_arquivo_quando_a_ferramenta_roda(self):
        vistas = []
        original = B.FERRAMENTAS["guardar_memoria"]["fn"]

        def espia(**kw):
            vistas.append([l["k"] for l in self.linhas()])
            return original(**kw)
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": espia}):
            PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual(vistas, [["intencao"]], "a expectativa foi escrita antes de agir, e o resultado só depois")

    def test_a_experiencia_nasce_com_a_expectativa_gravada_antes(self):
        r = PL.executar_objetivo("registrar_informacao", minha())
        xs = [l["k"] for l in self.linhas()]
        self.assertEqual(xs, ["intencao", "experiencia"])
        x = X.da_tarefa(r["tarefa"])
        self.assertEqual((x["fonte"], x["objetivo"]["tipo"], x["estrategia"]["id"], x["resultado"]), ("planejador", "registrar_informacao", "guardar_memoria", X.SUCESSO))
        self.assertEqual(x["hipotese"]["origem"], "planejador")
        self.assertEqual(x["alternativas"], ["anotar", "criar_arquivo"])
        self.assertTrue(x["escolha"]["ranking"])
        self.assertEqual(x["escolha"]["escolhida"], "guardar_memoria")

    def test_dois_passos_com_dependencia(self):
        r = PL.executar_objetivo("registrar_e_avisar", {"texto": SEGREDO, "minutos": 9})
        self.assertEqual(r["decisao"], "concluir")
        t = T.obter(r["tarefa"])
        self.assertEqual([p["ferramenta"] for p in t["passos"]], ["anotar", "criar_lembrete"])
        self.assertEqual(t["passos"][1]["depende_de"], ["p1"])
        self.assertEqual(self.notas(), 1)
        self.assertEqual(len(self.lembretes()), 1, "os dois efeitos existem de verdade")
        self.assertEqual(X.da_tarefa(r["tarefa"])["estrategia"]["id"], "anotar+criar_lembrete")

    def test_lembrar_depois(self):
        r = PL.executar_objetivo("lembrar_depois", {"texto": SEGREDO, "minutos": 5})
        self.assertEqual(r["decisao"], "concluir")
        self.assertEqual(len(self.lembretes()), 1)

    def test_a_tarefa_pode_servir_a_uma_meta_por_id(self):
        r = PL.executar_objetivo("registrar_informacao", minha(), meta="m01", conclui_meta=True)
        t = T.obter(r["tarefa"])
        self.assertEqual((t["contexto"]["meta"], t["contexto"]["conclui_meta"], t["estado"]), ("m01", True, T.CONCLUIDA))
        self.assertEqual(T.resumo_por_meta()["m01"]["conclui"], True)

    def test_o_objetivo_da_tarefa_nao_carrega_o_conteudo(self):
        r = PL.executar_objetivo("registrar_informacao", minha({"titulo": "um título"}))
        t = T.obter(r["tarefa"])
        self.assertNotIn(SEGREDO, t["objetivo"])
        self.assertIn("texto: ", t["objetivo"])


class Recusas(Base):
    def casos(self):
        return [
            ("tipo_que_nao_existe", {"texto": "x"}, {}),
            ("registrar_informacao", {}, {}),
            ("registrar_informacao", {"texto": ""}, {}),
            ("registrar_informacao", {"texto": "a" * 2001}, {}),
            ("registrar_informacao", {"texto": "ok", "outro": 1}, {}),
            ("registrar_informacao", "texto", {}),
            ("lembrar_depois", {"texto": "x", "minutos": -3}, {}),
            ("lembrar_depois", {"texto": "x", "minutos": "muito"}, {}),
            ("lembrar_depois", {"texto": "x", "minutos": True}, {}),
            ("lembrar_depois", {"texto": "x" * 201, "minutos": 5}, {}),
            ("registrar_informacao", {"texto": "x"}, {"origem": "ia"}),
            ("registrar_informacao", {"texto": "x"}, {"nivel_max": 9}),
            (None, {"texto": "x"}, {}),
        ]

    def test_pedido_invalido_e_recusado_sem_criar_nada(self):
        for tipo, params, extra in self.casos():
            with self.subTest(tipo=tipo, params=str(params)[:30], extra=extra):
                r = PL.executar_objetivo(tipo, params, **extra)
                self.assertEqual((r["decisao"], r["tarefa"]), ("recusar", None))
        self.assertEqual(T.listar(), [])
        self.assertEqual(X.resumo()["total"], 0)

    def test_conteudo_sensivel_e_recusado_antes_de_qualquer_ferramenta(self):
        for texto in ("minha senha é hunter2xyz", "cartão 4111 1111 1111 1111 vence 12/30", "meu cpf 123.456.789-09"):
            r = PL.executar_objetivo("registrar_informacao", {"texto": texto})
            self.assertEqual((r["decisao"], r["tarefa"]), ("recusar", None), texto)
            self.assertIn("dado sensível", r["mensagem"])
        self.assertEqual((self.notas("minha senha é hunter2xyz"), T.listar()), (0, []), "nem a nota, nem o arquivo, nem a tarefa")

    def test_objetivo_proprio_sem_o_dono_e_recusado(self):
        for extra in ({}, {"autorizado_por": "ia", "proposta": "o01"}, {"autorizado_por": "dono"}, {"autorizado_por": "dono", "proposta": 1}):
            r = PL.executar_objetivo("registrar_informacao", minha(), origem="propria", **extra)
            self.assertEqual((r["decisao"], r["tarefa"]), ("recusar", None), extra)
        self.assertEqual(T.listar(), [])

    def test_objetivo_proprio_so_em_tipo_permitido(self):
        r = PL.executar_objetivo("lembrar_depois", {"texto": "x", "minutos": 5}, origem="propria", autorizado_por="dono", proposta="o01")
        self.assertEqual((r["decisao"], r["tarefa"]), ("recusar", None))
        self.assertIn("não podem ser próprios", r["mensagem"])

    def test_objetivo_proprio_aprovado_roda_e_fica_registrado_como_proprio(self):
        r = PL.executar_objetivo("registrar_informacao", minha(), origem="propria", autorizado_por="dono", proposta="o01")
        self.assertEqual(r["decisao"], "concluir")
        t = T.obter(r["tarefa"])
        self.assertEqual(t["contexto"]["origem"], "propria")
        self.assertIn("proposta o01 aprovada pelo dono", t["contexto"]["restricoes"])

    def test_objetivo_proprio_nunca_passa_do_nivel_1(self):
        with mock.patch.dict(PL.OBJETIVOS, {"so_sms": self.tipo_com_sms(permite_proprio=True)}):
            r = PL.executar_objetivo("so_sms", {"texto": SEGREDO}, origem="propria", autorizado_por="dono", proposta="o01", nivel_max=3)
        self.assertNotIn(r["decisao"], ("concluir", "esperar_dono"))
        self.assertEqual(sms_enviados() - self.sms0, 0)

    @staticmethod
    def tipo_com_sms(permite_proprio=False):
        return {"descricao": "avisar a mãe", "params": {"texto": ("str", 1, 200)}, "obrigatorios": ("texto",), "permite_proprio": permite_proprio,
                "estrategias": [PL._E(("enviar_sms",), "mandar um SMS", "o SMS sai", "o SMS sai do celular",
                                      lambda p: [PL._passo("mandar um SMS", "enviar_sms", {"contato": "mae", "texto": p["texto"]})])], "parciais": []}


class FalhaEAlternativa(Base):
    def test_C_estrategia_falha_experiencia_registrada_e_alternativa_funciona(self):
        with mente("guardar_memoria", "Guardei na memória de longo prazo."):
            r = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual((r["decisao"], r["estado"]), ("concluir", T.CONCLUIDA))
        self.assertEqual([x["estrategia"] for x in r["tentativas"]], ["guardar_memoria", "anotar"])
        self.assertEqual([x["resultado"] for x in r["tentativas"]], [X.FALHA, X.SUCESSO])
        self.assertEqual(self.notas(), 1, "a alternativa produziu o efeito de verdade")
        falha = X.da_tarefa(r["tarefa"], 1)
        self.assertEqual((falha["resultado"], falha["tipo_falha"], falha["estrategia"]["id"]), (X.FALHA, "falso_sucesso", "guardar_memoria"))
        self.assertEqual(falha["alternativas"], ["anotar", "criar_arquivo"], "a alternativa já estava prevista antes de falhar")
        self.assertEqual([c["tipo"] for c in falha["causas"]], [X.FATO, X.INFERENCIA, X.HIPOTESE])
        ok = X.da_tarefa(r["tarefa"], 2)
        self.assertEqual((ok["resultado"], ok["estrategia"]["id"]), (X.SUCESSO, "anotar"))
        self.assertIn("10 atualizar o plano", " ".join(r["ciclo"]))
        t = T.obter(r["tarefa"])
        self.assertEqual(t["plano_v"], 2)
        self.assertIn("refazendo o plano", [h["motivo"] for h in t["historico"]])

    def test_erro_do_corretor_tambem_leva_a_alternativa(self):
        def quebra(**kw):
            raise RuntimeError("cofre travou")
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": quebra}):
            r = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual((r["decisao"], r["tentativas"][0]["resultado"], r["tentativas"][1]["estrategia"]), ("concluir", X.FALHA, "anotar"))
        self.assertEqual(X.da_tarefa(r["tarefa"], 1)["tipo_falha"], "erro")

    def test_todas_as_estrategias_falham_pede_esclarecimento_e_nao_finge(self):
        with mente("guardar_memoria", "ok"), mente("anotar", "ok"), mente("criar_arquivo", "ok"):
            r = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual(r["decisao"], "pedir_esclarecimento")
        self.assertEqual(len(r["tentativas"]), 3)
        self.assertEqual(r["estado"], T.FALHOU, "a tarefa NÃO é dada como concluída")
        self.assertIn("Não consegui", r["mensagem"])
        self.assertIn("Não restam alternativas", r["mensagem"])
        self.assertEqual(self.notas(), 0)
        self.assertEqual(X.sinais("guardar_memoria")["falhas"] + X.sinais("anotar")["falhas"] + X.sinais("criar_arquivo")["falhas"], 3)

    def test_limite_de_tentativas_para_e_pergunta(self):
        with mente("guardar_memoria", "ok"), mente("anotar", "ok"):
            r = PL.executar_objetivo("registrar_informacao", minha(), max_tentativas=2)
        self.assertEqual((r["decisao"], len(r["tentativas"])), ("pedir_esclarecimento", 2))
        self.assertIn("quer que eu continue", r["mensagem"])

    def test_recusa_do_corretor_nao_se_contorna(self):
        recusa = lambda nome, args, turno=None: B._res("recusada", "Pedido inválido: de propósito", "invalido")
        with mock.patch.object(B, "executar_estruturado", side_effect=recusa):
            r = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual((r["decisao"], len(r["tentativas"])), ("interromper", 1))
        self.assertIn("Não vou tentar contornar", r["mensagem"])
        self.assertEqual(X.da_tarefa(r["tarefa"])["tipo_falha"], "recusa")

    def test_ao_falhar_a_primeira_a_segunda_nao_repete_a_ferramenta_que_mentiu(self):
        chamadas = []
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": lambda **kw: chamadas.append(1) or "ok"}):
            PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual(len(chamadas), 1)

    def test_acao_que_exige_confirmacao_nunca_e_escolhida_sozinha(self):
        with mock.patch.dict(PL.OBJETIVOS, {"avisar": {**Recusas.tipo_com_sms(), "estrategias": [
                PL._E(("anotar",), "só anotar", "anotar", "nota", lambda p: [PL._passo("anotar", "anotar", {"texto": p["texto"]})]),
                *Recusas.tipo_com_sms()["estrategias"]]}}):
            with mente("anotar", "ok"):
                r = PL.executar_objetivo("avisar", {"texto": SEGREDO})
        self.assertEqual(r["decisao"], "pedir_esclarecimento")
        self.assertEqual([x["estrategia"] for x in r["tentativas"]], ["anotar"])
        self.assertEqual(sms_enviados() - self.sms0, 0)
        self.assertEqual([s["estrategia"] for s in r["sugestoes"]], ["enviar_sms"], "oferece, não executa")
        self.assertIn("exige confirmação", r["sugestoes"][0]["porque"])

    def test_com_nivel_2_autorizado_pelo_dono_a_acao_espera_a_confirmacao(self):
        with mock.patch.dict(PL.OBJETIVOS, {"avisar": Recusas.tipo_com_sms()}):
            r = PL.executar_objetivo("avisar", {"texto": SEGREDO}, nivel_max=2)
        self.assertEqual((r["decisao"], r["estado"]), ("esperar_dono", T.BLOQUEADA))
        self.assertEqual(sms_enviados() - self.sms0, 0, "o planejador não confirma nada")
        self.assertIn("confirmação clara", r["mensagem"])

    def test_oferece_o_parcial_mas_nao_o_executa(self):
        with mente("criar_lembrete", "Lembrete criado."):
            r = PL.executar_objetivo("lembrar_depois", {"texto": SEGREDO, "minutos": 5})
        self.assertEqual(r["decisao"], "pedir_esclarecimento")
        self.assertEqual([s["estrategia"] for s in r["sugestoes"]], ["anotar"])
        self.assertIn("não cumpre o pedido por inteiro", r["sugestoes"][0]["descricao"])
        self.assertEqual(self.notas(), 0, "só anotar não foi feito sem perguntar")

    def test_sem_como_conferir_pede_o_dono_em_vez_de_tentar_outra(self):
        with mock.patch.dict(PL.OBJETIVOS, {"cego": {"descricao": "x", "params": {"texto": ("str", 1, 20)}, "obrigatorios": ("texto",), "permite_proprio": False, "parciais": [],
                                                      "estrategias": [PL._E(("acao_cega_pl",), "ação cega", "h", "e", lambda p: [PL._passo("cega", "acao_cega_pl", {})]),
                                                                      PL._E(("anotar",), "anotar", "h", "e", lambda p: [PL._passo("anotar", "anotar", {"texto": p["texto"]})])]}}):
            B.registrar("acao_cega_pl", "t", {}, [], lambda: "Feito.", 1)
            self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_pl", None)
            r = PL.executar_objetivo("cego", {"texto": "x"})
        self.assertEqual((r["decisao"], r["estado"], len(r["tentativas"])), ("pedir_esclarecimento", T.EXECUTADA_SEM_VERIFICACAO, 1), "a ação provavelmente aconteceu: outra estratégia duplicaria")
        self.assertEqual(self.notas("x"), 0)


class AprendizadoMudaAEscolha(Base):
    def primeira(self, r):
        return r["tentativas"][0]["escolha"]["escolhida"]

    def test_E_depois_de_falhar_a_proxima_vez_comeca_pela_que_funcionou(self):
        mentira = []
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": lambda **kw: mentira.append(1) or "Guardei."}):
            r1 = PL.executar_objetivo("registrar_informacao", minha())
            r2 = PL.executar_objetivo("registrar_informacao", minha({"texto": SEGREDO + "2"}))
        self.assertEqual((self.primeira(r1), self.primeira(r2)), ("guardar_memoria", "anotar"), "a experiência mudou o começo")
        self.assertEqual(len(mentira), 1, "a ferramenta que mentiu não foi nem chamada na segunda vez")
        self.assertEqual((r2["decisao"], len(r2["tentativas"])), ("concluir", 1))

    def test_a_justificativa_cita_experiencias_que_existem_e_bate_com_o_registro(self):
        with mente("guardar_memoria", "Guardei."):
            r1 = PL.executar_objetivo("registrar_informacao", minha())
            r2 = PL.executar_objetivo("registrar_informacao", minha({"texto": SEGREDO + "2"}))
        escolha = r2["tentativas"][0]["escolha"]
        por_id = {i["id"]: i for i in escolha["ranking"]}
        falha_antiga = X.da_tarefa(r1["tarefa"], 1)
        self.assertIn(falha_antiga["id"], por_id["guardar_memoria"]["experiencias"])
        self.assertEqual((por_id["guardar_memoria"]["falhas"], por_id["guardar_memoria"]["n"]), (1, 1))
        self.assertIn(falha_antiga["id"], por_id["guardar_memoria"]["motivo"], "o motivo em texto aponta para a experiência")
        self.assertEqual(X.conferir_escolha(escolha), (True, []))
        self.assertEqual(X.conferir_escolha(X.da_tarefa(r2["tarefa"])["escolha"]), (True, []), "a justificativa gravada em disco também confere")
        self.assertEqual(escolha["regra"], PL.REGRA_DE_ESCOLHA)

    def test_justificativa_adulterada_e_apanhada(self):
        with mente("guardar_memoria", "Guardei."):
            PL.executar_objetivo("registrar_informacao", minha())
            r2 = PL.executar_objetivo("registrar_informacao", minha({"texto": SEGREDO + "2"}))
        escolha = json.loads(json.dumps(r2["tentativas"][0]["escolha"]))
        escolha["ranking"][0]["falhas"] += 1
        self.assertFalse(X.conferir_escolha(escolha)[0])

    def test_sem_experiencia_a_ordem_e_a_do_catalogo(self):
        e = PL.escolher("registrar_informacao", {"texto": "x"}, X.ambiente())
        self.assertEqual([r["id"] for r in e["ranking"]], ["guardar_memoria", "anotar", "criar_arquivo"])
        self.assertTrue(all(r["p"] == 0.5 and r["n"] == 0 for r in e["ranking"]))
        self.assertEqual(len(e["conhecimento"]["descobrir"]), 3, "tudo está por descobrir")

    def test_um_acerto_nao_faz_a_estrategia_imune(self):
        PL.executar_objetivo("registrar_informacao", minha())                       # guardar_memoria funciona: p = 0,67
        with mente("guardar_memoria", "Guardei."):
            PL.executar_objetivo("registrar_informacao", minha({"texto": SEGREDO + "2"}))   # e agora mente: 1 acerto, 1 falha: p = 0,5
        e = PL.escolher("registrar_informacao", {"texto": "x"}, X.ambiente())
        self.assertEqual({r["id"]: r["p"] for r in e["ranking"]}["guardar_memoria"], 0.5)

    def test_uma_falha_nao_proibe_a_estrategia(self):
        with mente("guardar_memoria", "ok"), mente("anotar", "ok"), mente("criar_arquivo", "ok"):
            PL.executar_objetivo("registrar_informacao", minha())
        e = PL.escolher("registrar_informacao", {"texto": "x"}, X.ambiente())
        self.assertEqual([r["id"] for r in e["ranking"]], ["guardar_memoria", "anotar", "criar_arquivo"], "todas com uma falha: empate, vale o catálogo; nenhuma foi banida")

    def test_experiencia_de_outras_condicoes_nao_vale(self):
        manutencao = {"cofre_ativo": True, "manutencao": True}
        with mock.patch.object(X, "ambiente", return_value=manutencao), mente("guardar_memoria", "Guardei."):
            r1 = PL.executar_objetivo("registrar_informacao", minha())
        self.assertEqual(r1["tentativas"][0]["escolha"]["condicoes"], manutencao)
        normal = X.ambiente()
        self.assertEqual(normal["manutencao"], False)
        e = PL.escolher("registrar_informacao", {"texto": "x"}, normal)
        self.assertEqual(e["escolhida"], "guardar_memoria", "a falha foi em manutenção; agora não pesa")
        self.assertEqual(e["ranking"][0]["n"], 0)
        e2 = PL.escolher("registrar_informacao", {"texto": "x"}, manutencao)
        self.assertEqual(e2["escolhida"], "anotar", "nas mesmas condições da falha, pesa")

    def test_experiencia_falsa_nao_cria_estrategia_nem_sobe_de_nivel(self):
        """Linhas inventadas no arquivo de experiências só podem reordenar o que o catálogo já permite."""
        falsa = {"k": "experiencia", "id": "x0900", "em": 1.0, "tarefa": "t0900", "plano_v": 1, "resultado": "sucesso", "estrategia": {"id": "enviar_sms"}, "objetivo": {"texto": "x"}}
        os.makedirs(self.base(".cerebro"), exist_ok=True)
        with open(self.base(".cerebro", "experiencias.jsonl"), "a", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({**falsa, "id": f"x09{i:02d}", "tarefa": f"t09{i:02d}"}) + "\n")
        X.reiniciar()
        self.assertEqual(X.sinais("enviar_sms")["sucessos"], 10)
        with mock.patch.dict(PL.OBJETIVOS, {"avisar": Recusas.tipo_com_sms()}):
            e = PL.escolher("avisar", {"texto": "x"}, X.ambiente())
            r = PL.executar_objetivo("avisar", {"texto": SEGREDO})
        self.assertEqual((e["ranking"], e["escolhida"]), ([], None))
        self.assertEqual(r["decisao"], "pedir_esclarecimento")
        self.assertEqual(sms_enviados() - self.sms0, 0)

    def test_recusas_e_execucoes_sem_conferencia_nao_pesam(self):
        recusa = lambda nome, args, turno=None: B._res("recusada", "Pedido inválido: de propósito", "invalido")
        with mock.patch.object(B, "executar_estruturado", side_effect=recusa):
            PL.executar_objetivo("registrar_informacao", minha())
        s = X.sinais("guardar_memoria")
        self.assertEqual((s["n"], s["falhas"], s["recusas"], s["p"]), (0, 0, 1, 0.5))

    def test_ambiente_muda_entre_tentativas_e_o_plano_e_reavaliado(self):
        amb = {"cofre_ativo": True, "manutencao": False}

        def mentira_que_desliga_o_cofre(**kw):
            amb["cofre_ativo"] = False
            return "ok"
        with mock.patch.object(X, "ambiente", side_effect=lambda: dict(amb)), mock.patch.dict(B.FERRAMENTAS["anotar"], {"fn": mentira_que_desliga_o_cofre}):
            r = PL.executar_objetivo("registrar_e_avisar", {"texto": SEGREDO, "minutos": 9})
        self.assertEqual(r["decisao"], "pedir_esclarecimento")
        self.assertEqual(len(r["tentativas"]), 1, "a segunda estratégia exige o cofre, que desligou")
        self.assertTrue(any("cofre_ativo=não" in l for l in r["ciclo"] if l.startswith("2 contexto (tentativa 2)")), r["ciclo"])
        self.assertIn("Ficaram de fora: «guardar_memoria+criar_lembrete» exige cofre_ativo=sim, e agora é não", r["mensagem"], "o motivo da exclusão é dito, não escondido")


class DicaParaIA(Base):
    def test_ferramenta_da_ia_que_mente_recebe_a_dica_de_alternativa(self):
        with mente("guardar_memoria", "Guardei na memória."):
            texto = T.executar_registrado("guardar_memoria", {"texto": SEGREDO})
        self.assertIn("NÃO encontrei", texto)
        self.assertIn("Experiência registrada", texto)
        self.assertIn("«anotar» (ainda sem histórico)", texto)
        self.assertIn("«criar_arquivo»", texto)
        self.assertIn("o corretor continua decidindo", texto)
        self.assertNotIn(SEGREDO, texto)

    def test_a_dica_usa_o_historico_das_alternativas(self):
        for i in range(2):
            T.executar_registrado("anotar", {"texto": f"{SEGREDO}-{i}"})
        with mente("guardar_memoria", "Guardei."):
            texto = T.executar_registrado("guardar_memoria", {"texto": SEGREDO})
        self.assertIn("«anotar» (2 de 2 deram certo)", texto)
        self.assertIn("deu certo 0 de 1 vezes", texto)

    def test_erro_da_ferramenta_ganha_dica_mas_recusa_do_corretor_nao(self):
        def quebra(**kw):
            raise RuntimeError("cofre travou")
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": quebra}):
            com_erro = T.executar_registrado("guardar_memoria", {"texto": SEGREDO})
        self.assertIn("Experiência registrada", com_erro)
        recusada = T.executar_registrado("anotar", {})
        self.assertEqual(recusada, B.executar("anotar", {}), "pedido inválido: a IA corrige o pedido, não troca de ferramenta")

    def test_a_dica_nao_sugere_alternativa_indisponivel_agora(self):
        desligado = {"cofre_ativo": False, "manutencao": False}
        with mock.patch.object(X, "ambiente", return_value=desligado), mente("anotar", "Anotado."):
            texto = T.executar_registrado("anotar", {"texto": SEGREDO})
        self.assertIn("«criar_arquivo»", texto)
        self.assertNotIn("«guardar_memoria»", texto, "com o cofre desligado ela não é alternativa")

    def test_sucesso_nao_ganha_dica(self):
        texto = T.executar_registrado("anotar", {"texto": SEGREDO})
        self.assertNotIn("Experiência registrada", texto)

    def test_ferramenta_sem_alternativa_equivalente_nao_ganha_dica(self):
        with mente("criar_lembrete", "Lembrete criado."):
            texto = T.executar_registrado("criar_lembrete", {"minutos": 5, "texto": SEGREDO})
        self.assertIn("NÃO encontrei", texto)
        self.assertNotIn("Experiência registrada", texto)

    def test_dica_que_quebra_nao_atrapalha(self):
        def quebra(nome, args):
            raise RuntimeError("bug")
        with mock.patch.object(T, "DICAS", [quebra]), mente("guardar_memoria", "Guardei."):
            texto = T.executar_registrado("guardar_memoria", {"texto": SEGREDO})
        self.assertIn("NÃO encontrei", texto)

    def test_dica_tem_tamanho_limitado_e_uma_so(self):
        with mock.patch.object(T, "DICAS", [lambda n, a: "x" * 5000, lambda n, a: "segunda"]), mente("guardar_memoria", "Guardei."):
            texto = T.executar_registrado("guardar_memoria", {"texto": SEGREDO})
        self.assertLess(len(texto), 900)
        self.assertNotIn("segunda", texto)

    def test_o_gancho_esta_registrado_uma_vez_so(self):
        PL._registrar_dica()
        PL._registrar_dica()
        self.assertEqual(sum(1 for d in T.DICAS if getattr(d, "_friday_planejador", False)), 1)


class Privacidade(Base):
    def test_nada_do_conteudo_vai_para_experiencias_nem_para_a_auditoria(self):
        with mente("guardar_memoria", "Guardei."):
            r = PL.executar_objetivo("registrar_informacao", minha({"titulo": "um título"}))
        self.assertNotIn(SEGREDO, self.arquivo())
        with open(B.AUDITORIA, encoding="utf-8") as f:
            self.assertNotIn(SEGREDO, f.read())
        self.assertTrue(B.verificar_auditoria()[0])
        for p in T.obter(r["tarefa"])["passos"]:
            self.assertIsNone(p["args"], "tarefa concluída não guarda conteúdo")

    def test_planejar_nao_escreve_na_auditoria_alem_das_acoes(self):
        antes = 0
        if os.path.exists(B.AUDITORIA):
            with open(B.AUDITORIA, encoding="utf-8") as f:
                antes = len(f.read().splitlines())
        PL.executar_objetivo("registrar_informacao", minha())
        with open(B.AUDITORIA, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()) - antes, 1, "uma ação, uma linha")


class SoPropoe(unittest.TestCase):
    def test_o_planejador_nao_chama_o_corretor_para_executar(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "friday", "planejador.py"), encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        usos = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "B"}
        self.assertEqual(usos, {"FERRAMENTAS"}, "só lê o catálogo de ferramentas; quem executa é `tarefas` pelo corretor")

    def test_o_catalogo_so_tem_ferramentas_que_existem_e_nenhuma_proibida(self):
        for tipo, obj in PL.OBJETIVOS.items():
            self.assertTrue(obj["estrategias"], tipo)
            ids = [e["id"] for e in obj["estrategias"]]
            self.assertEqual(len(ids), len(set(ids)), f"{tipo}: estratégias repetidas")
            for e in obj["estrategias"]:
                for f in e["ferramentas"]:
                    self.assertIn(f, B.FERRAMENTAS, f"{tipo}/{e['id']}")
                    self.assertNotEqual(B.FERRAMENTAS[f]["nivel"], 4)
                for proibida in ("autonomia", "curiosidade", "conversa", "protocolo", "desligar", "parar", "shell", "sql"):
                    self.assertNotIn(proibida, e["id"])

    def test_nenhum_tipo_proprio_chega_a_nivel_2(self):
        for tipo, obj in PL.OBJETIVOS.items():
            if obj["permite_proprio"]:
                for e in obj["estrategias"]:
                    for p in e["montar"]({"texto": "x", "titulo": "t", "minutos": 5}):
                        self.assertLess(PL.T._nivel_do_passo(p["ferramenta"], p["args"]), 2, f"{tipo}/{e['id']}")

    def test_a_ia_nao_ganhou_ferramenta_de_planejamento(self):
        for nome in B.FERRAMENTAS:
            self.assertFalse(any(w in nome.lower() for w in ("planej", "objetivo", "experienc")), nome)


if __name__ == "__main__":
    unittest.main()
