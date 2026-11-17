"""Fase 3 — registro de experiências (friday/experiencias.py).

Mapa dos testes da missão:  E aprendizado (a experiência passada muda a escolha seguinte, com justificativa conferível — a escolha em si está em test_planejador.py) ·
G privacidade (nada de conteúdo no registro) · C (a experiência da falha fica registrada; a alternativa está em test_planejador.py).
Aqui: o registro é fiel, tipado (fato/inferência/hipótese/desconhecido), não vira regra universal e só vale nas condições em que nasceu.
"""
import ast, json, os, re, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import experiencias as X, ferramentas as F, memoria as MEM, tarefas as T, verificacao as V
from test_tarefas import Base as BaseTarefas, mente, SEGREDO


def falha_com_erro(**kw):
    raise RuntimeError("quebrou de propósito")


class Base(BaseTarefas):
    def setUp(self):
        super().setUp()
        X.reiniciar()
        self.addCleanup(X.reiniciar)

    def rodar(self, passos, objetivo="registrar uma coisa", **kw):
        tid = T.criar(objetivo, passos=passos, **kw)
        T.executar(tid)
        return tid

    def cega(self):
        B.registrar("acao_cega_exp", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_exp", None)
        return {"descricao": "fazer algo sem como conferir", "ferramenta": "acao_cega_exp", "args": {}}

    def arquivo(self):
        with open(self.base(".cerebro", "experiencias.jsonl"), encoding="utf-8") as f:
            return f.read()

    def linhas(self):
        return [json.loads(l) for l in self.arquivo().splitlines() if l.strip()]


class Registro(Base):
    def test_sucesso_vira_experiencia_de_sucesso(self):
        tid = self.rodar([self.lembrete()])
        x = X.da_tarefa(tid)
        self.assertEqual((x["resultado"], x["tipo_falha"], x["prova"], x["fonte"]), (X.SUCESSO, None, V.INDEPENDENTE, "tarefa"))
        self.assertEqual(x["estrategia"]["id"], "criar_lembrete")
        self.assertIsNone(x["diferenca"])
        self.assertEqual(x["causas"], [])
        self.assertEqual(x["acoes"][0]["ferramenta"], "criar_lembrete")
        self.assertEqual(x["evidencias"][0]["veredito"], V.CONFIRMADO)

    def test_falso_sucesso_vira_falha_com_causas_tipadas(self):
        with mente("criar_lembrete", "Lembrete criado para daqui a 7 minutos."):
            tid = self.rodar([self.lembrete()])
        x = X.da_tarefa(tid)
        self.assertEqual((x["resultado"], x["tipo_falha"]), (X.FALHA, "falso_sucesso"))
        tipos = [c["tipo"] for c in x["causas"]]
        self.assertEqual(tipos, [X.FATO, X.INFERENCIA, X.HIPOTESE], "o que se viu, o que se concluiu e o que é palpite ficam separados")
        fato, inferencia, hipotese = x["causas"]
        self.assertEqual(fato["confianca"], 1.0)
        self.assertLess(inferencia["confianca"], 1.0)
        self.assertLess(hipotese["confianca"], inferencia["confianca"], "palpite pesa menos que conclusão")
        self.assertTrue(any("por que a ferramenta disse" in d for d in x["desconhecido"]), "o que não se sabe fica escrito")
        self.assertIn("esperava o efeito conferido", x["diferenca"])

    def test_erro_do_corretor_vira_falha_de_erro(self):
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": falha_com_erro}):
            tid = self.rodar([self.lembrete()])
        x = X.da_tarefa(tid)
        self.assertEqual((x["resultado"], x["tipo_falha"]), (X.FALHA, "erro"))
        self.assertIn("Erro: RuntimeError", x["causas"][0]["texto"])
        self.assertNotIn("quebrou de propósito", self.arquivo(), "a resposta da ferramenta não é guardada")

    def test_recusa_do_corretor_nao_e_falha_da_estrategia(self):
        tid = self.rodar([{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": "muito", "texto": "a"}}])
        x = X.da_tarefa(tid)
        self.assertEqual((x["resultado"], x["tipo_falha"]), (X.FALHA, "recusa"))
        s = X.sinais("criar_lembrete")
        self.assertEqual((s["n"], s["falhas"], s["recusas"]), (0, 0, 1), "recusa por argumento inválido não pesa contra a estratégia")

    def test_sem_como_conferir_nao_e_sucesso_nem_falha(self):
        tid = self.rodar([self.cega()])
        x = X.da_tarefa(tid)
        self.assertEqual(x["resultado"], X.SEM_CONFERENCIA)
        self.assertTrue(any("nenhuma conferência independente" in d for d in x["desconhecido"]))
        s = X.sinais("acao_cega_exp")
        self.assertEqual((s["n"], s["sem_conferencia"]), (0, 1))

    def test_o_dono_confirma_e_a_ultima_versao_da_tentativa_vale(self):
        tid = self.rodar([self.cega()])
        self.assertEqual(X.sinais("acao_cega_exp")["sem_conferencia"], 1)
        T.confirmar_manual(tid)
        x = X.da_tarefa(tid)
        self.assertEqual((x["resultado"], x["prova"]), (X.SUCESSO, "dono"))
        self.assertTrue(x["substitui"], "a nova versão aponta para a anterior")
        self.assertTrue(any("só o dono confirmou" in d for d in x["desconhecido"]))
        s = X.sinais("acao_cega_exp")
        self.assertEqual((s["n"], s["sucessos"], s["sem_conferencia"]), (1, 1, 0), "a mesma tentativa não conta duas vezes")
        self.assertEqual(len([l for l in self.linhas() if l["k"] == "experiencia"]), 2, "nada é apagado: as duas versões estão no arquivo")

    def test_cancelada_nao_pesa(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.cancelar(tid)
        x = X.da_tarefa(tid)
        self.assertEqual(x["resultado"], X.CANCELADA)
        self.assertEqual(X.sinais("criar_lembrete")["ignoradas"], 1)
        self.assertEqual(X.sinais("criar_lembrete")["n"], 0)

    def test_interrompida_nao_pesa_e_diz_o_que_nao_sabe(self):
        tid = T.criar("avisar", passos=[{"descricao": "avisar", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO}}])
        T.reiniciar()
        T.executar(tid)
        x = X.da_tarefa(tid)
        self.assertEqual(x["resultado"], X.INTERROMPIDA)
        self.assertTrue(any("chegou a acontecer" in d for d in x["desconhecido"]))
        self.assertEqual(X.sinais("enviar_sms")["n"], 0)

    def test_estrategia_com_varios_passos_tem_o_caminho_como_id(self):
        tid = self.rodar([{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}, self.lembrete(depende_de=["p1"])])
        self.assertEqual(X.da_tarefa(tid)["estrategia"]["id"], "anotar+criar_lembrete")

    def test_cada_plano_novo_e_uma_tentativa_nova(self):
        with mente("criar_lembrete", "Lembrete criado."):
            tid = self.rodar([self.lembrete()])
        self.assertEqual(T.obter(tid)["plano_v"], 1)
        T.planejar(tid, [self.lembrete()])
        T.executar(tid)
        self.assertEqual(T.obter(tid)["plano_v"], 2)
        self.assertEqual((X.da_tarefa(tid, 1)["resultado"], X.da_tarefa(tid, 2)["resultado"]), (X.FALHA, X.SUCESSO))
        self.assertEqual(X.da_tarefa(tid)["plano_v"], 2, "sem dizer o plano, vale o mais recente")


class SemEnfeitar(Base):
    def test_a_hipotese_de_quem_nao_planejou_e_marcada_como_implicita(self):
        tid = self.rodar([self.lembrete()])
        x = X.da_tarefa(tid)
        self.assertEqual(x["hipotese"]["origem"], "implicita")
        self.assertIn("atinge o objetivo", x["hipotese"]["texto"])

    def test_a_expectativa_e_gravada_antes_do_resultado(self):
        tid = T.criar("registrar", passos=[self.lembrete()])
        plano_v = T.obter(tid)["plano_v"]
        X.intencao(tid, plano_v, tipo="lembrar_depois", estrategia="criar_lembrete", descricao="criar um lembrete", hipotese="o lembrete será falado na hora",
                   esperado="um lembrete novo no banco com o texto e o horário", alternativas=["anotar"])
        antes = self.linhas()
        self.assertEqual([l["k"] for l in antes], ["intencao"])
        T.executar(tid)
        depois = self.linhas()
        self.assertEqual([l["k"] for l in depois], ["intencao", "experiencia"], "primeiro a intenção, depois o resultado")
        x = X.da_tarefa(tid)
        self.assertEqual((x["fonte"], x["hipotese"]["origem"]), ("planejador", "planejador"))
        self.assertEqual(x["esperado"], "um lembrete novo no banco com o texto e o horário")
        self.assertEqual((x["objetivo"]["tipo"], x["alternativas"]), ("lembrar_depois", ["anotar"]))
        self.assertLessEqual(depois[0]["em"], depois[1]["em"])

    def test_toda_afirmacao_tem_tipo_e_so_fato_chega_a_confianca_total(self):
        with mente("criar_lembrete", "Lembrete criado."):
            a = self.rodar([self.lembrete()])
        b = self.rodar([self.lembrete(texto=SEGREDO + "b")])
        c = self.rodar([self.cega()])
        for tid in (a, b, c):
            x = X.da_tarefa(tid)
            for item in x["causas"] + x["aprendido"]:
                self.assertIn(item["tipo"], X.TIPOS)
                if item["tipo"] != X.FATO:
                    self.assertLess(item["confianca"], 1.0, f"{item['tipo']} não é certeza: {item['texto']}")
                else:
                    self.assertEqual(item["confianca"], 1.0)

    def test_uma_tentativa_nunca_vira_regra_universal(self):
        with mente("criar_lembrete", "Lembrete criado."):
            a = self.rodar([self.lembrete()])
        b = self.rodar([self.lembrete(texto=SEGREDO + "b")])
        universal = re.compile(r"\b(sempre|nunca|todos?|todas?|nenhum[a]?|jamais|garantid[oa])\b", re.I)
        for tid in (a, b):
            x = X.da_tarefa(tid)
            for item in x["aprendido"]:
                if item["tipo"] != X.FATO:
                    self.assertFalse(universal.search(item["texto"]), item["texto"])
                    self.assertIn("uma observação", item["texto"])
                self.assertEqual(item["n"], 1)
            self.assertIn("indício, não regra", x["reuso"]["validade"])
            self.assertIn("condições", x["reuso"]["quando"])
            self.assertIn("outras", x["reuso"]["nao_quando"])

    def test_condicoes_ficam_no_registro(self):
        tid = self.rodar([self.lembrete()])
        self.assertEqual(X.da_tarefa(tid)["condicoes"], {"cofre_ativo": True, "manutencao": False})
        self.assertIn("cofre_ativo=sim", X.da_tarefa(tid)["reuso"]["quando"])


class Ambiente(Base):
    def test_reflete_o_estado_de_verdade(self):
        self.assertEqual(X.ambiente(), {"cofre_ativo": True, "manutencao": False})
        with mock.patch.object(MEM, "ativo", return_value=False):
            self.assertEqual(X.ambiente()["cofre_ativo"], False)
        marca = os.path.join(B.BASE, "MANUTENCAO")
        open(marca, "w").close()
        self.addCleanup(os.remove, marca)
        self.assertEqual(X.ambiente()["manutencao"], True)

    def test_compativel_so_compara_chaves_que_os_dois_lados_tem(self):
        self.assertTrue(X.compativel({"a": True}, {"b": 1}))
        self.assertTrue(X.compativel({}, {"a": 1}))
        self.assertTrue(X.compativel({"a": True}, {"a": True, "b": 2}))
        self.assertFalse(X.compativel({"a": True}, {"a": False}))
        self.assertTrue(X.compativel(None, None))


class Sinais(Base):
    def falhar(self, n=1, texto=SEGREDO):
        with mente("criar_lembrete", "Lembrete criado."):
            for i in range(n):
                self.rodar([self.lembrete(texto=f"{texto}-f{i}")])

    def acertar(self, n=1, texto=SEGREDO):
        for i in range(n):
            self.rodar([self.lembrete(texto=f"{texto}-a{i}")])

    def test_sem_dados_vale_meio(self):
        s = X.sinais("criar_lembrete")
        self.assertEqual((s["n"], s["p"], s["confianca"], s["ultimo"], s["ids"]), (0, 0.5, 0.0, None, []))

    def test_contagem_e_probabilidade_suavizada(self):
        self.falhar(1)
        self.assertEqual(X.sinais("criar_lembrete")["p"], 0.3333)
        self.acertar(2)
        s = X.sinais("criar_lembrete")
        self.assertEqual((s["n"], s["sucessos"], s["falhas"], s["p"]), (3, 2, 1, 0.6))
        self.assertEqual(s["confianca"], 0.6)
        self.assertEqual(len(s["ids"]), 3)
        self.assertEqual(s["ultimo"]["resultado"], X.SUCESSO)

    def test_uma_so_falha_nao_zera_a_estrategia(self):
        self.falhar(1)
        self.assertGreater(X.sinais("criar_lembrete")["p"], 0.0)

    def test_so_conta_a_estrategia_pedida(self):
        self.falhar(1)
        self.assertEqual(X.sinais("anotar")["n"], 0)

    def test_condicoes_diferentes_nao_se_misturam(self):
        self.falhar(2)
        igual = X.sinais("criar_lembrete", {"cofre_ativo": True, "manutencao": False})
        outra = X.sinais("criar_lembrete", {"cofre_ativo": False, "manutencao": False})
        self.assertEqual((igual["n"], outra["n"], outra["p"]), (2, 0, 0.5), "o que falhou com o cofre ligado não pesa com o cofre desligado")

    def test_chave_que_so_um_lado_tem_nao_exclui(self):
        self.falhar(1)
        self.assertEqual(X.sinais("criar_lembrete", {"cofre_ativo": True})["n"], 1)
        self.assertEqual(X.sinais("criar_lembrete", {"outra_coisa": 1})["n"], 1)

    def test_ate_limita_ao_que_ja_existia(self):
        self.acertar(1)
        t1 = max(x["em"] for x in X._ultimas())
        self.falhar(1)
        self.assertEqual(X.sinais("criar_lembrete", ate=t1)["n"], 1)
        self.assertEqual(X.sinais("criar_lembrete")["n"], 2)

    def test_relevantes_vem_da_mais_nova_para_a_mais_velha(self):
        self.acertar(1)
        self.falhar(1)
        rs = X.relevantes("criar_lembrete")
        self.assertEqual([r["resultado"] for r in rs], [X.FALHA, X.SUCESSO])
        self.assertEqual(len(X.relevantes("criar_lembrete", limite=1)), 1)

    def test_conferir_escolha_aceita_a_verdadeira_e_acusa_a_adulterada(self):
        self.falhar(1)
        self.acertar(1)
        agora = max(x["em"] for x in X._ultimas())
        cond = {"cofre_ativo": True, "manutencao": False}
        item = {**{k: X.sinais("criar_lembrete", cond)[k] for k in ("n", "sucessos", "falhas", "p")}, "id": "criar_lembrete", "experiencias": X.sinais("criar_lembrete", cond)["ids"]}
        escolha = {"em": agora + 1, "condicoes": cond, "ranking": [item]}
        self.assertEqual(X.conferir_escolha(escolha), (True, []))
        mentira = {**escolha, "ranking": [{**item, "falhas": 0, "p": 0.9}]}
        ok, problemas = X.conferir_escolha(mentira)
        self.assertFalse(ok)
        self.assertTrue(any("falhas" in p for p in problemas) and any("p dito" in p for p in problemas))
        inventada = {**escolha, "ranking": [{**item, "experiencias": item["experiencias"] + ["x9999"]}]}
        self.assertFalse(X.conferir_escolha(inventada)[0])
        self.assertFalse(X.conferir_escolha({"ranking": "x"})[0])
        self.assertFalse(X.conferir_escolha(None)[0])

    def test_uma_escolha_antiga_continua_conferivel_depois_de_novas_experiencias(self):
        self.acertar(1)
        cond = {"cofre_ativo": True, "manutencao": False}
        s = X.sinais("criar_lembrete", cond)
        escolha = {"em": max(x["em"] for x in X._ultimas()) + 0.001, "condicoes": cond,
                   "ranking": [{"id": "criar_lembrete", "n": s["n"], "sucessos": s["sucessos"], "falhas": s["falhas"], "p": s["p"], "experiencias": s["ids"]}]}
        self.falhar(2)
        self.assertEqual(X.conferir_escolha(escolha), (True, []), "a conferência olha o que existia na hora da escolha")


class Padroes(Base):
    """`padroes()` só agrupa o que se repetiu nas MESMAS condições, com desfecho conhecido. Não decide nada: quem usa é `objetivos.py`, que só propõe."""

    def falhar(self, n=1, texto=SEGREDO):
        with mente("criar_lembrete", "Lembrete criado."):
            for i in range(n):
                self.rodar([self.lembrete(texto=f"{texto}-f{i}")])

    def acertar(self, n=1, texto=SEGREDO):
        for i in range(n):
            self.rodar([self.lembrete(texto=f"{texto}-a{i}")])

    def test_sem_repeticao_nao_ha_padrao(self):
        self.assertEqual(X.padroes(), [])
        self.falhar(1)
        self.assertEqual(X.padroes(), [], "uma tentativa é um caso, não um padrão")
        self.assertEqual(len(X.padroes(minimo=1)), 1)

    def test_repeticao_vira_grupo_com_as_provas(self):
        self.falhar(2)
        (g,) = X.padroes()
        self.assertEqual((g["estrategia"], g["sucessos"], g["falhas"], g["origens"]), ("criar_lembrete", 0, 2, {"usuario"}))
        self.assertEqual(g["condicoes"], X.ambiente())
        self.assertEqual(sorted(g["experiencias"]), sorted(x["id"] for x in X._ultimas()))
        self.assertEqual(len(g["tarefas"]), 2)
        self.assertTrue(all(X.obter(i) for i in g["experiencias"]))

    def test_acertos_e_falhas_aparecem_juntos_e_o_mais_falhado_vem_primeiro(self):
        self.acertar(1)
        self.falhar(2)
        (g,) = X.padroes()
        self.assertEqual((g["sucessos"], g["falhas"]), (1, 2))
        self.acertar(3, texto="outro")
        self.assertEqual([(g["sucessos"], g["falhas"]) for g in X.padroes()], [(4, 2)])

    def test_a_estrategia_mais_falhada_vem_primeiro(self):
        with mente("anotar", "Anotei."):
            for i in range(2):
                self.rodar([{"descricao": "salvar como nota", "ferramenta": "anotar", "args": {"texto": f"{SEGREDO}-n{i}"}}])
        self.falhar(3)
        self.assertEqual([(g["estrategia"], g["falhas"]) for g in X.padroes()], [("criar_lembrete", 3), ("anotar", 2)])

    def test_condicoes_diferentes_formam_grupos_diferentes(self):
        with mock.patch.object(X, "ambiente", return_value={"cofre_ativo": True, "manutencao": False}):
            self.falhar(2)
        with mock.patch.object(X, "ambiente", return_value={"cofre_ativo": False, "manutencao": False}):
            self.falhar(1)
        (g,) = X.padroes()
        self.assertEqual((g["falhas"], g["condicoes"]["cofre_ativo"]), (2, True))

    def test_so_conta_desfecho_conhecido(self):
        for _ in range(3):                                           # recusa do corretor: o pedido estava errado, a estratégia não falhou
            self.rodar([{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": "muito", "texto": "a"}}])
        for _ in range(2):                                           # executada, sem como conferir
            self.rodar([self.cega()])
        self.assertEqual(X.padroes(minimo=1), [])

    def test_tentativa_refeita_conta_uma_vez(self):
        self.falhar(1)
        x = X._experiencias()[-1]
        T_ = T.obter(x["tarefa"])
        X.registrar_tarefa(T_)                                       # a mesma tentativa registrada de novo: vale a última, não soma
        self.assertEqual(X.padroes(minimo=1)[0]["falhas"], 1)

    def test_nao_devolve_conteudo(self):
        self.falhar(2)
        self.assertNotIn(SEGREDO, json.dumps(X.padroes(), default=list))


class Persistencia(Base):
    def test_relê_do_arquivo_depois_de_reiniciar(self):
        tid = self.rodar([self.lembrete()])
        X.reiniciar()
        self.assertEqual(X.da_tarefa(tid)["resultado"], X.SUCESSO)
        self.assertEqual(X.resumo()["total"], 1)

    def test_o_arquivo_so_acrescenta(self):
        self.rodar([self.lembrete()])
        antes = self.arquivo()
        self.rodar([self.lembrete(texto=SEGREDO + "2")])
        self.assertTrue(self.arquivo().startswith(antes))

    def test_ids_nao_se_repetem(self):
        for i in range(3):
            self.rodar([self.lembrete(texto=f"{SEGREDO}{i}")])
        ids = [l["id"] for l in self.linhas() if l["k"] == "experiencia"]
        self.assertEqual(ids, ["x0001", "x0002", "x0003"])
        X.reiniciar()
        self.rodar([self.lembrete(texto=SEGREDO + "9")])
        self.assertEqual([l["id"] for l in self.linhas() if l["k"] == "experiencia"][-1], "x0004")

    def test_linha_estragada_e_contada_e_nao_derruba(self):
        self.rodar([self.lembrete()])
        with open(self.base(".cerebro", "experiencias.jsonl"), "a", encoding="utf-8") as f:
            f.write("isto não é json\n")
            f.write(json.dumps({"k": "experiencia", "id": "x0099", "tarefa": "t0001", "resultado": "inventado", "estrategia": {"id": "criar_lembrete"}}) + "\n")
            f.write(json.dumps({"k": "experiencia", "id": "x0098", "tarefa": "t0001", "resultado": "sucesso", "estrategia": {"id": "rm -rf /"}}) + "\n")
            f.write(json.dumps({"k": "outra_coisa"}) + "\n")
        X.reiniciar()
        r = X.resumo()
        self.assertEqual((r["total"], r["descartadas"]), (1, 4), "só o registro bom fica; as 4 linhas ruins são contadas, não escondidas")

    def test_tipo_de_afirmacao_invalido_e_descartado(self):
        tid = self.rodar([self.lembrete()])
        linha = [l for l in self.linhas() if l["k"] == "experiencia"][0]
        linha["id"] = "x0050"
        linha["aprendido"] = [{"texto": "vale sempre", "tipo": "verdade_absoluta", "confianca": 1.0}, {"texto": "bom", "tipo": "fato", "confianca": 1.0}]
        with open(self.base(".cerebro", "experiencias.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(linha) + "\n")
        X.reiniciar()
        x = X.obter("x0050")
        self.assertEqual([a["texto"] for a in x["aprendido"]], ["bom"])

    def test_confianca_fora_da_faixa_vira_zero(self):
        self.rodar([self.lembrete()])
        linha = [l for l in self.linhas() if l["k"] == "experiencia"][0]
        linha["id"] = "x0051"
        linha["causas"] = [{"texto": "x", "tipo": "hipotese", "confianca": 7}]
        with open(self.base(".cerebro", "experiencias.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(linha) + "\n")
        X.reiniciar()
        self.assertEqual(X.obter("x0051")["causas"][0]["confianca"], 0.0)

    def test_com_o_cofre_desligado_aprende_so_na_memoria_do_processo(self):
        with mock.patch.object(MEM, "ativo", return_value=False):
            tid = T.criar("x", passos=[{"descricao": "avisar", "ferramenta": "silenciar", "args": {"minutos": 1}}])
            T.executar(tid)
            F.voltar_a_falar()
            self.assertEqual(X.da_tarefa(tid)["resultado"], X.SUCESSO)
            self.assertEqual(X.sinais("silenciar", {"cofre_ativo": False})["sucessos"], 1)
        self.assertFalse(os.path.exists(self.base(".cerebro", "experiencias.jsonl")), "nada foi escrito em disco")


class Privacidade(Base):
    def test_o_conteudo_pedido_nao_vai_para_o_registro(self):
        with mente("criar_lembrete", "Lembrete criado."):
            self.rodar([self.lembrete(texto=SEGREDO)], objetivo="lembrar de beber água")
        self.rodar([{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO + "n"}}])
        self.rodar([{"descricao": "avisar", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO + "s"}}])
        self.assertNotIn(SEGREDO, self.arquivo())
        for nome, txt in self.todo_o_disco():
            if nome != "tarefas.json":                     # o estado das tarefas tem as suas regras próprias (test_tarefas.py); aqui vale o registro de experiências e o resto
                self.assertNotIn(SEGREDO, txt, nome)

    def test_objetivo_com_dado_pessoal_sai_redigido(self):
        self.rodar([self.lembrete()], objetivo="ligar para (11) 98888-0002 e dizer a senha é abc12345 do wifi")
        txt = self.arquivo()
        self.assertNotIn("98888", txt)
        self.assertNotIn("abc12345", txt)

    def test_auditoria_continua_sem_conteudo_e_integra(self):
        antes = 0
        if os.path.exists(B.AUDITORIA):
            with open(B.AUDITORIA, encoding="utf-8") as f:
                antes = len(f.read().splitlines())
        self.rodar([self.lembrete()])
        with open(B.AUDITORIA, encoding="utf-8") as f:
            txt = f.read()
        self.assertNotIn(SEGREDO, txt)
        self.assertEqual(len(txt.splitlines()) - antes, 1, "registrar a experiência não escreve na auditoria")
        self.assertTrue(B.verificar_auditoria()[0])

    def todo_o_disco(self):
        achados = []
        for raiz, _, nomes in os.walk(self.base()):
            for n in nomes:
                if n.endswith((".json", ".jsonl")):
                    with open(os.path.join(raiz, n), encoding="utf-8") as f:
                        achados.append((n, f.read()))
        return achados


class Robustez(Base):
    def test_falha_ao_gravar_nao_atrapalha_a_tarefa_e_fica_contada(self):
        with mock.patch.object(X, "_acrescentar", return_value=False):
            tid = self.rodar([self.lembrete()])
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        r = X.resumo()
        self.assertEqual(r["erros"], 1)
        self.assertEqual(r["total"], 0)

    def test_erro_inesperado_no_gancho_nao_atrapalha_e_fica_contado(self):
        with mock.patch.object(X, "registrar_tarefa", side_effect=RuntimeError("bug")):
            tid = self.rodar([self.lembrete()])
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        self.assertEqual(X.resumo()["erros"], 1)
        self.assertIn("RuntimeError", X._ERROS["ultimo"])

    def test_o_gancho_esta_registrado_uma_vez_so(self):
        X._registrar_gancho()
        X._registrar_gancho()
        self.assertEqual(sum(1 for g in T.GANCHOS_FIM if getattr(g, "_friday_experiencias", False)), 1)

    def test_intencao_invalida_e_recusada(self):
        with self.assertRaises(ValueError):
            X.intencao("tarefa", 1, tipo="x", estrategia="rm -rf /", descricao="", hipotese="", esperado="")
        with self.assertRaises(ValueError):
            X.intencao("t1", 1, tipo="x", estrategia="anotar", descricao="", hipotese="", esperado="")

    def test_gancho_nao_chama_o_corretor(self):
        with mock.patch.object(B, "executar_estruturado", side_effect=AssertionError("o registro não executa nada")), \
                mock.patch.object(B, "executar", side_effect=AssertionError("o registro não executa nada")):
            X.registrar_tarefa(T.obter(self.rodar([self.lembrete()])))


class Voz(Base):
    def test_sem_experiencias_diz_que_ainda_nao_tem(self):
        self.assertIn("Ainda não tenho", X.tratar("o que você aprendeu com as tarefas?"))
        self.assertIn("Ainda não tenho", X.tratar("Minhas experiências"))

    def test_fala_honesta_com_poucos_casos(self):
        with mente("criar_lembrete", "Lembrete criado."):
            self.rodar([self.lembrete()])
        self.rodar([self.lembrete(texto=SEGREDO + "b")])
        fala = X.tratar("o que você aprendeu com as tarefas")
        self.assertIn("2 experiência", fala)
        self.assertIn("1 deram certo", fala)
        self.assertIn("1 falharam", fala)
        self.assertIn("indício", fala)
        self.assertIn("não são regra", fala)
        self.assertNotIn(SEGREDO, fala)

    def test_outras_falas_passam(self):
        for t in ("oi", "quais são as minhas tarefas", "", "x" * 300, None, 5, "o que você aprendeu hoje na escola de samba"):
            self.assertIsNone(X.tratar(t))


class SoRegistra(unittest.TestCase):
    def test_nao_ha_chamada_ao_corretor_para_executar(self):
        """Experiência só observa: o módulo não chama `executar`, não registra ferramenta e não toca em tarefas além de ler e ouvir o fim."""
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "friday", "experiencias.py"), encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        usos = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "B"}
        self.assertEqual(usos, {"BASE"}, "só olha a pasta do corretor (para saber se está em manutenção)")
        tarefas = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "T"}
        self.assertTrue(tarefas <= {"GANCHOS_FIM", "CONCLUIDA", "CANCELADA", "EXECUTADA_SEM_VERIFICACAO", "FALHOU"}, tarefas)

    def test_a_ia_nao_ganhou_ferramenta_de_experiencia(self):
        for nome, f in B.FERRAMENTAS.items():
            self.assertNotIn("experienc", nome.lower())
            self.assertNotIn("experienc", str(f.get("descricao", "")).lower())


if __name__ == "__main__":
    unittest.main()
