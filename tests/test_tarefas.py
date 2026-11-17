"""Fase 2 — registro de tarefas (friday/tarefas.py): máquina de estados, execução PELO corretor, conferência do efeito, confirmação, privacidade e persistência.

Mapa dos testes da missão:  A execução básica verificada · B falso sucesso não conclui · F ação sensível não roda com confirmação ambígua ·
G privacidade (auditoria e registro) · (D retomada e I coordenação ficam nas Fases 5–6; aqui só o que elas precisam: gravar antes de executar).
"""
import json, os, re, threading, time, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import ferramentas as F, memoria as MEM, tarefas as T, verificacao as V
from test_neuronios import Cerebro, BIN, LOG

SEGREDO = "zq-conteudo-particular-7752"


def mente(nome, resposta):
    return mock.patch.dict(B.FERRAMENTAS[nome], {"fn": lambda **kw: resposta})


def sms_enviados():
    return E.ler_log(LOG).count("CMD termux-sms-send")


class Base(Cerebro):
    def setUp(self):
        super().setUp()
        T.reiniciar()
        self.addCleanup(T.reiniciar)
        F.voltar_a_falar()
        self.sms0, self.m_lemb, self.m_nota = sms_enviados(), F.marca_lembretes(), F.marca_notas()   # o banco e o log são do processo todo: conta-se só o que nasce neste teste
        self.fim = []
        T.GANCHOS_FIM.append(self.fim.append)
        self.addCleanup(lambda: T.GANCHOS_FIM.remove(self.fim.append) if self.fim.append in T.GANCHOS_FIM else None)

    def sms(self):
        return sms_enviados() - self.sms0

    def lembretes(self, texto=SEGREDO):
        return [r for r in F.lembretes_depois(self.m_lemb) if r[1] == texto]

    def notas(self, texto=SEGREDO):
        return F.notas_depois(self.m_nota).count(texto)

    def lembrete(self, texto=SEGREDO, minutos=7, **extra):
        return {"descricao": "criar um lembrete", "ferramenta": "criar_lembrete", "args": {"minutos": minutos, "texto": texto}, **extra}

    def estados(self, t):
        return [h["para"] for h in t["historico"]]

    def disco(self):
        with open(self.base(".cerebro", "tarefas.json"), encoding="utf-8") as f:
            return json.load(f)


class MaquinaDeEstados(Base):
    def test_todo_estado_tem_regra_e_os_finais_nao_saem(self):
        self.assertEqual(set(T.TRANSICOES), set(T.ESTADOS))
        for final in (T.CONCLUIDA, T.CANCELADA):
            self.assertEqual(T.TRANSICOES[final], set(), f"{final} é final")
        for de, para in T.TRANSICOES.items():
            self.assertTrue(para <= set(T.ESTADOS))
            self.assertNotIn(de, para, "não existe transição para o mesmo estado")

    def test_caminho_feliz_existe_na_ordem_da_missao(self):
        for de, para in zip((T.CRIADA, T.PLANEJANDO, T.PRONTA, T.EXECUTANDO, T.VERIFICANDO), (T.PLANEJANDO, T.PRONTA, T.EXECUTANDO, T.VERIFICANDO, T.CONCLUIDA)):
            self.assertIn(para, T.TRANSICOES[de])

    def test_ninguem_pula_direto_para_concluida(self):
        for de in (T.CRIADA, T.PLANEJANDO, T.PRONTA, T.EXECUTANDO, T.BLOQUEADA, T.FALHOU, T.PRECISA_INTERVENCAO, T.EXECUTADA_SEM_VERIFICACAO):
            self.assertNotIn(T.CONCLUIDA, T.TRANSICOES[de], f"{de} não conclui sem VERIFICANDO")

    def test_transicao_invalida_e_recusada_e_nao_muda_nada(self):
        tid = T.criar("objetivo")
        antes = T.obter(tid)
        with self.assertRaises(T.TransicaoInvalida):
            T._mudar_id(tid, T.CONCLUIDA, "tentativa")
        self.assertEqual(T.obter(tid), antes)

    def test_criada_tem_os_campos_da_missao(self):
        tid = T.criar("lembrar de beber água", restricoes=["só lembrete"], origem="usuario")
        t = T.obter(tid)
        self.assertRegex(tid, r"^t\d{4}$")
        for campo in ("id", "objetivo", "contexto", "passos", "estado", "tentativas", "depende_de", "proxima_acao", "historico", "criada", "atualizada"):
            self.assertIn(campo, t)
        self.assertEqual((t["estado"], t["contexto"]["restricoes"], t["contexto"]["origem"], t["tentativas"]), (T.CRIADA, ["só lembrete"], "usuario", 0))
        self.assertEqual(t["historico"][0]["para"], T.CRIADA)

    def test_ids_sao_unicos_e_nao_voltam_nunca(self):
        ids = {T.criar(f"tarefa {i}") for i in range(30)}
        self.assertEqual(len(ids), 30)
        T.reiniciar()
        self.assertNotIn(T.criar("outra"), ids, "o contador sobrevive ao reinício")

    def test_contador_nao_volta_mesmo_que_as_tarefas_tenham_saido_do_arquivo(self):
        T.criar("x")
        d = self.disco()
        d["tarefas"], d["proximo"] = {}, 50
        with open(self.base(".cerebro", "tarefas.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        T.reiniciar()
        self.assertEqual(T.criar("y"), "t0050")

    def test_origem_invalida_e_recusada(self):
        with self.assertRaises(ValueError):
            T.criar("x", origem="qualquer")


class Planejar(Base):
    def test_plano_valido_deixa_a_tarefa_pronta(self):
        tid = T.criar("lembrar", passos=[self.lembrete()])
        t = T.obter(tid)
        self.assertEqual(t["estado"], T.PRONTA)
        self.assertEqual(self.estados(t), [T.CRIADA, T.PLANEJANDO, T.PRONTA])
        self.assertEqual(t["passos"][0]["id"], "p1")
        self.assertEqual(t["passos"][0]["estado"], "pendente")

    def test_plano_com_ferramenta_desconhecida_e_recusado(self):
        tid = T.criar("x")
        with self.assertRaises(ValueError):
            T.planejar(tid, [{"descricao": "x", "ferramenta": "nao_existe_tar", "args": {}}])
        self.assertEqual(T.obter(tid)["estado"], T.CRIADA)

    def test_dependencia_so_aceita_passo_anterior(self):
        tid = T.criar("x")
        with self.assertRaises(ValueError):
            T.planejar(tid, [self.lembrete(depende_de=["p2"]), self.lembrete()])
        with self.assertRaises(ValueError):
            T.planejar(tid, [self.lembrete(depende_de=["p1"])])
        with self.assertRaises(ValueError):
            T.planejar(tid, [])
        with self.assertRaises(ValueError):
            T.planejar(tid, [self.lembrete()] * (T.MAX_PASSOS + 1))

    def test_nivel_4_nao_entra_no_plano(self):
        B.registrar("acao_n4_tar", "t", {}, [], lambda: "nunca", 4)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_n4_tar", None)
        with self.assertRaises(ValueError):
            T.planejar(T.criar("x"), [{"descricao": "x", "ferramenta": "acao_n4_tar", "args": {}}])


class A_ExecucaoBasicaVerificada(Base):
    def test_lembrete_criado_e_conferido_conclui(self):
        tid = T.criar("lembrar de beber água", passos=[self.lembrete()])
        r = T.executar(tid)
        t = T.obter(tid)
        self.assertEqual((r["estado"], t["estado"]), (T.CONCLUIDA, T.CONCLUIDA))
        p = t["passos"][0]
        self.assertEqual((p["estado"], p["tentativas"], p["verificacao"]["veredito"], p["verificacao"]["forca"]), ("verificado", 1, "confirmado", "independente"))
        self.assertEqual(self.estados(t), [T.CRIADA, T.PLANEJANDO, T.PRONTA, T.EXECUTANDO, T.VERIFICANDO, T.CONCLUIDA])
        self.assertEqual(len(self.lembretes()), 1, "o lembrete existe de verdade")
        self.assertEqual(t["tentativas"], 1)

    def test_a_acao_passou_pelo_corretor_e_ficou_na_auditoria(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        with open(B.AUDITORIA, encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(any(l.get("ferramenta") == "criar_lembrete" and l.get("decisao") == "automatico" for l in linhas))
        self.assertEqual(B.verificar_auditoria()[0], True)

    def test_dois_passos_com_dependencia_rodam_na_ordem(self):
        tid = T.criar("x", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}, self.lembrete(depende_de=["p1"])])
        r1 = T.executar_proximo(tid)
        self.assertEqual((r1["passo"], T.obter(tid)["estado"]), ("p1", T.PRONTA))
        r2 = T.executar_proximo(tid)
        self.assertEqual((r2["passo"], T.obter(tid)["estado"]), ("p2", T.CONCLUIDA))

    def test_o_corretor_continua_decidindo_args_invalidos_viram_falha(self):
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "criar_lembrete", "args": {"minutos": "muito", "texto": "a"}}])
        r = T.executar(tid)
        t = T.obter(tid)
        self.assertEqual(t["estado"], T.FALHOU)
        self.assertEqual(t["passos"][0]["estado"], "falhou")
        self.assertEqual(t["passos"][0]["codigo"], "tipo:minutos")
        self.assertEqual(self.lembretes("a"), [], "o corretor recusou: nada foi criado")

    def test_nao_executa_tarefa_que_nao_esta_pronta(self):
        tid = T.criar("x")
        r = T.executar_proximo(tid)
        self.assertIsNone(r["passo"])
        self.assertEqual(T.obter(tid)["estado"], T.CRIADA)

    def test_tarefa_terminada_nao_executa_de_novo(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        self.assertEqual(len(self.lembretes()), 1)
        T.executar(tid)
        self.assertEqual(len(self.lembretes()), 1, "concluída não repete a ação")

    def test_gancho_de_fim_recebe_copia_da_tarefa(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        self.assertEqual([(t["id"], t["estado"]) for t in self.fim], [(tid, T.CONCLUIDA)])
        self.fim[0]["objetivo"] = "adulterado"
        self.assertNotEqual(T.obter(tid)["objetivo"], "adulterado")

    def test_gancho_que_quebra_nao_atrapalha(self):
        def ruim(_t):
            raise RuntimeError("quebrei")
        T.GANCHOS_FIM.insert(0, ruim)
        self.addCleanup(T.GANCHOS_FIM.remove, ruim)
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        self.assertEqual(len(self.fim), 1)


class B_FalsoSucessoNaoConclui(Base):
    def test_ferramenta_diz_que_fez_e_nao_fez(self):
        tid = T.criar("lembrar", passos=[self.lembrete()])
        with mente("criar_lembrete", "Lembrete criado para daqui a 7 minutos."):
            T.executar(tid)
        t = T.obter(tid)
        self.assertEqual(t["estado"], T.FALHOU)
        self.assertNotEqual(t["estado"], T.CONCLUIDA)
        p = t["passos"][0]
        self.assertEqual((p["estado"], p["verificacao"]["veredito"]), ("refutado", "refutado"))
        self.assertIn("efeito", t["causa"])
        self.assertTrue(t["proxima_acao"])
        self.assertEqual(self.lembretes(), [], "e de fato não há lembrete")

    def test_passo_seguinte_nao_roda_depois_de_falso_sucesso(self):
        tid = T.criar("x", passos=[self.lembrete(), {"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}, "depende_de": ["p1"]}])
        with mente("criar_lembrete", "ok"):
            T.executar(tid)
        t = T.obter(tid)
        self.assertEqual([p["estado"] for p in t["passos"]], ["refutado", "pendente"])
        self.assertEqual(self.notas(), 0)

    def test_erro_da_ferramenta_e_falha_nao_conclusao(self):
        B.registrar("acao_erro_tar", "t", {}, [], lambda: "Erro: algo deu errado", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_erro_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_erro_tar", "args": {}}])
        T.executar(tid)
        self.assertEqual((T.obter(tid)["estado"], T.obter(tid)["passos"][0]["estado"]), (T.FALHOU, "falhou"))

    def test_ferramenta_sem_conferencia_nao_vira_concluida(self):
        B.registrar("acao_cega_tar", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_tar", "args": {}}])
        T.executar(tid)
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], t["passos"][0]["verificacao"]["veredito"]), (T.EXECUTADA_SEM_VERIFICACAO, "sem_verificacao", "nao_verificavel"))
        self.assertIn("só você pode dizer", t["proxima_acao"], "a próxima ação diz que quem decide se deu certo é o dono")
        self.assertIn("está feita", t["proxima_acao"])

    def test_so_o_dono_conclui_o_que_nao_da_para_conferir(self):
        B.registrar("acao_cega_tar", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_tar", "args": {}}])
        T.executar(tid)
        ok, _ = T.confirmar_manual(tid)
        t = T.obter(tid)
        self.assertTrue(ok)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], t["passos"][0]["verificacao"]["forca"]), (T.CONCLUIDA, "verificado", "dono"))

    def test_confirmacao_manual_so_vale_onde_falta_conferencia(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)                                                # concluída de verdade
        self.assertFalse(T.confirmar_manual(tid)[0])
        tid2 = T.criar("y")                                            # ainda nem tem plano
        self.assertFalse(T.confirmar_manual(tid2)[0])

    def test_passo_dependente_de_um_nao_conferido_pede_o_dono(self):
        B.registrar("acao_cega_tar", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_tar", "args": {}}, self.lembrete(depende_de=["p1"])])
        T.executar(tid)
        t = T.obter(tid)
        self.assertEqual(t["estado"], T.PRECISA_INTERVENCAO)
        self.assertEqual([p["estado"] for p in t["passos"]], ["sem_verificacao", "pendente"])
        self.assertEqual(self.lembretes(), [])
        self.assertTrue(T.confirmar_manual(tid)[0])                     # o dono diz que o passo 1 deu certo: o plano segue
        self.assertEqual(T.obter(tid)["estado"], T.PRONTA)
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        self.assertEqual(len(self.lembretes()), 1)

    def test_caminho_da_conversa_avisa_a_ia_quando_o_efeito_nao_existe(self):
        with mente("criar_lembrete", "Lembrete criado para daqui a 7 minutos."):
            texto = T.executar_registrado("criar_lembrete", {"minutos": 7, "texto": SEGREDO})
        self.assertIn("Lembrete criado", texto)
        self.assertIn("NÃO encontrei", texto, "a IA é avisada de que o efeito não existe")
        t = [x for x in T.listar() if x["contexto"]["origem"] == "ia"][-1]
        self.assertEqual(t["estado"], T.FALHOU)

    def test_caminho_da_conversa_nao_muda_o_texto_quando_deu_certo(self):
        texto = T.executar_registrado("criar_lembrete", {"minutos": 7, "texto": SEGREDO})
        self.assertEqual(texto, "Lembrete criado para daqui a 7 minutos.")
        t = [x for x in T.listar() if x["contexto"]["origem"] == "ia"][-1]
        self.assertEqual(t["estado"], T.CONCLUIDA)

    def test_leitura_pura_nao_vira_tarefa(self):
        antes = len(T.listar())
        self.assertEqual(T.executar_registrado("listar_lembretes", {}), B.executar("listar_lembretes", {}))
        self.assertEqual(len(T.listar()), antes)

    def test_caminho_da_conversa_devolve_o_mesmo_texto_do_corretor(self):
        for nome, args in (("anotar", {"texto": SEGREDO}), ("anotar", {}), ("nao_existe_tar", {}), ("criar_lembrete", {"minutos": "x", "texto": "a"})):
            with self.subTest(nome=nome, args=args):
                self.assertEqual(T.executar_registrado(nome, args), B.executar(nome, args))

    def test_falha_ao_registrar_nao_impede_a_ferramenta(self):
        with mock.patch.object(T, "criar", side_effect=OSError("disco")):
            self.assertEqual(T.executar_registrado("anotar", {"texto": SEGREDO}), "Anotado.")
        self.assertEqual(self.notas(), 1, "executou uma vez só")


class F_AcaoSensivelNaoRodaComConfirmacaoAmbigua(Base):
    PLANO = [{"descricao": "avisar a mãe", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO}}]

    def pendente(self):
        tid = T.criar("avisar a mãe", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        T.executar(tid)
        return tid

    def test_acao_de_nivel_2_fica_bloqueada_esperando_o_dono(self):
        tid = self.pendente()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.BLOQUEADA, "aguardando"))
        self.assertEqual(t["passos"][0]["pendencia"], B.pendente_publico()["id"])
        self.assertEqual(self.sms(), 0)

    def test_respostas_vagas_nao_executam_nem_mudam_a_tarefa(self):
        tid = self.pendente()
        antes = T.obter(tid)
        for fala in ("sim", "pode", "pode fazer", "isso", "isso mesmo", "claro", "ok"):
            B.confirmar_voz(fala)
        self.assertEqual(self.sms(), 0)
        self.assertEqual(T.obter(tid), antes)

    def test_confirmacao_do_painel_com_id_errado_nao_executa(self):
        tid = self.pendente()
        B.confirmar_botao("zzzzzz")
        self.assertEqual((self.sms(), T.obter(tid)["estado"]), (0, T.BLOQUEADA))

    def test_confirmacao_clara_executa_e_registra_sem_dizer_que_foi_entregue(self):
        tid = self.pendente()
        ok, _ = B.confirmar_voz("confirmo")
        t = T.obter(tid)
        self.assertTrue(ok)
        self.assertEqual(self.sms(), 1)
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.EXECUTADA_SEM_VERIFICACAO, "sem_verificacao"))
        self.assertEqual(self.estados(t)[-3:], [T.EXECUTANDO, T.VERIFICANDO, T.EXECUTADA_SEM_VERIFICACAO])

    def test_confirmacao_pelo_botao_com_o_id_certo(self):
        tid = self.pendente()
        B.confirmar_botao(B.pendente_publico()["id"])
        self.assertEqual((self.sms(), T.obter(tid)["estado"]), (1, T.EXECUTADA_SEM_VERIFICACAO))

    def test_cancelar_cancela_a_tarefa_e_nao_executa(self):
        tid = self.pendente()
        B.confirmar_voz("cancela")
        self.assertEqual((self.sms(), T.obter(tid)["estado"], T.obter(tid)["passos"][0]["estado"]), (0, T.CANCELADA, "cancelado"))

    def test_cancelar_pelo_painel(self):
        tid = self.pendente()
        B.cancelar()
        self.assertEqual((self.sms(), T.obter(tid)["estado"]), (0, T.CANCELADA))

    def test_expirar_pede_o_dono_e_nao_executa(self):
        tid = self.pendente()
        B.PEND["expira"] = time.time() - 1
        B.pendente_publico()
        t = T.obter(tid)
        self.assertEqual((self.sms(), t["estado"], t["passos"][0]["estado"]), (0, T.PRECISA_INTERVENCAO, "intervencao"))
        self.assertIn("expir", t["causa"])

    def test_ser_substituida_pede_o_dono_e_a_antiga_nunca_roda(self):
        tid = self.pendente()
        B.executar("ligar", {"contato": "mae"})                         # outra ação sensível por cima
        self.assertEqual(T.obter(tid)["estado"], T.PRECISA_INTERVENCAO)
        B.confirmar_voz("confirmo")
        self.assertEqual(self.sms(), 0, "a confirmação vale para a ação nova, nunca para a antiga")

    def test_pelo_caminho_da_conversa_tambem_nao_executa_com_sim(self):
        texto = T.executar_registrado("enviar_sms", {"contato": "mae", "texto": SEGREDO})
        self.assertTrue(texto.startswith("AÇÃO PENDENTE"))
        t = [x for x in T.listar() if x["contexto"]["origem"] == "ia"][-1]
        self.assertEqual(t["estado"], T.BLOQUEADA)
        B.confirmar_voz("sim")
        B.confirmar_voz("pode")
        self.assertEqual(self.sms(), 0)
        B.confirmar_voz("confirmo")
        self.assertEqual((self.sms(), T.obter(t["id"])["estado"]), (1, T.EXECUTADA_SEM_VERIFICACAO))

    def test_dado_de_terceiros_sobe_o_nivel_tambem_para_a_tarefa(self):
        turno = B.Turno()
        turno.contaminado = True
        tid = T.criar("x", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}])
        T.executar(tid, turno)
        self.assertEqual(T.obter(tid)["estado"], T.BLOQUEADA, "nível 1 + turno contaminado = nível 2: pede confirmação")
        self.assertEqual(self.notas(), 0)

    def test_cancelar_a_tarefa_cancela_so_a_confirmacao_dela(self):
        tid = self.pendente()
        self.assertTrue(T.cancelar(tid, "desisti"))
        self.assertIsNone(B.pendente_publico())
        self.assertEqual(T.obter(tid)["estado"], T.CANCELADA)
        B.executar("ligar", {"contato": "mae"})                         # outra pendência de outra origem
        outra = T.criar("y")
        T.cancelar(outra)
        self.assertIsNotNone(B.pendente_publico(), "cancelar uma tarefa sem pendência não mexe na confirmação alheia")

    def test_confirmacao_que_nao_e_de_tarefa_nao_mexe_em_nenhuma(self):
        tid = T.criar("x", passos=[self.lembrete()])
        B.executar("enviar_sms", {"contato": "mae", "texto": "oi"})
        B.confirmar_voz("confirmo")
        self.assertEqual(T.obter(tid)["estado"], T.PRONTA)


class G_Privacidade(Base):
    def todo_o_disco(self):
        base = self.base()
        achados = []
        for raiz, _, nomes in os.walk(base):
            for n in nomes:
                if n.endswith((".json", ".jsonl")):
                    with open(os.path.join(raiz, n), encoding="utf-8") as f:
                        achados.append((n, f.read()))
        return achados

    def test_auditoria_nunca_tem_o_conteudo_mesmo_com_tarefas(self):
        tid = T.criar("x", passos=[self.lembrete(), {"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}])
        T.executar(tid)
        T.executar_registrado("anotar", {"texto": SEGREDO})
        with open(B.AUDITORIA, encoding="utf-8") as f:
            self.assertNotIn(SEGREDO, f.read())

    def test_objetivo_e_historico_saem_redigidos(self):
        tid = T.criar("ligar para (11) 98888-0002 e dizer a senha é abc12345 do wifi")
        t = T.obter(tid)
        self.assertNotIn("98888", t["objetivo"])
        self.assertNotIn("abc12345", t["objetivo"])
        self.assertTrue(all("98888" not in json.dumps(h) for h in t["historico"]))
        for nome, txt in self.todo_o_disco():
            self.assertNotIn("98888", txt, nome)
            self.assertNotIn("abc12345", txt, nome)

    def test_tarefa_da_conversa_nao_guarda_os_argumentos(self):
        T.executar_registrado("anotar", {"texto": SEGREDO})
        for nome, txt in self.todo_o_disco():
            self.assertNotIn(SEGREDO, txt, nome)
        t = [x for x in T.listar() if x["contexto"]["origem"] == "ia"][-1]
        self.assertIsNone(t["passos"][0]["args"])
        self.assertIn("‹texto:", t["passos"][0]["args_resumo"])

    def test_acao_sensivel_guarda_so_o_resumo(self):
        tid = T.criar("x", passos=[{"descricao": "avisar", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO}}])
        T.executar(tid)
        t = T.obter(tid)
        self.assertIsNone(t["passos"][0]["args"], "nível 2: nada de conteúdo no registro")
        for nome, txt in self.todo_o_disco():
            self.assertNotIn(SEGREDO, txt, nome)

    def test_argumento_sensivel_nao_e_guardado_nem_depois_de_executar(self):
        tid = T.criar("x", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": "minha senha é hunter2xyz"}}])
        T.executar(tid)
        self.assertIsNone(T.obter(tid)["passos"][0]["args"])
        for nome, txt in self.todo_o_disco():
            self.assertNotIn("hunter2xyz", txt, nome)

    def _espiar_disco(self, ferramenta):
        """Troca a função da ferramenta por uma que, no meio da execução (tarefa EXECUTANDO, registro já gravado antes da chamada), copia todo o disco."""
        vistos = []
        original = B.FERRAMENTAS[ferramenta]["fn"]

        def espia(**kw):
            vistos.extend(self.todo_o_disco())
            return original(**kw)
        p = mock.patch.dict(B.FERRAMENTAS[ferramenta], {"fn": espia})
        p.start()
        self.addCleanup(p.stop)
        return vistos

    def test_tarefa_da_conversa_nao_grava_os_argumentos_nem_enquanto_roda(self):
        vistos = self._espiar_disco("anotar")
        T.executar_registrado("anotar", {"texto": SEGREDO})
        self.assertTrue(vistos, "a ferramenta rodou e o disco foi lido no meio")
        for nome, txt in vistos:
            self.assertNotIn(SEGREDO, txt, f"{nome} (durante a execução)")

    def test_argumento_sensivel_nao_vai_para_o_disco_nem_antes_de_executar(self):
        tid = T.criar("x", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": "minha senha é hunter2xyz"}}])
        self.assertIsNone(T.obter(tid)["passos"][0]["args"])
        for nome, txt in self.todo_o_disco():
            self.assertNotIn("hunter2xyz", txt, nome)
        vistos = self._espiar_disco("anotar")
        T.executar(tid)
        self.assertTrue(vistos)
        for nome, txt in vistos:
            self.assertNotIn("hunter2xyz", txt, f"{nome} (durante a execução)")

    def test_acao_de_nivel_2_nao_vai_para_o_disco_nem_enquanto_espera_o_dono(self):
        tid = T.criar("x", passos=[{"descricao": "avisar", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO}}])
        for nome, txt in self.todo_o_disco():
            self.assertNotIn(SEGREDO, txt, f"{nome} (pronta)")
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.BLOQUEADA)
        for nome, txt in self.todo_o_disco():
            self.assertNotIn(SEGREDO, txt, f"{nome} (esperando o dono)")

    def test_passo_de_baixo_risco_guarda_os_args_para_poder_retomar(self):
        tid = T.criar("x", passos=[self.lembrete()])
        self.assertEqual(T.obter(tid)["passos"][0]["args"], {"minutos": 7, "texto": SEGREDO})

    def test_terminou_o_conteudo_sai_do_registro(self):
        tid = T.criar("x", passos=[self.lembrete()])
        self.assertIn(SEGREDO, json.dumps(self.disco()), "enquanto pode ser preciso retomar, os argumentos de baixo risco ficam")
        T.executar(tid)
        self.assertNotIn(SEGREDO, json.dumps(self.disco()), "concluída: só o resumo e a conferência ficam")
        self.assertIsNone(T.obter(tid)["passos"][0]["args"])
        outra = T.criar("y", passos=[self.lembrete(texto=SEGREDO + "2")])
        T.cancelar(outra)
        self.assertNotIn(SEGREDO + "2", json.dumps(self.disco()))
        for nome, txt in self.todo_o_disco():
            self.assertNotIn(SEGREDO, txt, nome)

    def test_evidencia_e_resultado_nao_carregam_o_conteudo(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        p = T.obter(tid)["passos"][0]
        self.assertNotIn(SEGREDO, json.dumps(p["verificacao"]))
        self.assertNotIn("resultado", p, "o texto da resposta não é guardado, só o código e o tamanho")
        self.assertIsInstance(p["tam"], int)

    def test_historico_em_arquivo_so_acrescenta(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        caminho = self.base(".cerebro", "tarefas_historico.jsonl")
        with open(caminho, encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
        self.assertGreaterEqual(len(linhas), 6)
        self.assertEqual([l["para"] for l in linhas if l.get("tarefa") == tid and "para" in l][-1], T.CONCLUIDA)


class Persistencia(Base):
    def test_estado_vai_para_o_disco_e_volta(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        no_disco = self.disco()["tarefas"][tid]
        T.reiniciar()
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)
        self.assertEqual(no_disco["estado"], T.CONCLUIDA)

    def test_grava_antes_de_executar(self):
        """Se o processo cair DEPOIS de chamar o corretor e ANTES de registrar o resultado, o disco já diz que o passo estava executando, com a marca."""
        tid = T.criar("x", passos=[self.lembrete()])

        class Caiu(BaseException):
            pass

        visto = {}

        def cai(*a, **k):
            visto["disco"] = self.disco()["tarefas"][tid]
            raise Caiu()
        with mock.patch.object(B, "executar_estruturado", side_effect=cai):
            with self.assertRaises(Caiu):
                T.executar_proximo(tid)
        p = visto["disco"]["passos"][0]
        self.assertEqual((visto["disco"]["estado"], p["estado"], p["tentativas"]), (T.EXECUTANDO, "executando", 1))
        self.assertIn("t0", p["marca"])
        T.reiniciar()
        self.assertEqual(T.obter(tid)["estado"], T.EXECUTANDO, "depois do «reinício» ainda consta executando")

    def test_arquivo_adulterado_vira_estado_limpo(self):
        tid = T.criar("x", passos=[self.lembrete()])
        d = self.disco()
        d["tarefas"][tid]["estado"] = "TUDO_PERMITIDO"
        d["tarefas"]["../../etc"] = {"objetivo": "x"}
        d["tarefas"][tid]["passos"][0]["ferramenta"] = "rm -rf"
        d["tarefas"][tid]["objetivo"] = "x" * 10000
        with open(self.base(".cerebro", "tarefas.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        T.reiniciar()
        self.assertNotIn("../../etc", {t["id"] for t in T.listar()})
        t = T.obter(tid)
        self.assertIsNotNone(t, "a tarefa legítima sobrevive: só os campos adulterados são corrigidos")
        self.assertEqual(t["estado"], T.PRECISA_INTERVENCAO, "estado inventado vira «precisa de você», nunca «tudo permitido»")
        self.assertLessEqual(len(t["objetivo"]), 300)
        self.assertEqual(t["passos"], [], "o passo com ferramenta inválida foi descartado")

    def test_arquivo_corrompido_nao_derruba(self):
        T.criar("x")
        with open(self.base(".cerebro", "tarefas.json"), "w", encoding="utf-8") as f:
            f.write("{isto não é json")
        T.reiniciar()
        self.assertEqual(T.listar(), [])
        self.assertTrue(T.criar("de novo"))

    def test_concluidas_antigas_saem_do_estado_vivo_mas_ficam_no_historico(self):
        with mock.patch.object(T, "MAX_FINAIS", 3):
            ids = []
            for i in range(6):
                tid = T.criar(f"tarefa {i}", passos=[self.lembrete(texto=f"{SEGREDO}{i}")])
                T.executar(tid)
                ids.append(tid)
        vivos = {t["id"] for t in T.listar()}
        self.assertLessEqual(len(vivos), 3)
        self.assertIn(ids[-1], vivos)
        with open(self.base(".cerebro", "tarefas_historico.jsonl"), encoding="utf-8") as f:
            historico = f.read()
        for tid in ids:
            self.assertIn(f'"{tid}"', historico, "nada se perde")
        instantaneos = [json.loads(l)["snapshot"] for l in historico.splitlines() if '"snapshot"' in l]
        self.assertEqual(sorted(x["id"] for x in instantaneos), sorted(ids), "cada tarefa terminada deixa uma foto completa no histórico")
        self.assertTrue(all(x["estado"] == T.CONCLUIDA and all(p["args"] is None for p in x["passos"]) for x in instantaneos), "a foto não carrega argumentos")

    def test_sem_cofre_vive_so_no_processo(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            T.reiniciar()
            tid = T.criar("x", passos=[self.lembrete()])
            T.executar(tid)
            self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)


class CasosDeBorda(Base):
    def test_cancelar_nao_cancela_a_confirmacao_de_outra_origem_depois_de_um_reinicio(self):
        tid = F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.pendente(self)
        B.PEND = None                                                   # o programa reiniciou: a confirmação em memória se foi, o disco ainda diz «aguardando»
        T.reiniciar()
        B.executar("ligar", {"contato": "mae"})                         # e agora há uma confirmação de OUTRA ação
        outra = B.pendente_publico()["id"]
        self.assertTrue(T.cancelar(tid))
        self.assertEqual((B.pendente_publico() or {}).get("id"), outra, "cancelar a tarefa não pode derrubar a confirmação alheia")

    def test_erro_inesperado_no_corretor_nao_repete_a_acao(self):
        chamadas = []
        with mock.patch.object(B, "executar_estruturado", side_effect=lambda *a, **k: (chamadas.append(1), (_ for _ in ()).throw(RuntimeError("bug")))[1]), \
                mock.patch.object(B, "executar", side_effect=lambda *a, **k: chamadas.append("antigo") or "x"):
            texto = T.executar_registrado("anotar", {"texto": SEGREDO})
        self.assertEqual(chamadas, [1], "o corretor foi chamado uma vez e nada tentou de novo")
        self.assertIn("Erro", texto)
        t = [x for x in T.listar() if x["contexto"]["origem"] == "ia"][-1]
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.PRECISA_INTERVENCAO, "intervencao"))
        self.assertIn("não sei se", t["causa"])

    def test_passo_sensivel_nao_sobrevive_ao_reinicio_com_os_argumentos(self):
        tid = T.criar("avisar", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        T.reiniciar()                                                   # os argumentos só existiam na memória do processo
        T.executar(tid)
        t = T.obter(tid)
        self.assertEqual((self.sms(), t["estado"], t["passos"][0]["estado"]), (0, T.PRECISA_INTERVENCAO, "intervencao"))
        self.assertIn("argumentos", t["causa"])

    def test_cancelada_no_meio_da_execucao_registra_o_que_aconteceu(self):
        tid = T.criar("x", passos=[self.lembrete()])
        real = B.executar_estruturado

        def cancela_no_meio(*a, **k):
            T.cancelar(tid)
            return real(*a, **k)
        with mock.patch.object(B, "executar_estruturado", side_effect=cancela_no_meio):
            T.executar_proximo(tid)
        t = T.obter(tid)
        self.assertEqual(t["estado"], T.CANCELADA, "o dono cancelou: continua cancelada")
        self.assertEqual((t["passos"][0]["estado"], len(self.lembretes())), ("verificado", 1), "mas a ação rodou e o registro não esconde isso")
        with open(self.base(".cerebro", "tarefas_historico.jsonl"), encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(any("já estava em andamento" in l.get("aviso", "") for l in linhas), "o histórico diz que a ação rodou apesar do cancelamento")
        self.assertFalse(any("erro_ao_registrar" in l for l in linhas), "e isso não foi um erro de registro")

    def test_cancelada_no_meio_com_confirmacao_nascendo_nao_deixa_confirmacao_solta(self):
        tid = T.criar("x", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        real = B.executar_estruturado

        def cancela_no_meio(*a, **k):
            T.cancelar(tid)
            return real(*a, **k)
        with mock.patch.object(B, "executar_estruturado", side_effect=cancela_no_meio):
            T.executar_proximo(tid)
        self.assertIsNone(B.pendente_publico(), "a confirmação que nasceu depois do cancelamento foi derrubada")
        B.confirmar_voz("confirmo")
        self.assertEqual((self.sms(), T.obter(tid)["estado"]), (0, T.CANCELADA))

    def test_refutado_e_depois_o_efeito_aparece_nao_repete_ao_retomar(self):
        tid = T.criar("x", passos=[self.lembrete()])
        with mente("criar_lembrete", "Lembrete criado."):
            T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.FALHOU)
        F.criar_lembrete(7, SEGREDO)                                    # o lembrete só apareceu depois
        ok, msg = T.reabrir(tid)
        self.assertTrue(ok)
        self.assertIn("não repeti", msg)
        self.assertEqual((T.obter(tid)["estado"], len(self.lembretes())), (T.CONCLUIDA, 1))

    def test_refutado_e_o_efeito_continua_ausente_retoma_e_cria(self):
        tid = T.criar("x", passos=[self.lembrete()])
        with mente("criar_lembrete", "Lembrete criado."):
            T.executar(tid)
        ok, _ = T.reabrir(tid)
        self.assertTrue(ok)
        T.executar(tid)
        self.assertEqual((T.obter(tid)["estado"], len(self.lembretes()), T.obter(tid)["passos"][0]["tentativas"]), (T.CONCLUIDA, 1, 2))

    def test_confirmacao_manual_numa_tarefa_pronta_recusa_sem_quebrar(self):
        B.registrar("acao_cega_tar", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_tar", "args": {}}, self.lembrete()])   # o 2º passo não depende do 1º
        T.executar_proximo(tid)
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.PRONTA, "sem_verificacao"))
        ok, msg = T.confirmar_manual(tid)
        self.assertFalse(ok)
        self.assertEqual(T.obter(tid)["estado"], T.PRONTA)

    def test_so_retoma_o_que_esta_parado(self):
        tid = T.criar("x", passos=[self.lembrete()])
        self.assertFalse(T.reabrir(tid)[0], "pronta não é retomada: é executada")
        T.executar(tid)
        self.assertFalse(T.reabrir(tid)[0], "concluída não volta")
        self.assertFalse(T.reabrir("t9999")[0])

    def test_tarefa_que_depende_de_outra_espera_e_depois_roda(self):
        a = T.criar("primeiro", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": SEGREDO}}])
        b = T.criar("depois", passos=[self.lembrete()], depende_de=[a])
        T.executar(b)
        self.assertEqual((T.obter(b)["estado"], len(self.lembretes())), (T.BLOQUEADA, 0))
        T.executar(a)
        T.executar(b)
        self.assertEqual((T.obter(b)["estado"], len(self.lembretes())), (T.CONCLUIDA, 1))

    def test_modo_manutencao_bloqueia_e_depois_libera(self):
        marca = os.path.join(B.BASE, "MANUTENCAO")
        with open(marca, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(marca) and os.remove(marca))
        tid = T.criar("x", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        T.executar(tid)
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], t["passos"][0]["tentativas"]), (T.BLOQUEADA, "pendente", 0))
        os.remove(marca)
        T.executar(tid)
        self.assertEqual(T.obter(tid)["estado"], T.BLOQUEADA, "agora pede a confirmação")
        self.assertIsNotNone(B.pendente_publico())
        self.assertEqual(self.sms(), 0)


class Concorrencia(Base):
    def test_duas_threads_no_mesmo_passo_executam_uma_vez(self):
        chamadas = []
        liberar = threading.Event()

        def devagar(texto):
            chamadas.append(texto)
            liberar.wait(5)
            return "Anotado."
        B.registrar("acao_lenta_tar", "t", {"texto": {"type": "string"}}, ["texto"], devagar, 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_lenta_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_lenta_tar", "args": {"texto": "a"}}])
        res = []
        ts = [threading.Thread(target=lambda: res.append(T.executar_proximo(tid))) for _ in range(2)]
        for t in ts:
            t.start()
        time.sleep(0.3)
        liberar.set()
        for t in ts:
            t.join(10)
        self.assertEqual(chamadas, ["a"], "a ação rodou uma única vez")
        self.assertEqual(sorted(r["passo"] is None for r in res), [False, True])
        self.assertEqual([r["motivo"] for r in res if r["passo"] is None], ["já está em execução"], "quem chegou depois foi avisado de que já está em execução")

    def test_consultar_e_cancelar_nao_trava_enquanto_o_corretor_trabalha(self):
        liberar = threading.Event()
        B.registrar("acao_lenta_tar", "t", {}, [], lambda: (liberar.wait(5), "Feito.")[1], 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_lenta_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_lenta_tar", "args": {}}])
        th = threading.Thread(target=lambda: T.executar_proximo(tid))
        th.start()
        time.sleep(0.2)
        feitos = []
        leitor = threading.Thread(target=lambda: feitos.append((T.listar(), T.obter(tid), T.falar_tarefas())))
        leitor.start()
        leitor.join(2)
        self.assertFalse(leitor.is_alive(), "a trava das tarefas não fica presa durante a chamada ao corretor")
        self.assertEqual(feitos[0][1]["estado"], T.EXECUTANDO)
        liberar.set()
        th.join(10)

    def test_confirmacao_em_outra_thread_enquanto_se_consulta(self):
        tid = T.criar("x", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        T.executar(tid)
        erros = []

        def consulta():
            try:
                for _ in range(200):
                    T.listar(); T.obter(tid)
            except Exception as e:  # pragma: no cover
                erros.append(e)
        th = threading.Thread(target=consulta)
        th.start()
        B.confirmar_voz("confirmo")
        th.join(10)
        self.assertEqual((erros, T.obter(tid)["estado"]), ([], T.EXECUTADA_SEM_VERIFICACAO))


class Observador(Base):
    def test_o_observador_esta_registrado_uma_vez_so(self):
        marcados = lambda: [f for f in B.OBSERVADORES if getattr(f, "_friday_tarefas", False)]
        self.assertEqual(len(marcados()), 1)
        T._registrar_observador()
        T._registrar_observador()
        self.assertEqual(len(marcados()), 1)

    def test_evento_desconhecido_ou_malformado_e_ignorado(self):
        T._ouvir({"tipo": "executada", "pendencia": "naoexiste"})
        T._ouvir({"tipo": "qualquer"})
        T._ouvir({})
        T._ouvir(None)
        T._ouvir({"tipo": "cancelada", "pendencia": 123})

    def test_execucao_automatica_nao_e_tratada_duas_vezes(self):
        tid = T.criar("x", passos=[self.lembrete()])
        T.executar(tid)
        self.assertEqual(T.obter(tid)["passos"][0]["tentativas"], 1)
        self.assertEqual(self.estados(T.obter(tid)).count(T.VERIFICANDO), 1)


class SemFerramentaParaIA(Base):
    def test_nenhuma_ferramenta_da_ia_cria_ou_mexe_em_tarefas(self):
        for nome in B.FERRAMENTAS:
            self.assertNotIn("tarefa", nome.lower(), nome)
        for d in B.definicoes():
            self.assertNotIn("tarefa", d["name"].lower())
            self.assertNotIn("tarefas.json", d.get("description", "").lower())


class PorVoz(Base):
    def test_listar(self):
        self.assertIn("nenhuma", T.tratar("minhas tarefas").lower())
        tid = T.criar("lembrar de beber água", passos=[self.lembrete()])
        r = T.tratar("quais são as minhas tarefas")
        self.assertIn("beber água", r)
        self.assertIn(tid[1:].lstrip("0"), r)

    def test_cancelar_por_voz(self):
        tid = T.criar("x", passos=[self.lembrete()])
        n = int(tid[1:])
        self.assertIn("cancel", T.tratar(f"cancela a tarefa {n}").lower())
        self.assertEqual(T.obter(tid)["estado"], T.CANCELADA)
        self.assertIn("não", T.tratar("cancela a tarefa 999").lower())

    def test_dono_conclui_o_que_nao_da_para_conferir(self):
        B.registrar("acao_cega_tar", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_cega_tar", None)
        tid = T.criar("x", passos=[{"descricao": "x", "ferramenta": "acao_cega_tar", "args": {}}])
        T.executar(tid)
        T.tratar(f"a tarefa {int(tid[1:])} está feita")
        self.assertEqual(T.obter(tid)["estado"], T.CONCLUIDA)

    def test_conversa_comum_nao_e_comando(self):
        for frase in ("que horas são", "tenho muitas tarefas hoje", "me lembra de uma tarefa"):
            self.assertIsNone(T.tratar(frase), frase)

    def test_retomar_nao_pula_a_confirmacao(self):
        tid = T.criar("x", passos=F_AcaoSensivelNaoRodaComConfirmacaoAmbigua.PLANO)
        T.executar(tid)
        B.confirmar_voz("cancela")
        T.reabrir(tid)
        T.tratar(f"retomar a tarefa {int(tid[1:])}")
        self.assertEqual(self.sms(), 0, "retomar pede a confirmação de novo, não executa sozinho")


class PorMeta(Base):
    def test_resumo_por_meta(self):
        a = T.criar("x", passos=[self.lembrete()], meta="m01")
        T.criar("y", passos=[self.lembrete()], meta="m01")
        T.executar(a)
        self.assertEqual(T.resumo_por_meta(), {"m01": {"total": 2, "concluidas": 1, "conclui": False}})

    def test_meta_invalida_e_recusada(self):
        with self.assertRaises(ValueError):
            T.criar("x", meta="../x")


if __name__ == "__main__":
    unittest.main()
