import ast, os, re, json, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, curiosidade as CUR, anatomia as AN, prefrontal as P, main as MAIN
from test_neuronios import Cerebro

AGORA = 1_800_000_000.0
FONTES = Path(__file__).resolve().parent.parent / "friday"


def quadro(**kw):
    """Um quadro geral inventado (o que `observar` devolveria). Por padrão: tudo ligado e câmera presente."""
    q = {"agora": AGORA, "vida": True, "dopamina": 0.55, "serotonina": 0.5, "acetilcolina": 0.5, "energia": 0.9, "vontade_estudar": 0.7, "vontade_conversar": 0.1,
         "horas": 3.0, "memoria": True, "curiosidade_ativa": True, "conversa_ativa": True, "visao_ativa": True, "tem_camera": True, "em_descanso": False, "em_silencio": False,
         "estudos_hoje": 0, "conversas_hoje": 0, "olhadas_hoje": 0, "coisas": 3, "ultima_olhada_s": 3 * 3600, "temas_estudados": {}, "estudo_no_teto": False,
         "autonomia": "assistente", "memorias": 5, "humor": "bem", "ult_tema": ""}
    q.update(kw)
    return q


class Base(Cerebro):
    def setUp(self):
        super().setUp()
        P.ARQ.reiniciar()
        CUR.ARQ.reiniciar()
        P._foco.clear(); P._hab.clear()
        P._agora_.update(dec=None, q=None, mesmo=0, assinatura=None, resfria={}, janela={})
        p = mock.patch.dict(os.environ, {"PFC_FOCO": "0"})
        p.start(); self.addCleanup(p.stop)


class Foco(Base):
    def test_perceber_guarda_so_o_rotulo_e_decai_com_o_tempo(self):
        P.perceber("fala", "pedido", "resumo curto", agora=AGORA, dopamina=0.55)
        f0 = P.foco(AGORA)
        self.assertEqual([x["origem"] for x in f0], ["fala"])
        self.assertLess(P.foco(AGORA + 600)[0]["forca"], f0[0]["forca"])           # esfria
        self.assertEqual(P.foco(AGORA + 3 * 3600), [])                              # e sai do foco

    def test_o_que_se_repete_perde_forca_habituacao(self):
        a = P.perceber("maos", "construir", agora=AGORA, dopamina=0.55)["forca"]
        b = P.perceber("maos", "construir", agora=AGORA + 1, dopamina=0.55)["forca"]
        c = P.perceber("maos", "construir", agora=AGORA + 2, dopamina=0.55)["forca"]
        self.assertGreater(a, b); self.assertGreater(b, c)
        d = P.perceber("maos", "apagar", agora=AGORA + 3, dopamina=0.55)["forca"]   # outra coisa: força cheia
        self.assertAlmostEqual(d, a, places=3)

    def test_dopamina_em_u_invertido_como_diz_o_artigo(self):
        meio, baixa, alta = P.qualidade_do_foco(0.55), P.qualidade_do_foco(0.0), P.qualidade_do_foco(1.0)
        self.assertEqual(meio, 1.0)
        self.assertLess(baixa, meio); self.assertLess(alta, meio)
        self.assertGreaterEqual(baixa, 0.2)
        P.perceber("fala", "a", agora=AGORA, dopamina=0.55); P.perceber("fala", "b", agora=AGORA, dopamina=0.0)
        it = {i["tipo"]: i for i in P._foco}
        self.assertGreater(it["a"]["meia"], it["b"]["meia"])                        # dopamina boa segura a atenção por mais tempo

    def test_foco_nao_tem_limite_mas_o_dono_pode_pedir_um(self):
        for i in range(300):
            P.perceber("sistema", f"t{i}", agora=AGORA, dopamina=0.55)
        self.assertEqual(len(P.foco(AGORA)), 300)
        with mock.patch.dict(os.environ, {"PFC_FOCO": "3"}):
            self.assertEqual(len(P.foco(AGORA)), 3)

    def test_significados_parecidos_se_reforcam(self):
        P.perceber("estudo", "novo", tema="memória humana no sono", agora=AGORA, dopamina=0.55)
        P.perceber("meta", "nova", tema="consolidação da memória no sono", agora=AGORA, dopamina=0.55)
        longe = P.perceber("estudo", "outro", tema="origem das estrelas", agora=AGORA, dopamina=0.55)
        por_tipo = {i["tipo"]: i for i in P._foco}
        self.assertGreater(por_tipo["novo"]["forca"], 0.7)                          # base 0,7 + reforço do parecido
        self.assertGreater(por_tipo["nova"]["forca"], 0.7)
        self.assertEqual(longe["forca"], 0.7)                                       # sem nada parecido: força cheia, sem reforço
        self.assertGreater(P.semelhanca("memória do sono", "sono e memória"), 0.5)
        self.assertEqual(P.semelhanca("estrelas", "cozinha"), 0.0)


class Decisao(Base):
    def test_varios_impulsos_ao_mesmo_tempo_sem_fila_nem_veto(self):
        dec = P.decidir(quadro(vontade_estudar=0.9, vontade_conversar=0.9, coisas=0, acetilcolina=0.9))
        self.assertGreaterEqual(len(dec["agir"]), 3)
        self.assertTrue(dec["simultaneo"])
        self.assertEqual(set(dec["agir"]) - {"descansar"}, {"estudar", "conversar", "olhar"})

    def test_o_dono_desligou_vira_nao_posso_e_diz_o_motivo(self):
        dec = P.decidir(quadro(curiosidade_ativa=False, conversa_ativa=False, tem_camera=False, em_silencio=True))
        for n in ("estudar", "conversar", "olhar"):
            self.assertEqual(dec["impulsos"][n]["decisao"], "não posso")
            self.assertTrue(dec["impulsos"][n]["motivo"])
        self.assertNotIn("estudar", dec["agir"])

    def test_serotonina_alta_inibe_mais_e_baixa_inibe_menos(self):
        self.assertGreater(P.limiar(0.9), P.limiar(0.5)); self.assertGreater(P.limiar(0.5), P.limiar(0.1))
        self.assertGreaterEqual(P.limiar(0.0, -0.15), 0.2); self.assertLessEqual(P.limiar(1.0, 0.15), 0.6)

    def test_cansada_segura_o_impulso_de_ir_atras_e_quer_descansar(self):
        cheia = P.decidir(quadro(energia=1.0, vontade_estudar=0.6))
        cansada = P.decidir(quadro(energia=0.15, vontade_estudar=0.6, horas=18))
        self.assertLess(cansada["impulsos"]["estudar"]["valor"], cheia["impulsos"]["estudar"]["valor"])
        self.assertIn("descansar", cansada["agir"]); self.assertNotIn("descansar", cheia["agir"])

    def test_o_que_deu_errado_antes_vale_menos_depois(self):
        q = quadro(vontade_estudar=0.5)
        antes = P.decidir(q)["impulsos"]["estudar"]["valor"]
        P.ARQ.get()["aprendido"]["estudar"]["media"] = 0.0
        depois = P.decidir(q)["impulsos"]["estudar"]["valor"]
        self.assertLess(depois, antes)

    def test_aprender_com_os_erros_quer_estudar_e_nada_acontece_a_media_cai(self):
        est = P.ARQ.get()
        for k in range(4):                                                          # janelas de 10 min querendo estudar com o contador de estudos parado
            q = quadro(vontade_estudar=0.9, agora=AGORA + k * P.JANELA_S)
            P.aprender(P.decidir(q, est), q, est)
        self.assertLess(est["aprendido"]["estudar"]["media"], 0.5)
        self.assertGreaterEqual(est["aprendido"]["estudar"]["n"], 2)

    def test_aprender_com_os_acertos_quando_o_estudo_aconteceu(self):
        est = P.ARQ.get()
        q1 = quadro(vontade_estudar=0.9)
        P.aprender(P.decidir(q1, est), q1, est)
        q2 = quadro(vontade_estudar=0.9, agora=AGORA + P.JANELA_S, estudos_hoje=1)
        P.aprender(P.decidir(q2, est), q2, est)
        self.assertGreater(est["aprendido"]["estudar"]["media"], 0.5)

    def test_parar_de_querer_antes_da_janela_nao_conta_como_erro(self):
        est = P.ARQ.get()
        q1 = quadro(vontade_estudar=0.9)
        P.aprender(P.decidir(q1, est), q1, est)
        q2 = quadro(vontade_estudar=0.0, agora=AGORA + 60)
        P.aprender(P.decidir(q2, est), q2, est)
        self.assertEqual(est["aprendido"]["estudar"], {"media": 0.5, "n": 0})


class Monitor(Base):
    def test_conflito_e_registrado_mas_nada_e_vetado(self):
        q = quadro(energia=0.1, vontade_estudar=0.95, horas=20)
        dec = P.decidir(q)
        al = P.monitorar(dec, q)
        self.assertTrue(any("descansar" in a and "junto" in a for a in al), al)
        self.assertGreaterEqual(len(dec["agir"]), 2)                                 # ela decide fazer tudo: nada foi cortado
        self.assertEqual(P.ARQ.get()["cont"]["conflitos"], 1)

    def test_falta_de_iniciativa_abulia_baixa_o_limiar(self):
        est = P.ARQ.get()
        est["ult_agir"] = AGORA - 13 * 3600
        q = quadro(vontade_estudar=0.3, vontade_conversar=0.0, tem_camera=False, energia=1.0, horas=0)
        dec = P.decidir(q, est)
        self.assertEqual(dec["agir"], [])
        self.assertTrue(any("iniciativa" in a for a in P.monitorar(dec, q, est)))
        self.assertLess(est["ajuste"], 0)

    def test_compulsao_repetir_o_mesmo_sem_parar_pede_uma_pausa(self):
        al = []
        for k in range(P.COMPULSAO_TICKS + 2):
            q = quadro(agora=AGORA + k)
            al += P.monitorar(P.decidir(q), q)
        self.assertTrue(any("repetindo" in a for a in al))
        self.assertGreaterEqual(P.ARQ.get()["cont"]["compulsoes"], 1)

    def test_limites_diz_a_verdade_do_que_ela_nao_consegue(self):
        txt = " ".join(P.limites(quadro(tem_camera=False, memoria=False, vida=False, curiosidade_ativa=False)))
        for trecho in ("memória", "estado interno", "câmera", "curiosidade", "rostos"):
            self.assertIn(trecho, txt)
        cheia = " ".join(P.limites(quadro()))
        self.assertNotIn("não tenho câmera", cheia)
        self.assertIn("rostos", cheia)                                                # isso é sempre verdade, de propósito


class Metas(Base):
    def test_meta_vira_neuronio_do_lobo_frontal_e_fica_guardada(self):
        ok, m = P.nova_meta("aprender", tema="buracos negros", agora=AGORA)
        self.assertTrue(ok); self.assertEqual(m["tema"], "buracos negros")
        notas = [f.stem for f in self.base("Memorias").glob("*.md")]
        self.assertIn("Meta Aprender sobre buracos negros", notas)
        n = MEM._ler_nota(self.base("Memorias") / "Meta Aprender sobre buracos negros.md")
        self.assertEqual(AN.regiao_de(n["meta"]["tipo"]), "frontal")
        P.ARQ.reiniciar()
        self.assertEqual(len(P.metas("ativa")), 1)                                   # sobreviveu ao "reinício"

    def test_meta_repetida_e_assunto_ruim_sao_recusados(self):
        self.assertTrue(P.nova_meta("aprender", tema="buracos negros")[0])
        self.assertFalse(P.nova_meta("aprender", tema="buracos negros")[0])
        for ruim in ("ab", "x" * 80, "minha senha é 1234 e meu cpf 123.456.789-09", "um dois tres quatro cinco seis"):
            self.assertFalse(P.nova_meta("aprender", tema=ruim)[0], ruim)
        self.assertFalse(P.nova_meta("destruir", tema="x")[0])
        self.assertFalse(P.nova_meta("aprender", tema="estrelas", origem="hacker")[0])

    def test_arquivar_nao_apaga(self):
        P.nova_meta("aprender", tema="buracos negros")
        self.assertEqual(P.arquivar_meta("buracos"), "Aprender sobre buracos negros")
        self.assertEqual(P.metas("ativa"), [])
        self.assertEqual(len(P.metas("arquivada")), 1)
        self.assertTrue(any(f.stem.startswith("Meta") for f in self.base("Memorias").glob("*.md")))     # o neurônio continua lá
        self.assertTrue(P.nova_meta("aprender", tema="buracos negros")[0])                                # e dá para recomeçar

    def test_arquivo_adulterado_nao_derruba_nem_inventa_meta(self):
        P.nova_meta("aprender", tema="buracos negros")
        arq = self.base(".cerebro", "prefrontal.json")
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["metas"]["m99"] = {"tipo": "apagar-tudo", "estado": "ativa", "origem": "dono", "titulo": "x"}
        d["metas"]["../x"] = {"tipo": "ver", "estado": "ativa", "origem": "dono", "titulo": "y"}
        d["ajuste"] = 9e9; d["aprendido"]["estudar"] = {"media": "lixo", "n": -5}; d["decisoes"] = "não é lista"
        arq.write_text(json.dumps(d), encoding="utf-8")
        P.ARQ.reiniciar()
        est = P.ARQ.get()
        self.assertEqual(list(est["metas"]), ["m1"])
        self.assertEqual(est["ajuste"], 0.15); self.assertEqual(est["aprendido"]["estudar"], {"media": 0.5, "n": 0}); self.assertEqual(est["decisoes"], [])
        arq.write_text("{lixo", encoding="utf-8"); P.ARQ.reiniciar()
        self.assertEqual(P.metas(), [])

    def test_empurra_a_curiosidade_no_maximo_a_cada_3h_e_so_sem_obstaculo(self):
        P.nova_meta("aprender", tema="buracos negros")
        est = P.ARQ.get()
        q = quadro()
        dec = P.decidir(q, est)
        self.assertIn("estudar", dec["agir"])
        with mock.patch.object(CUR, "interesse", return_value=True) as it:
            self.assertEqual(len(P.perseguir(dec, q, est)), 1)
            self.assertEqual(len(P.perseguir(dec, quadro(agora=AGORA + 3600), est)), 0)              # 1 h depois: cedo demais
            self.assertEqual(len(P.perseguir(dec, quadro(agora=AGORA + 3 * 3600 + 1), est)), 1)
            self.assertEqual(it.call_count, 2)
            it.assert_called_with("buracos negros", 1.0)
        q2 = quadro(curiosidade_ativa=False, agora=AGORA + 99 * 3600)                                   # o dono desligou: ela respeita e diz por quê
        with mock.patch.object(CUR, "interesse", return_value=True) as it:
            P.perseguir(P.decidir(q2, est), q2, est)
            it.assert_not_called()
        self.assertIn("curiosidade", P.metas("ativa")[0]["nota"])

    def test_meta_que_empaca_passa_a_vez_flexibilidade_e_depois_volta(self):
        P.nova_meta("aprender", tema="buracos negros")
        est = P.ARQ.get()
        with mock.patch.object(CUR, "interesse", return_value=True):
            for k in range(3):
                q = quadro(agora=AGORA + k * (3 * 3600 + 1))
                feitos = P.perseguir(P.decidir(q, est), q, est)
            self.assertTrue(any("passo a vez" in f for f in feitos), feitos)
            m = list(est["metas"].values())[0]
            self.assertGreater(m["pausa_ate"], q["agora"])
            q = quadro(agora=q["agora"] + 4 * 3600)                                                        # ainda em pausa: não empurra
            self.assertEqual(P.perseguir(P.decidir(q, est), q, est), [])
            q = quadro(agora=m["pausa_ate"] + 1)                                                           # passou o dia: volta
            self.assertEqual(len(P.perseguir(P.decidir(q, est), q, est)), 1)

    def test_meta_cumprida_vira_decisao_guardada(self):
        P.nova_meta("aprender", tema="buracos negros")
        est = P.ARQ.get()
        q = quadro(temas_estudados={"buracos negros": 1})
        feitos = P.perseguir(P.decidir(q, est), q, est)
        self.assertTrue(any("cumpri" in f for f in feitos))
        self.assertEqual(len(P.metas("cumprida")), 1)
        self.assertTrue(any(f.stem.startswith("Meta cumprida") for f in self.base("Memorias").glob("*.md")))

    def test_metas_de_ver_e_conhecer_medem_numeros_que_existem(self):
        P.nova_meta("ver", alvo=10); P.nova_meta("conhecer", alvo=20)
        est = P.ARQ.get()
        q = quadro(coisas=5, memorias=10)
        P.perseguir(P.decidir(q, est), q, est)
        prog = {m["tipo"]: m["progresso"] for m in P.metas("ativa")}
        self.assertEqual(prog, {"ver": 0.5, "conhecer": 0.5})
        q = quadro(coisas=3, tem_camera=False)
        P.perseguir(P.decidir(q, est), q, est)
        self.assertIn("câmera", [m for m in P.metas("ativa") if m["tipo"] == "ver"][0]["nota"])

    def test_semear_cria_duas_metas_uma_vez_so(self):
        self.assertTrue(P.semear()); self.assertFalse(P.semear())
        self.assertEqual(sorted(m["tipo"] for m in P.metas("ativa")), ["conhecer", "ver"])
        self.assertTrue(all(m["origem"] == "propria" for m in P.metas()))

    def test_plano_antecipa_obstaculos_e_olha_o_que_ja_sabe(self):
        MEM.guardar("Buracos negros", "Estudo meu antigo sobre buracos negros e estrelas", "fato")
        P.nova_meta("aprender", tema="buracos negros")
        m = P.metas("ativa")[0]
        pl = P.plano(m, quadro(curiosidade_ativa=False, estudo_no_teto=True))
        self.assertEqual(len(pl["obstaculos"]), 2)
        self.assertTrue(pl["proximo"].startswith("esperar"))
        self.assertIn("Buracos negros", pl["passos"][0])
        self.assertEqual(P.plano(m, quadro())["obstaculos"], [])


class Pensar(Base):
    def test_um_passo_registra_so_quando_a_decisao_muda_e_so_acrescenta(self):
        arq = self.base(".cerebro", "decisoes.jsonl")
        P.pensar(quadro(agora=AGORA))
        P.pensar(quadro(agora=AGORA + 20))                                            # igual: não escreve de novo
        self.assertEqual(arq.read_text(encoding="utf-8").count("\n"), 1)
        P.pensar(quadro(agora=AGORA + 40, vontade_estudar=0.0, tem_camera=False))     # decisão mudou
        txt = arq.read_text(encoding="utf-8")
        self.assertEqual(txt.count("\n"), 2)
        self.assertEqual(json.loads(txt.splitlines()[0])["agir"], ["olhar", "estudar"])
        self.assertEqual(json.loads(txt.splitlines()[1])["agir"], [])
        self.assertEqual(P.ARQ.get()["cont"]["pensamentos"], 3)

    def test_mudancas_entram_no_foco(self):
        P.pensar(quadro(agora=AGORA))
        P.pensar(quadro(agora=AGORA + 20, estudos_hoje=1, olhadas_hoje=1, conversas_hoje=1, ult_tema="origem das estrelas"))
        self.assertEqual({(i["origem"], i["tipo"]) for i in P.foco(AGORA + 20)}, {("estudo", "novo"), ("visao", "olhada"), ("fala", "conversa")})

    def test_observar_devolve_todos_os_campos_com_os_modulos_de_verdade(self):
        q = P.observar(AGORA)
        for k in quadro():
            self.assertIn(k, q)
        json.dumps(q)

    def test_laco_sobrevive_a_erro_e_semeia_na_primeira_volta(self):
        voltas = []

        def dorme(s):
            voltas.append(s)
            if len(voltas) >= 3:
                raise KeyboardInterrupt
        with mock.patch.object(P.time, "sleep", dorme), mock.patch.object(P, "pensar", side_effect=[RuntimeError("x"), {"ok": 1}, {"ok": 2}]) as pens:
            with self.assertRaises(KeyboardInterrupt):
                P.laco(intervalo=1)
        self.assertEqual(pens.call_count, 3)
        self.assertEqual(len(P.metas("ativa")), 2)                                    # semeou na primeira volta

    def test_resumo_para_o_painel_e_serializavel(self):
        P.nova_meta("aprender", tema="buracos negros")
        P.pensar(quadro())
        r = P.resumo()
        json.dumps(r)
        self.assertEqual(r["metas"][0]["titulo"], "Aprender sobre buracos negros")
        self.assertIn("estudar", r["agir"]); self.assertEqual(set(r["impulsos"]), set(P.IMPULSOS))


class PorVoz(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(MAIN.C, "responder", side_effect=AssertionError("foi parar na IA"))
        p.start(); self.addCleanup(p.stop)

    def test_perguntas_do_precortex_nao_gastam_ia(self):
        P.pensar(quadro())
        self.assertIn("Agora eu quero", MAIN.processar("o que você decidiu?"))
        self.assertIn("Não tenho metas ativas", MAIN.processar("quais são as suas metas?"))
        self.assertIn("O que eu não consigo agora", MAIN.processar("o que você não consegue fazer agora?"))
        self.assertIn("modelo de software, não consciência", MAIN.processar("como funciona o seu pré-córtex?"))
        self.assertTrue(MAIN.processar("no que você está focada?").startswith(("Estou com a atenção", "Meu foco")))

    def test_criar_e_arquivar_meta_por_voz(self):
        r = MAIN.processar("tenha como meta aprender sobre buracos negros")
        self.assertIn("Combinado", r); self.assertEqual(P.metas("ativa")[0]["tema"], "buracos negros")
        self.assertIn("buracos negros", MAIN.processar("quais são as suas metas?"))
        self.assertIn("Arquivei", MAIN.processar("arquive a meta buracos"))
        self.assertIn("Não achei", MAIN.processar("arquive a meta buracos"))
        self.assertIn("Combinado", MAIN.processar("sua meta é ver 12 coisas"))
        self.assertEqual([m["alvo"] for m in P.metas("ativa")], [12])

    def test_assunto_da_meta_mantem_os_acentos(self):
        self.assertIn("Combinado", MAIN.processar("Tenha como meta aprender sobre córtex pré-frontal."))
        self.assertEqual(P.metas("ativa")[0]["tema"], "córtex pré-frontal")

    def test_frases_parecidas_mas_de_outro_assunto_nao_sao_sequestradas(self):
        for t in ("qual é o seu foco principal no trabalho de amanhã, me ajude a planejar?", "o que você decidiu comer hoje à noite e por quê?",
                  "me conte a meta do time de vendas deste mês", "estude sobre córtex pré-frontal"):
            self.assertIsNone(P.tratar(t), t)

    def test_nao_ha_ferramenta_da_ia_para_isso(self):
        nomes = " ".join(B.FERRAMENTAS)
        for palavra in ("meta", "prefrontal", "foco", "gesto", "maos", "modelo3d", "decid"):
            self.assertNotIn(palavra, nomes, palavra)

    def test_painel_recebe_o_precortex_e_as_maos(self):
        e = MAIN.estado_completo()
        json.dumps(e)
        self.assertIn("prefrontal", e); self.assertIn("maos", e)


class SoLeOResto(Base):
    """O pedido do dono: «não modifique nada, se ela quiser fazer tudo ao mesmo tempo ela que decide». O pré-córtex não pode virar trava, fila nem chave dos outros laços."""
    FONTE = (FONTES / "prefrontal.py").read_text(encoding="utf-8")

    def test_so_importa_o_que_precisa_para_ler(self):
        achados = set()
        for no in ast.walk(ast.parse(self.FONTE)):
            if isinstance(no, ast.Import):
                achados |= {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom) and no.module:
                achados.add(no.module.split(".")[0])
        self.assertTrue(achados <= {"os", "re", "json", "time", "threading", "datetime", "memoria", "estado", "vida", "ferramentas", "curiosidade", "conversa", "visao", "autonomia", "tarefas"}, achados)
        for proibido in ("broker", "catalogo", "cerebro", "android", "protocolos", "neuronios", "internet", "maos", "main"):
            self.assertNotIn(proibido, achados)

    def test_das_tarefas_so_le_o_resumo(self):
        """Fase 2: o pré-córtex lê as tarefas (contagens por meta); não cria, executa nem cancela nenhuma."""
        usos = {n.attr for n in ast.walk(ast.parse(self.FONTE)) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "TAR"}
        self.assertEqual(usos, {"resumo_por_meta"})

    def test_so_chama_nos_outros_o_que_le_ou_o_caminho_seguro_de_sempre(self):
        chamadas = set(re.findall(r"\b(CUR|CONV|VIS|AUT|F|V|M|N|B)\.([a-zA-Z_]+)\(", self.FONTE))
        permitido = {("CUR", "interesse"), ("CUR", "ativa"), ("CUR", "passou_do_teto"), ("CUR", "_tema_valido"), ("CUR", "_e"), ("CONV", "resumo"), ("VIS", "resumo"),
                     ("AUT", "modo"), ("F", "em_descanso"), ("F", "em_silencio"), ("M", "guardar"), ("M", "buscar"), ("M", "ativo"), ("M", "base"), ("M", "_fold"), ("M", "_dentro"),
                     ("V", "nivel"), ("V", "energia"), ("V", "vontade_estudar"), ("V", "vontade_conversar"), ("V", "horas_acordada"), ("V", "ligada"), ("V", "humor")}
        self.assertTrue(chamadas <= permitido, chamadas - permitido)

    def test_nao_toca_nos_laços_nem_nas_chaves_do_dono(self):
        fonte = self.FONTE.replace("def laco", "def _laco_proprio")
        for ruim in (r"\.AVISAR", r"\.FALAR", r"\.laco\b", r"ASSINCRONO", r"\b(?:CUR|CONV|VIS|AUT|F|V)\.\w+\s*=[^=]", r"os\.(?:remove|unlink)", r"rmtree", r"\bevento\(", r"\.ligar\(|\.desligar\("):
            self.assertIsNone(re.search(ruim, fonte), ruim)

    def test_decidir_nunca_exclui_um_impulso_por_causa_de_outro(self):
        q = quadro(vontade_estudar=1.0, vontade_conversar=1.0, coisas=0, acetilcolina=1.0, energia=0.1, horas=30)
        self.assertEqual(P.decidir(q)["impulsos"]["olhar"]["decisao"], "agir")
        for k in ("vontade_estudar", "vontade_conversar"):                              # zerar a vontade de estudar ou de conversar não muda o olhar: não há disputa
            self.assertEqual(P.decidir({**q, k: 0.0})["impulsos"]["olhar"]["decisao"], "agir")

    def test_os_laços_dos_outros_modulos_continuam_decidindo_sozinhos(self):
        for nome, trecho in (("visao.py", "if vez_de_olhar():\n                olhar(pedido=False)"), ("curiosidade.py", "if vez_de_estudar():\n                estudar()"),
                             ("conversa.py", "if vez_de_falar():\n                falar_agora(falar)")):
            codigo = (FONTES / nome).read_text(encoding="utf-8")
            self.assertIn(trecho, codigo, nome)
            self.assertNotIn("prefrontal", codigo, nome)                                 # nem consultam o pré-córtex


if __name__ == "__main__":
    unittest.main()
