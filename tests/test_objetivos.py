"""Fase 4 — objetivos propostos por ela mesma (friday/objetivos.py): propor ≠ planejar ≠ ser autorizada a executar.

Mapa dos testes da missão:  F (confirmação ambígua nunca autoriza: «sim», «pode», «faz» não aprovam nada) · G privacidade (nem o conteúdo do dono vai para a proposta, o histórico ou a auditoria) ·
D (reinício no meio da execução: a proposta se acerta com a tarefa, sem repetir o que foi feito) · I (coordenação: uma proposta aberta por assunto, no máximo 5 esperando, nada duplicado).
Aqui: ela só PROPÕE (com justificativa e experiências como evidência), o dono AUTORIZA por frase explícita, o planejador PLANEJA e o corretor EXECUTA — e o dono pode pausar, retomar e cancelar.
"""
import ast, json, os, re, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import experiencias as X, memoria as MEM, objetivos as O, planejador as PL, tarefas as T
from test_experiencias import Base as BaseX
from test_tarefas import mente, SEGREDO

RAIZ = Path(os.path.dirname(os.path.abspath(__file__))).parent / "friday"
TEXTO = "observação de teste"


class Base(BaseX):
    GANCHO = False          # os testes de `propor` direto criam falhas de apoio; o gancho automático só fica ligado onde ele é o assunto

    def setUp(self):
        super().setUp()
        O.reiniciar()
        self.addCleanup(O.reiniciar)
        if not self.GANCHO:
            T.GANCHOS_FIM[:] = [g for g in T.GANCHOS_FIM if g is not O._ao_terminar_tarefa]
            self.addCleanup(O._registrar_gancho)

    def falso_sucesso(self, n=1, texto=SEGREDO, **kw):
        """n tarefas do dono em que a ferramenta diz «guardei» mas o efeito não existe (falso sucesso). Devolve os ids das tarefas."""
        tids = []
        for _ in range(n):
            with mente("guardar_memoria", "Guardei na memória."):
                tids.append(self.rodar([{"descricao": "guardar na memória", "ferramenta": "guardar_memoria", "args": {"texto": texto}}], **kw))
        return tids

    def base_proposta(self, chave="k1"):
        tid = self.falso_sucesso(1)[0]
        return {"tipo": "registrar_informacao", "params": {"texto": TEXTO, "titulo": "teste"}, "titulo": "anotar o teste", "justificativa": "porque as experiências mostram isso",
                "evidencias": [X.da_tarefa(tid)["id"]], "vinculo": tid, "chave": chave}

    def propor(self, base, **mudar):
        k = {**base, **mudar}
        return O.propor(k.pop("tipo"), k.pop("params"), **k)

    def nova(self, chave="k1"):
        base = self.base_proposta(chave)
        ok, p = self.propor(base)
        self.assertTrue(ok, p)
        return p

    def no_cofre(self, texto):
        return any(texto in a.read_text(encoding="utf-8", errors="replace") for a in self.base().rglob("*.md"))

    def arquivos_de_estado(self):
        # tarefas.json guarda, de propósito, os argumentos de baixo risco de tarefas que falharam (para tentar de novo); o que se confere aqui são os arquivos de objetivos e de experiências
        return "".join(a.read_text(encoding="utf-8", errors="replace") for a in self.base(".cerebro").glob("*") if a.is_file() and a.suffix in (".json", ".jsonl") and a.name != "tarefas.json" and "tarefas_historico" not in a.name)


class Proposta(Base):
    def test_proposta_valida_nasce_como_proposta_e_nada_e_executado(self):
        base = self.base_proposta()
        tarefas0 = len(T.listar())
        with mock.patch.object(T, "criar", side_effect=AssertionError("propor não cria tarefa")), \
                mock.patch.object(B, "executar_estruturado", side_effect=AssertionError("propor não chama o corretor")):
            ok, p = self.propor(base)
        self.assertTrue(ok, p)
        self.assertEqual((p["id"], p["estado"], p["decidida_por"], p["resultado"]), ("o01", "proposto", None, None))
        self.assertEqual(p["limites"], {"nivel_max": 1, "max_tentativas": 2, "acao_externa": False})
        self.assertEqual(p["vinculo"], {"tarefa": base["vinculo"], "origem": "usuario"})
        self.assertEqual(len(T.listar()), tarefas0)
        self.assertFalse(self.no_cofre(TEXTO), "a proposta não escreve nada no cofre")

    def test_o_que_nao_pode_ser_proposto_e_recusado(self):
        base = self.base_proposta()
        propria = T.criar("tarefa dela", origem="propria")
        casos = {
            "tipo que o catálogo não permite como próprio": {"tipo": "lembrar_depois", "params": {"texto": "x", "minutos": 5}},
            "tipo inexistente": {"tipo": "apagar_tudo"},
            "sem o texto": {"params": {"titulo": "só o título"}},
            "parâmetro desconhecido": {"params": {"texto": TEXTO, "comando": "rm"}},
            "conteúdo sensível": {"params": {"texto": "minha senha é hunter2xyz"}},
            "sem evidência": {"evidencias": []},
            "evidência que não existe": {"evidencias": ["x9999"]},
            "evidência fora do formato": {"evidencias": ["../x0001"]},
            "evidência que não é lista": {"evidencias": "x0001"},
            "tarefa inexistente": {"vinculo": "t9999"},
            "vínculo fora do formato": {"vinculo": "tarefa"},
            "vínculo com tarefa que ela mesma criou": {"vinculo": propria},
            "sem justificativa": {"justificativa": "  "},
        }
        for nome, mudar in casos.items():
            with self.subTest(nome):
                ok, motivo = self.propor(base, **mudar)
                self.assertFalse(ok, nome)
                self.assertIsInstance(motivo, str)
        self.assertEqual(O.listar(), [], "nenhuma proposta recusada deixa rastro")

    def test_I_uma_proposta_aberta_por_assunto(self):
        base = self.base_proposta()
        self.assertTrue(self.propor(base)[0])
        ok, motivo = self.propor(base)
        self.assertEqual((ok, "já existe uma proposta aberta" in motivo), (False, True))
        self.assertEqual(len(O.listar()), 1)

    def test_I_no_maximo_cinco_esperando_o_dono(self):
        base = self.base_proposta()
        for i in range(O.MAX_ABERTAS):
            self.assertTrue(self.propor(base, chave=f"k{i}")[0])
        ok, motivo = self.propor(base, chave="outra")
        self.assertEqual((ok, "demais esperando" in motivo), (False, True))
        self.assertTrue(O.pausar("o01"))
        self.assertFalse(self.propor(base, chave="outra")[0], "pausada ainda ocupa uma vaga")
        self.assertTrue(O.cancelar("o02"))
        self.assertTrue(self.propor(base, chave="outra")[0], "cancelada libera a vaga")

    def test_o_que_o_dono_recusou_nao_volta(self):
        base = self.base_proposta()
        self.assertTrue(self.propor(base)[0])
        self.assertTrue(O.cancelar("o01"))
        ok, motivo = self.propor(base)
        self.assertEqual((ok, "já recusou" in motivo), (False, True))
        self.assertTrue(self.propor(base, chave="outro assunto")[0], "outro assunto não é afetado")

    def test_so_volta_a_propor_depois_de_fazer_se_houver_algo_novo(self):
        base = self.base_proposta()
        self.assertTrue(self.propor(base, falhas_na_epoca=2)[0])
        self.assertTrue(O.aprovar("o01")[0])
        self.assertEqual(O.obter("o01")["estado"], "concluido")
        self.assertFalse(self.propor(base, falhas_na_epoca=3)[0], "uma falha a mais não é novidade")
        ok, p = self.propor(base, falhas_na_epoca=4)
        self.assertTrue(ok, p)
        self.assertEqual(p["id"], "o02")

    def test_a_proposta_persiste_e_volta_igual(self):
        p = self.nova()
        O.reiniciar()
        self.assertEqual(O.obter("o01"), p)
        self.assertEqual(self.nova("k2")["id"], "o02", "o contador continua de onde parou")


class DoPadrao(Base):
    GANCHO = True
    """Ela olha as próprias experiências e PROPÕE; nunca age. Só falha repetida, sem nenhum acerto, nas mesmas condições, em tarefas do dono."""

    def test_uma_falha_so_nao_vira_proposta(self):
        self.falso_sucesso(1)
        self.assertEqual(O.listar(), [])

    def test_duas_falhas_iguais_viram_uma_proposta_pelo_gancho(self):
        t1, t2 = self.falso_sucesso(2)
        (p,) = O.listar()
        self.assertEqual((p["id"], p["estado"], p["tipo"], p["vinculo"]["tarefa"]), ("o01", "proposto", "registrar_informacao", t2))
        self.assertEqual(sorted(p["evidencias"]), sorted([X.da_tarefa(t1)["id"], X.da_tarefa(t2)["id"]]))
        self.assertTrue(all(X.obter(e) for e in p["evidencias"]), "cada evidência é uma experiência que existe")
        self.assertIn("guardar_memoria", p["titulo"])
        self.assertIn("2 vezes", p["justificativa"])
        self.assertIn("indício, não regra", p["params"]["texto"], "poucas observações não viram regra")
        self.assertEqual(T.obter(t2)["contexto"]["origem"], "usuario")
        self.assertEqual(len([t for t in T.listar() if t["contexto"]["origem"] == "propria"]), 0, "propor não cria tarefa dela")

    def test_nao_propoe_de_novo_o_mesmo_assunto(self):
        self.falso_sucesso(3)
        self.assertEqual(len(O.listar()), 1)

    def test_com_um_acerto_nas_mesmas_condicoes_nao_ha_padrao(self):
        self.rodar([{"descricao": "guardar na memória", "ferramenta": "guardar_memoria", "args": {"texto": "algo que funciona"}}])
        self.assertEqual(X.sinais("guardar_memoria")["sucessos"], 1)
        self.falso_sucesso(2)
        self.assertEqual(O.listar(), [])

    def test_condicoes_diferentes_nao_se_somam(self):
        with mock.patch.object(X, "ambiente", return_value={"cofre_ativo": True, "manutencao": False}):
            self.falso_sucesso(1)
        with mock.patch.object(X, "ambiente", return_value={"cofre_ativo": False, "manutencao": False}):
            self.falso_sucesso(1)
        self.assertEqual(O.listar(), [])

    def test_o_que_ela_fez_por_conta_propria_nao_alimenta_novas_propostas(self):
        self.falso_sucesso(2, origem="propria")
        self.assertEqual(O.listar(), [], "só tarefas que o dono pediu servem de base: sem laço de autoalimentação")

    def test_mesmo_chamando_direto_o_que_e_dela_nao_serve_de_base(self):
        self.falso_sucesso(3, origem="propria")
        self.assertEqual(O.propor_a_partir_das_experiencias(), [], "a defesa vale também fora do gancho")
        self.assertEqual(O.listar(), [])

    def test_recusa_do_corretor_nao_e_falha_da_estrategia(self):
        for _ in range(3):
            self.rodar([{"descricao": "x", "ferramenta": "guardar_memoria", "args": {"texto": 7}}])
        self.assertEqual(O.listar(), [])

    def test_o_gancho_nunca_atrapalha_a_tarefa(self):
        with mock.patch.object(O, "propor_a_partir_das_experiencias", side_effect=RuntimeError("quebrou")):
            tids = self.falso_sucesso(1)
        self.assertEqual(T.obter(tids[0])["estado"], T.FALHOU, "a tarefa terminou normalmente")
        self.assertEqual(O.resumo()["erros"], 1, "e o erro ficou contado, não escondido")


class Aprovacao(Base):
    def test_aprovar_por_voz_executa_pelo_planejador_e_confere_o_efeito(self):
        self.nova()
        fala = O.tratar("Aprova o objetivo 1!")
        self.assertIn("Pronto", fala)
        p = O.obter("o01")
        self.assertEqual((p["estado"], p["decidida_por"], p["resultado"]["decisao"]), ("concluido", "dono", "concluir"))
        t = T.obter(p["resultado"]["tarefa"])
        self.assertEqual((t["contexto"]["origem"], t["estado"]), ("propria", T.CONCLUIDA))
        self.assertIn("proposta o01 aprovada pelo dono", t["contexto"]["restricoes"])
        self.assertEqual(t["passos"][0]["verificacao"]["forca"], "independente")
        self.assertEqual(self.notas(f"teste: {TEXTO}"), 1, "o efeito existe de verdade, não só a resposta da ferramenta")
        x = X.da_tarefa(t["id"])
        self.assertEqual((x["objetivo"]["origem"], x["estrategia"]["id"]), ("propria", "anotar"), "a experiência fica registrada como dela")
        self.assertEqual(x["escolha"]["escolhida"], "anotar", "e a proposta já nasce usando o que ela aprendeu: guardar_memoria falhou antes, então começa por outra")

    def test_F_resposta_vaga_nunca_aprova(self):
        self.nova()
        for frase in ("sim", "pode", "pode fazer", "faz aí", "ok", "aprova", "aprovo", "aprova o objetivo", "aprova os objetivos", "aprova tudo", "sim, aprova o objetivo 1",
                      "claro que sim", "confirmo", "manda ver", "aprova o objetivo um", "aprova o objetivo 1 e o 2", "objetivo 1"):
            with self.subTest(frase):
                self.assertIsNone(O.tratar(frase))
        self.assertEqual(O.obter("o01")["estado"], "proposto")
        self.assertEqual((len(T.listar(estados=(T.CONCLUIDA,))), self.no_cofre(TEXTO)), (0, False))

    def test_so_o_texto_curto_do_dono_vale(self):
        self.nova()
        self.assertIsNone(O.tratar("aprova o objetivo 1 " + "e " * 120))
        self.assertIsNone(O.tratar(None))
        self.assertIsNone(O.tratar(7))
        self.assertEqual(O.obter("o01")["estado"], "proposto")

    def test_objetivo_inexistente(self):
        self.assertEqual(O.tratar("aprova o objetivo 9"), "Não aprovei: não achei esse objetivo.")

    def test_nao_executa_duas_vezes(self):
        self.nova()
        O.tratar("aprova o objetivo 1")
        n = len(T.listar())
        self.assertIn("está concluido", O.tratar("aprova o objetivo 1"))
        self.assertEqual(len(T.listar()), n, "a segunda aprovação não criou nada")

    def test_estrategia_que_falha_troca_de_estrategia_dentro_do_limite_da_proposta(self):
        self.nova()
        with mente("anotar", "Anotei."):
            O.tratar("aprova o objetivo 1")
        p = O.obter("o01")
        self.assertEqual(p["estado"], "concluido")
        t = T.obter(p["resultado"]["tarefa"])
        self.assertEqual(t["plano_v"], 2, "tentou a segunda estratégia equivalente")
        self.assertEqual([(X.da_tarefa(t["id"], v)["estrategia"]["id"], X.da_tarefa(t["id"], v)["resultado"]) for v in (1, 2)], [("anotar", X.FALHA), ("criar_arquivo", X.SUCESSO)])
        self.assertEqual(self.notas(f"teste: {TEXTO}"), 0, "a primeira não produziu efeito")

    def test_tudo_falha_a_proposta_falha_e_nao_finge(self):
        self.nova()
        with mente("guardar_memoria", "ok"), mente("anotar", "ok"), mente("criar_arquivo", "ok"):
            fala = O.tratar("aprova o objetivo 1")
        p = O.obter("o01")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("Não consegui", fala)
        self.assertEqual(self.notas(f"teste: {TEXTO}"), 0)

    def test_o_limite_da_proposta_e_o_do_codigo_nao_o_do_arquivo(self):
        self.nova()
        arq = self.base(".cerebro", "objetivos_proprios.json")
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["propostas"]["o01"]["limites"] = {"nivel_max": 3, "max_tentativas": 99, "acao_externa": True}
        arq.write_text(json.dumps(d), encoding="utf-8")
        O.reiniciar()
        self.assertEqual(O.obter("o01")["limites"], O.LIMITES)
        with mock.patch.object(PL, "executar_objetivo", wraps=PL.executar_objetivo) as espia:
            O.tratar("aprova o objetivo 1")
        self.assertEqual((espia.call_args.kwargs["nivel_max"], espia.call_args.kwargs["max_tentativas"], espia.call_args.kwargs["autorizado_por"]), (1, 2, "dono"))

    def test_aprovar_e_o_unico_caminho_para_executar(self):
        p = self.nova()
        with mock.patch.object(PL, "executar_objetivo", side_effect=AssertionError("só a aprovação do dono executa")):
            for _ in range(3):
                O.resumo(), O.falar(), O.conciliar(), O.listar()
            self.falso_sucesso(1)                                  # novas tarefas e ganchos também não executam
        self.assertEqual(O.obter(p["id"])["estado"], "proposto")


class PausaECancelamento(Base):
    def test_pausada_nao_pode_ser_aprovada_ate_retomar(self):
        self.nova()
        self.assertEqual(O.tratar("pausa o objetivo 1"), "Pausei o objetivo 1.")
        self.assertIn("pausado", O.tratar("aprova o objetivo 1"))
        self.assertEqual(O.obter("o01")["estado"], "pausado")
        self.assertEqual(O.tratar("retoma o objetivo 1"), "Retomei o objetivo 1.")
        self.assertIn("Pronto", O.tratar("aprova o objetivo 1"))

    def test_cancelar_por_qualquer_das_formas(self):
        for i, frase in enumerate(("cancela o objetivo 1", "recusa o objetivo 1", "não quero o objetivo 1", "cancelar objetivo 1")):
            with self.subTest(frase):
                O.reiniciar()
                self.nova(chave=f"c{i}")
                n = int(O.listar()[-1]["id"][1:])
                self.assertEqual(O.tratar(frase.replace("1", str(n))), f"Cancelei o objetivo {n}.")
                self.assertEqual(O.obter(f"o{n:02d}")["estado"], "cancelado")
                self.assertIn("cancelado", O.tratar(f"aprova o objetivo {n}"))

    def test_pausar_ou_retomar_fora_do_estado_certo_nao_muda_nada(self):
        self.nova()
        O.tratar("aprova o objetivo 1")
        for frase in ("pausa o objetivo 1", "retoma o objetivo 1", "cancela o objetivo 1", "pausa o objetivo 7"):
            self.assertIn("Não mudei nada", O.tratar(frase), frase)
        self.assertEqual(O.obter("o01")["estado"], "concluido")

    def test_cancelar_cancela_so_a_tarefa_que_a_proposta_criou(self):
        p = self.nova()
        marca = f"proposta {p['id']} aprovada pelo dono"
        dela = T.criar("tarefa que a proposta criou", origem="propria", restricoes=[marca])
        do_dono = T.criar("tarefa do dono com texto parecido", origem="usuario", restricoes=[marca])
        O.ARQ.get()["propostas"][p["id"]]["estado"] = "esperando"
        self.assertTrue(O.cancelar(p["id"]))
        self.assertEqual((T.obter(dela)["estado"], T.obter(do_dono)["estado"]), (T.CANCELADA, T.CRIADA))

    def test_cancelar_no_meio_da_execucao_vale_o_cancelamento(self):
        p = self.nova()

        def cancela_no_meio(*a, **k):
            O.cancelar(p["id"])
            return {"decisao": "concluir", "mensagem": "Pronto.", "tarefa": None}
        with mock.patch.object(PL, "executar_objetivo", cancela_no_meio):
            fala = O.tratar("aprova o objetivo 1")
        self.assertEqual(O.obter(p["id"])["estado"], "cancelado")
        self.assertIn("cancelado", fala)

    def test_historico_so_acrescenta_e_diz_quem_decidiu(self):
        self.nova()
        O.tratar("pausa o objetivo 1")
        O.tratar("retoma o objetivo 1")
        O.tratar("aprova o objetivo 1")
        p = O.obter("o01")
        self.assertEqual([h["para"] for h in p["historico"]], ["proposto", "pausado", "proposto", "executando", "concluido"])
        linhas = [json.loads(l) for l in self.base(".cerebro", "objetivos_proprios_historico.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l["para"] for l in linhas], [h["para"] for h in p["historico"]])
        self.assertEqual([l["por"] for l in linhas], [None, "dono", "dono", "dono", None])


class Reinicio(Base):
    """Teste D, no nível das propostas: o processo caiu no meio. A verdade está na tarefa; nada é repetido."""

    def test_caiu_antes_de_comecar_volta_a_esperar_o_dono_sem_executar_nada(self):
        p = self.nova()
        O.ARQ.get()["propostas"][p["id"]]["estado"] = "executando"
        O.ARQ.salvar()
        O.reiniciar()                                              # processo novo: relê o disco
        with mock.patch.object(PL, "executar_objetivo", side_effect=AssertionError("não executa sozinha")):
            self.assertEqual(O.conciliar(), 1)
        q = O.obter(p["id"])
        self.assertEqual(q["estado"], "proposto")
        self.assertIn("nada foi feito", q["historico"][-1]["motivo"])
        self.assertFalse(self.no_cofre(TEXTO))

    def test_caiu_depois_de_terminar_segue_o_estado_da_tarefa(self):
        p = self.nova()
        marca = f"proposta {p['id']} aprovada pelo dono"
        tid = T.criar("registrar", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}], origem="propria", restricoes=[marca])
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        O.ARQ.get()["propostas"][p["id"]]["estado"] = "executando"
        self.assertEqual(O.conciliar(), 1)
        q = O.obter(p["id"])
        self.assertEqual((q["estado"], q["resultado"]["tarefa"]), ("concluido", tid))
        self.assertEqual(O.conciliar(), 0, "conciliar de novo não muda nada")
        self.assertEqual(self.notas(), 1, "e a ação não foi repetida")

    def test_sem_como_conferir_espera_o_dono_e_depois_conclui(self):
        p = self.nova()
        marca = f"proposta {p['id']} aprovada pelo dono"
        tid = T.criar("fazer algo sem conferência", passos=[self.cega()], origem="propria", restricoes=[marca])
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.EXECUTADA_SEM_VERIFICACAO)
        O.ARQ.get()["propostas"][p["id"]]["estado"] = "executando"
        O.conciliar()
        self.assertEqual(O.obter(p["id"])["estado"], "esperando")
        self.assertTrue(T.confirmar_manual(tid)[0])
        O.conciliar()
        self.assertEqual(O.obter(p["id"])["estado"], "concluido")

    def test_erro_na_execucao_nao_e_escondido_e_a_proposta_nao_fica_travada(self):
        self.nova()
        with mock.patch.object(PL, "executar_objetivo", side_effect=RuntimeError("quebrou")):
            fala = O.tratar("aprova o objetivo 1")
        self.assertIn("RuntimeError", fala)
        self.assertIn("continua", fala)
        self.assertEqual(O.resumo()["erros"], 1)
        self.assertEqual(O.obter("o01")["estado"], "proposto", "sem tarefa, nada começou: volta a esperar o dono")
        self.assertEqual(O._EM_EXECUCAO, set())
        self.assertIn("Pronto", O.tratar("aprova o objetivo 1"), "e dá para tentar de novo")

    def test_enquanto_ela_executa_a_conciliacao_nao_mexe_na_proposta(self):
        self.nova()
        vistas = []

        def fingindo(*a, **k):
            vistas.append((O.conciliar(), O.obter("o01")["estado"]))
            return {"decisao": "concluir", "mensagem": "Pronto.", "tarefa": None}
        with mock.patch.object(PL, "executar_objetivo", fingindo):
            O.aprovar("o01")
        self.assertEqual(vistas, [(0, "executando")])

    def test_dois_pedidos_ao_mesmo_tempo_executam_uma_vez(self):
        import threading
        self.nova()
        saidas = []
        barreira = threading.Barrier(2)

        def tenta():
            barreira.wait()
            saidas.append(O.aprovar("o01")[0])
        ts = [threading.Thread(target=tenta) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(saidas), [False, True])
        self.assertEqual(len([t for t in T.listar() if t["contexto"]["origem"] == "propria"]), 1)


class ArquivoAdulterado(Base):
    """O arquivo de propostas é validado ao ler: editar o disco não vira autorização nem afrouxa um limite."""

    def mexer(self, f):
        self.nova()
        arq = self.base(".cerebro", "objetivos_proprios.json")
        d = json.loads(arq.read_text(encoding="utf-8"))
        f(d["propostas"]["o01"])
        arq.write_text(json.dumps(d), encoding="utf-8")
        O.reiniciar()
        return O.obter("o01")

    def test_o_que_nao_se_sustenta_e_descartado_ao_ler(self):
        troca = {
            "tipo não permitido": lambda p: p.update(tipo="lembrar_depois", params={"texto": "x", "minutos": 5}),
            "tipo inexistente": lambda p: p.update(tipo="apagar_tudo"),
            "conteúdo sensível": lambda p: p.update(params={"texto": "minha senha é hunter2xyz"}),
            "parâmetro extra": lambda p: p["params"].update(comando="rm -rf"),
            "evidências inválidas": lambda p: p.update(evidencias=["../../x"]),
            "sem evidências": lambda p: p.update(evidencias=[]),
            "sem vínculo": lambda p: p.update(vinculo={}),
            "id trocado": lambda p: p.update(id="o77"),
        }
        for nome, f in troca.items():
            with self.subTest(nome):
                O.reiniciar()
                self.assertIsNone(self.mexer(f), nome)
                self.base(".cerebro", "objetivos_proprios.json").unlink()
                O.reiniciar()

    def test_estado_desconhecido_vira_pausado_e_quem_decidiu_so_pode_ser_o_dono(self):
        q = self.mexer(lambda p: p.update(estado="aprovado_pela_ia", decidida_por="ia"))
        self.assertEqual((q["estado"], q["decidida_por"]), ("pausado", None))

    def test_dizer_executando_no_disco_nao_executa_nada(self):
        q = self.mexer(lambda p: p.update(estado="executando"))
        with mock.patch.object(PL, "executar_objetivo", side_effect=AssertionError("não executa sozinha")):
            O.conciliar()
        self.assertEqual(O.obter("o01")["estado"], "proposto")
        self.assertFalse(self.no_cofre(TEXTO))

    def test_arquivo_estragado_nao_derruba_nada(self):
        for lixo in ("não é json", "[]", '{"propostas": 7}', '{"propostas": {"o01": 7}, "proximo": "x"}', "{" * 50):
            with self.subTest(lixo[:12]):
                self.base(".cerebro").mkdir(parents=True, exist_ok=True)
                self.base(".cerebro", "objetivos_proprios.json").write_text(lixo, encoding="utf-8")
                O.reiniciar()
                self.assertEqual(O.listar(), [])
                self.assertEqual(self.nova()["id"], "o01")
                O.reiniciar()
                self.base(".cerebro", "objetivos_proprios.json").unlink()


class Privacidade(Base):
    GANCHO = True

    def test_G_o_conteudo_do_dono_nao_vai_para_a_proposta_nem_para_o_historico_nem_para_a_auditoria(self):
        self.falso_sucesso(2, texto=SEGREDO)
        self.assertEqual(len(O.listar()), 1)
        O.tratar("aprova o objetivo 1")
        O.tratar("quais objetivos você propõe")
        for nome, conteudo in (("estado", self.arquivos_de_estado()), ("cofre", "".join(a.read_text(encoding="utf-8", errors="replace") for a in self.base().rglob("*.md")))):
            self.assertNotIn(SEGREDO, conteudo, nome)
        if os.path.exists(B.AUDITORIA):
            with open(B.AUDITORIA, encoding="utf-8") as f:
                self.assertNotIn(SEGREDO, f.read())
        self.assertNotIn(SEGREDO, json.dumps(O.listar(), ensure_ascii=False) + json.dumps(O.resumo()) + O.falar())

    def test_a_voz_e_o_painel_nao_trazem_conteudo(self):
        self.nova()
        self.assertEqual(set(O.resumo()), {"propostas", "executando", "concluidos", "recusados", "erros"})
        self.assertEqual(O.resumo()["propostas"], 1)
        self.assertNotIn(TEXTO, O.falar())


class Voz(Base):
    def test_lista_vazia_e_cheia(self):
        self.assertEqual(O.tratar("quais objetivos você propõe?"), "Não tenho nenhum objetivo proposto esperando você.")
        self.nova()
        fala = O.tratar("Quais são os objetivos que você propõe")
        self.assertIn("1: anotar o teste (proposto)", fala)
        self.assertIn("porque as experiências", fala)
        self.assertIn("nenhum executado sem o seu", fala)

    def test_frases_alheias_passam_adiante(self):
        for frase in ("que horas são", "quais são as minhas tarefas", "aprova meu pedido", "cancela a tarefa 3", "o que você aprendeu com as tarefas"):
            self.assertIsNone(O.tratar(frase), frase)


class SoPropoe(unittest.TestCase):
    """A IA continua só propondo: nenhuma ferramenta dela mexe em objetivos, e só a voz do dono aprova."""

    def modulos(self):
        for f in sorted(RAIZ.glob("*.py")):
            yield f.name, ast.parse(f.read_text(encoding="utf-8"))

    def test_so_a_main_importa_objetivos(self):
        for nome, arv in self.modulos():
            if nome in ("objetivos.py", "main.py"):
                continue
            for n in ast.walk(arv):
                if isinstance(n, ast.Import):
                    self.assertNotIn("objetivos", [a.name for a in n.names], nome)
                if isinstance(n, ast.ImportFrom):
                    self.assertNotEqual(n.module, "objetivos", nome)

    def test_nenhuma_ferramenta_da_ia_toca_em_objetivos(self):
        for nome in B.FERRAMENTAS:
            self.assertNotRegex(nome, r"objetiv|propor|aprov|proposta", nome)
        fonte = (RAIZ / "catalogo.py").read_text(encoding="utf-8") + (RAIZ / "ferramentas.py").read_text(encoding="utf-8") + (RAIZ / "broker.py").read_text(encoding="utf-8")
        self.assertNotRegex(fonte, r"objetivos|\bO\.aprovar")

    def test_aprovar_so_e_chamado_pela_fala_do_dono(self):
        quem = []
        for nome, arv in self.modulos():
            for fn in [n for n in ast.walk(arv) if isinstance(n, ast.FunctionDef)]:
                for c in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
                    alvo = c.func.attr if isinstance(c.func, ast.Attribute) else c.func.id if isinstance(c.func, ast.Name) else ""
                    if alvo == "aprovar":
                        quem.append((nome, fn.name))
        self.assertEqual(quem, [("objetivos.py", "tratar")])

    def test_objetivos_nao_usa_o_corretor_nem_apaga_nada(self):
        arv = ast.parse((RAIZ / "objetivos.py").read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arv) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(arv) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn("broker", importados)
        self.assertNotIn("subprocess", importados)
        self.assertTrue({"experiencias", "planejador", "tarefas"} <= importados)

    def test_o_catalogo_de_tipos_proprios_so_tem_nivel_1_e_sem_efeito_fora(self):
        proprios = {k: v for k, v in PL.OBJETIVOS.items() if v["permite_proprio"]}
        self.assertEqual(sorted(proprios), ["registrar_informacao"])
        for tipo, obj in proprios.items():
            for e in obj["estrategias"]:
                self.assertLessEqual(PL._nivel_da_estrategia(e, {"texto": "x"}), O.LIMITES["nivel_max"], f"{tipo}/{e['id']}")
                for ferr in e["ferramentas"]:
                    self.assertNotIn(ferr, ("enviar_sms", "ligar", "abrir_url", "acionar_rele", "compartilhar"), f"{tipo}/{e['id']} sai do aparelho")


if __name__ == "__main__":
    unittest.main()
