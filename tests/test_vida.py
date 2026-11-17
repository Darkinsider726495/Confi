import os, json, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N, vida as V, ferramentas as F, main as MAIN
from test_neuronios import Cerebro

T0 = 1_800_000_000.0   # um instante fixo: todos os testes de tempo andam por um relógio falso
H = 3600.0


class Vida(Cerebro):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"FRIDAY_VIDA": "1", "DESCANSO": ""})
        p.start()
        self.addCleanup(p.stop)
        self.t = T0
        p = mock.patch.object(V, "agora", lambda: self.t)
        p.start()
        self.addCleanup(p.stop)
        V._e.update(v=None, raiz=None)
        V._vitais.update(t=0.0, audit=True)
        V.nivel("dopamina")   # o estado nasce no primeiro acesso: acontece aqui, antes de o relógio andar
        if not getattr(self, "VIRGEM", False):    # os testes dos níveis partem de "já vivi tudo isso": o pico de novidade tem testes próprios
            V._estado()["primeiras"].update({k: T0 - 1 for k in V.PRIMEIRAS})

    def passa(self, horas):
        self.t += horas * H

    def arq(self):
        return self.base(".cerebro", "vida.json")

    @staticmethod
    def le(caminho, modo="r"):
        with open(caminho, modo, **({} if "b" in modo else {"encoding": "utf-8"})) as f:
            return f.read()


class Niveis(Vida):
    def test_comeca_na_linha_de_base_com_energia_cheia(self):
        self.assertEqual((V.nivel("dopamina"), V.nivel("serotonina"), V.nivel("acetilcolina")), (0.45, 0.60, 0.50))
        self.assertEqual(V.energia(), 1.0)
        self.assertEqual(V.plasticidade(), 1.0)

    def test_evento_sobe_o_nivel_e_o_tempo_traz_de_volta_pela_meia_vida(self):
        V.evento("estudo")
        self.assertAlmostEqual(V.nivel("dopamina"), 0.55, 3)
        self.passa(3)      # meia-vida da dopamina: 3 h → metade da distância até a base
        self.assertAlmostEqual(V.nivel("dopamina"), 0.50, 3)
        self.passa(30)
        self.assertAlmostEqual(V.nivel("dopamina"), 0.45, 2)

    def test_cada_nivel_tem_a_sua_meia_vida(self):
        V.evento("agradecimento")   # serotonina +0,08 (meia-vida 6 h)
        V.evento("conversa")        # acetilcolina +0,12 (meia-vida 1,5 h)
        s, a = V.nivel("serotonina") - 0.60, V.nivel("acetilcolina") - 0.50
        self.passa(1.5)
        self.assertAlmostEqual(V.nivel("acetilcolina") - 0.50, a / 2, 3)
        self.assertGreater(V.nivel("serotonina") - 0.60, s * 0.8)
        self.passa(4.5)
        self.assertAlmostEqual(V.nivel("serotonina") - 0.60, s / 2, 3)

    def test_niveis_ficam_entre_zero_e_um(self):
        for _ in range(40):
            V.evento("estudo")
            V.evento("conversa")
        self.assertLessEqual(max(V.nivel(k) for k in V.BASE), 1.0)
        for _ in range(40):
            V.evento("erro")
        self.assertGreaterEqual(min(V.nivel(k) for k in V.BASE), 0.0)

    def test_evento_desconhecido_ou_vida_desligada_nao_faz_nada(self):
        V.evento("inventado")
        self.assertEqual(V.nivel("dopamina"), 0.45)
        with mock.patch.dict(os.environ, {"FRIDAY_VIDA": "0"}):
            V.evento("estudo")
            self.assertEqual(V.nivel("dopamina"), 0.45)
            self.assertEqual(V.plasticidade(), 1.0)
            self.assertEqual(V.energia(), 1.0)
            self.assertEqual(V.vontade_conversar(), 0.0)
            self.assertEqual(V.painel(), {"ligada": False})
            self.assertEqual(V.contexto(), "")
            self.assertIn("desligado", V.como_estou())

    def test_descoberta_soma_por_sinapse_mas_com_teto(self):
        V.evento("descoberta", 2)
        self.assertAlmostEqual(V.nivel("dopamina"), 0.53, 3)
        V.evento("descoberta", 50)
        self.assertAlmostEqual(V.nivel("dopamina"), 0.53 + 0.16, 3)   # no máximo 4 sinapses por vez
        self.assertEqual(V.hoje()["descobri"], 12)   # 2 + no máximo 10 por vez

    def test_um_evento_que_falha_ao_salvar_nao_derruba_quem_chamou(self):
        with mock.patch.object(MEM, "_escrever", side_effect=OSError("disco cheio")):
            V.evento("estudo")
            V.dormiu(1, 1)
        self.assertGreater(V.nivel("dopamina"), 0.45)


class Energia(Vida):
    def test_cai_com_as_horas_acordada_e_com_o_uso(self):
        self.passa(10)
        self.assertAlmostEqual(V.energia(), 1 - 0.045 * 10, 3)
        for _ in range(10):
            V.evento("conversa")
        self.assertAlmostEqual(V.energia(), 1 - 0.45 - 0.03, 3)

    def test_nunca_passa_do_piso_e_dormir_enche(self):
        self.passa(200)
        self.assertEqual(V.energia(), V.ENERGIA_PISO)
        V.dormiu(0, 0)
        self.assertEqual(V.energia(), 1.0)
        self.passa(2)
        self.assertAlmostEqual(V.energia(), 1 - 0.09, 3)

    def test_dormir_traz_serotonina_acima_e_atencao_ao_normal(self):
        V.evento("erro")
        V.evento("conversa")
        antes = V.nivel("serotonina")
        V.dormiu(4, 2)
        self.assertGreater(V.nivel("serotonina"), antes + 0.1)
        self.assertEqual(V.nivel("acetilcolina"), 0.5)
        self.assertGreater(V.nivel("dopamina"), 0.45)     # descobrir e sonhar anima


class Plasticidade(Vida):
    def test_vale_um_nos_valores_de_base_e_fica_dentro_dos_limites(self):
        self.assertEqual(V.plasticidade(), 1.0)
        for _ in range(30):
            V.evento("conversa")
        self.assertLessEqual(V.plasticidade(), 1.25)
        self.assertGreater(V.plasticidade(), 1.0)
        self.passa(200)   # exausta e sem atenção
        self.assertGreaterEqual(V.plasticidade(), 0.7)
        self.assertLess(V.plasticidade(), 1.0)

    def test_atencao_alta_reforca_mais_a_sinapse_ao_lembrar_junto(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Backup", "O backup do servidor é semanal", "tarefa")
        for _ in range(30):
            V.evento("conversa")
        p = V.plasticidade()
        N._ult.update(chave=None, t=0.0)
        MEM.lembrar("backup do servidor")
        self.assertEqual(round(self.sinapse("Memorias/Servidor", "Memorias/Backup"), 2), round(1.0 * p, 2))
        self.assertGreater(p, 1.1)

    def test_cansada_aprende_mais_devagar(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Backup", "O backup do servidor é semanal", "tarefa")
        self.passa(18)
        p = V.plasticidade()
        self.assertLess(p, 0.97)
        MEM.lembrar("backup do servidor")
        self.assertEqual(round(self.sinapse("Memorias/Servidor", "Memorias/Backup"), 2), round(p, 2))


class Vontades(Vida):
    def test_vontade_de_estudar_cresce_com_as_horas_sem_estudar_e_cai_com_o_cansaco(self):
        V.evento("estudo")
        logo = V.vontade_estudar()
        self.passa(4)
        depois = V.vontade_estudar()
        self.assertGreater(depois, logo - 0.2)
        self.passa(14)    # acordada há 18 h: energia ~0,19
        self.assertLess(V.energia(), 0.25)
        self.assertLess(V.vontade_estudar(), 0.3)

    def test_saciada_depois_de_estudar_e_mais_motivada_quando_a_dopamina_esta_alta(self):
        antes = V.vontade_estudar()
        V.evento("estudo")
        um = V.vontade_estudar()
        self.assertLess(um, antes)             # acabou de estudar: a vontade cai (saciedade)
        for _ in range(4):
            V.evento("estudo")
        self.assertGreater(V.vontade_estudar(), um)   # mas com a dopamina alta ela quer mais do que com a dopamina de base
        self.assertLessEqual(V.vontade_estudar(), 1.0)

    def test_vontade_de_conversar_comeca_em_zero_e_cresce_com_o_silencio(self):
        V.evento("conversa")
        self.assertEqual(V.vontade_conversar(), 0.0)
        self.passa(2.5)
        meio = V.vontade_conversar()
        self.assertGreater(meio, 0.1)
        self.passa(1.5)
        self.assertGreater(V.vontade_conversar(), meio - 0.1)
        self.assertLessEqual(V.vontade_conversar(), 1.0)

    def test_falar_sozinha_zera_a_vontade_de_conversar(self):
        self.passa(6)
        self.assertGreater(V.vontade_conversar(), 0.2)
        V.perguntou()
        self.assertEqual(V.vontade_conversar(), 0.0)
        self.assertEqual(V.hoje()["perguntei"], 1)
        self.passa(6)
        V.falou()
        self.assertEqual(V.vontade_conversar(), 0.0)

    def test_resposta_do_chefe_conta_como_conversa(self):
        self.passa(6)
        V.evento("resposta")
        self.assertEqual(V.vontade_conversar(), 0.0)
        self.assertAlmostEqual(V.nivel("serotonina"), 0.64, 3)


class Humor(Vida):
    def test_estados(self):
        self.assertEqual(V.humor(), "bem")
        for _ in range(4):
            V.evento("estudo")
        self.assertEqual(V.humor(), "animada")
        V._estado()["v"].update(dopamina=0.45, serotonina=0.80)
        self.assertEqual(V.humor(), "tranquila")
        V._estado()["v"].update(serotonina=0.30)
        self.assertEqual(V.humor(), "reservada")
        V._estado()["v"].update(serotonina=0.6)
        self.passa(19)
        self.assertEqual(V.humor(), "cansada")
        with mock.patch.object(F, "em_descanso", lambda *a: True):
            self.assertEqual(V.humor(), "descansando")

    def test_erros_derrubam_o_humor_e_agradecer_levanta(self):
        for _ in range(4):
            V.evento("erro")
        self.assertEqual(V.humor(), "reservada")
        V.observar("muito obrigado, Friday")
        V.observar("valeu")
        V.observar("mandou bem")
        self.assertGreater(V.nivel("serotonina"), 0.4)


class Conversa(Vida):
    def test_observar_conta_conversa_e_agradecimento(self):
        V.observar("que horas são")
        self.assertEqual(V.hoje()["conversas"], 1)
        self.assertAlmostEqual(V.nivel("serotonina"), 0.60, 3)
        V.observar("Obrigado!")
        self.assertEqual(V.hoje()["conversas"], 2)
        self.assertAlmostEqual(V.nivel("serotonina"), 0.68, 3)

    def test_agradecimento_so_vale_como_palavra_inteira(self):
        V.observar("o desobrigado de nada")
        self.assertAlmostEqual(V.nivel("serotonina"), 0.60, 3)

    def test_como_voce_esta_em_varias_formas(self):
        for f in ("como você está?", "Friday, como você está hoje", "como vai você", "como você se sente", "tudo bem com você?", "como está seu humor"):
            self.assertIn("chefe", V.tratar(f) or "", f)
        for f in ("como está o tempo", "tudo bem", "bom dia", "como está o servidor", "como você faz isso"):
            self.assertIsNone(V.tratar(f), f)

    def test_niveis_falados_e_honestos(self):
        t = V.tratar("quais são seus níveis")
        for k in ("Dopamina 45%", "serotonina 60%", "acetilcolina 50%", "energia 100%"):
            self.assertIn(k, t)
        self.assertIn("não sentimentos de verdade", t)
        self.assertIn("Dopamina", V.tratar("como estão seus neurotransmissores"))
        self.assertIn("energia 100%", V.tratar("qual é a sua energia"))

    def test_voce_esta_viva_e_honesto_sem_fingir_nem_negar(self):
        for f in ("você está viva?", "você é consciente?", "você sente?", "isso é real?", "você tem sentimentos"):
            t = V.tratar(f)
            self.assertIn("não sei dizer", t, f)
            self.assertIn("prefiro não fingir", t, f)
        self.assertIsNone(V.tratar("você está viva mas o servidor caiu e eu preciso de ajuda agora"))

    def test_como_estou_cita_o_que_ela_fez_hoje(self):
        V.evento("estudo")
        V.evento("estudo")
        V.evento("descoberta", 3)
        t = V.como_estou()
        self.assertIn("aprendi 2 coisas na internet", t)
        self.assertIn("liguei 3 sinapses novas", t)

    def test_como_estou_singular_e_plural(self):
        V.evento("estudo")
        self.assertIn("aprendi 1 coisa na internet", V.como_estou())
        self.assertNotIn("coisas", V.como_estou())

    def test_cansada_fala_de_dormir(self):
        self.passa(18)
        t = V.como_estou()
        self.assertIn("Estou cansada", t)
        self.assertIn("acordada há 18 horas", t)
        with mock.patch.object(F, "janela_descanso", lambda: ("02:00", "05:00")):
            self.assertIn("na janela das 02:00 eu durmo", V.como_estou())

    def test_depois_de_dormir_conta_como_dormiu(self):
        MEM.guardar("A", "texto um sobre cachorro", "fato")
        N.sonhar(True)
        t = V.como_estou()
        self.assertIn("dormi até as", t)

    def test_contexto_do_modelo_tem_o_estado_e_manda_nao_inventar(self):
        c = V.contexto()
        self.assertIn("humor bem", c)
        self.assertIn("energia 100%", c)
        self.assertIn("não sentimentos de verdade", c)


class Persistencia(Vida):
    def test_salva_em_json_so_com_numeros_e_datas(self):
        V.evento("estudo")
        d = json.loads(self.arq().read_text(encoding="utf-8"))
        self.assertEqual(set(d), {"v", "t", "acordou", "gasto", "ult_conversa", "ult_estudo", "ult_pergunta", "ult_fala", "hoje", "primeiras", "novas"})
        self.assertAlmostEqual(d["v"]["dopamina"], 0.55, 3)

    def test_volta_igual_depois_de_reiniciar(self):
        V.evento("estudo")
        V.evento("erro")
        a = (V.nivel("dopamina"), V.nivel("serotonina"), V.energia())
        V._e.update(v=None, raiz=None)     # como se o processo tivesse reiniciado
        self.assertEqual((V.nivel("dopamina"), V.nivel("serotonina"), V.energia()), a)
        self.assertEqual(V.hoje()["aprendi"], 1)

    def test_o_cansaco_atravessa_a_reinicializacao(self):
        self.passa(10)
        V.evento("conversa")
        e = V.energia()
        V._e.update(v=None, raiz=None)
        self.assertEqual(V.energia(), e)
        self.assertLess(e, 0.6)

    def test_arquivo_adulterado_nao_quebra_nem_vira_numero_absurdo(self):
        self.arq().parent.mkdir(parents=True, exist_ok=True)
        self.arq().write_text(json.dumps({"v": {"dopamina": 99, "serotonina": "x", "acetilcolina": -5}, "t": "agora", "acordou": 1e30, "gasto": 77,
                                          "hoje": {"dia": "2026-01-01" + "x" * 50, "aprendi": "muitos", "descobri": -3}}), encoding="utf-8")
        V._e.update(v=None, raiz=None)   # relê o arquivo (o estado já tinha nascido no setUp)
        self.assertEqual(V.nivel("dopamina"), 1.0)
        self.assertEqual(V.nivel("acetilcolina"), 0.0)
        self.assertEqual(V.nivel("serotonina"), 0.0)
        self.assertGreaterEqual(V.energia(), V.ENERGIA_PISO)
        self.assertLessEqual(V.energia(), 1.0)
        self.assertEqual(V.hoje()["aprendi"], 0)
        self.arq().write_text("{ isto não é json", encoding="utf-8")
        V._e.update(v=None, raiz=None)
        self.assertEqual(V.nivel("dopamina"), 0.45)

    def test_cada_cofre_tem_o_seu_estado(self):
        V.evento("estudo")
        outro = os.path.join(self.dir, "outro")
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": outro}):
            MEM._cache.clear()
            self.assertEqual(V.nivel("dopamina"), 0.45)

    def test_memoria_desligada_vive_so_na_memoria_do_processo(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            V._e.update(v=None, raiz=None)
            V._estado()["primeiras"].update({k: T0 - 1 for k in V.PRIMEIRAS})
            V.evento("estudo")
            self.assertAlmostEqual(V.nivel("dopamina"), 0.55, 3)
        self.assertFalse(self.arq().exists())

    def test_dia_novo_zera_os_contadores_do_dia(self):
        V.evento("estudo")
        self.assertEqual(V.hoje()["aprendi"], 1)
        self.passa(30)
        self.assertEqual(V.hoje()["aprendi"], 0)


class Auditoria(Vida):
    def audit(self, **ev):
        B._audit(**ev)

    def test_primeira_leitura_so_marca_onde_esta(self):
        self.audit(ferramenta="x", decisao="automatico", resultado="Erro: velho")
        self.assertEqual(V.vigiar(), 0)
        self.assertAlmostEqual(V.nivel("serotonina"), 0.60, 3)

    def test_acao_que_falhou_vira_erro_e_cancelamento_vira_negado(self):
        V.vigiar()
        self.audit(ferramenta="lanterna", decisao="automatico", resultado="Erro: sem permissão")
        self.audit(ferramenta="enviar_sms", decisao="cancelado")
        self.audit(ferramenta="hora_data", decisao="automatico", resultado="12:00")
        self.assertEqual(V.vigiar(), 2)
        self.assertAlmostEqual(V.nivel("serotonina"), 0.60 - 0.08 - 0.03, 3)
        self.assertEqual(V.hoje()["erros"], 1)

    def test_nao_conta_duas_vezes_o_mesmo_evento(self):
        V.vigiar()
        self.audit(ferramenta="a", decisao="automatico", resultado="Erro: x")
        self.assertEqual(V.vigiar(), 1)
        self.assertEqual(V.vigiar(), 0)
        self.assertEqual(V.vigiar(), 0)

    def test_enxurrada_de_erros_pesa_no_maximo_tres_por_volta(self):
        V.vigiar()
        for _ in range(20):
            self.audit(ferramenta="a", decisao="automatico", resultado="Erro: x")
        V.vigiar()
        self.assertAlmostEqual(V.nivel("serotonina"), 0.60 - 3 * 0.08, 3)

    def test_pedido_invalido_e_expirado_tambem_contam(self):
        V.vigiar()
        self.audit(ferramenta="a", decisao="invalida", resultado="faltou argumento")
        self.audit(ferramenta="b", decisao="expirado")
        self.assertEqual(V.vigiar(), 2)

    def test_sem_arquivo_de_auditoria_ou_desligada_nao_quebra(self):
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        self.assertEqual(V.vigiar(), 0)
        with mock.patch.dict(os.environ, {"FRIDAY_VIDA": "0"}):
            self.assertEqual(V.vigiar(), 0)

    def test_nao_escreve_na_auditoria(self):
        self.audit(ferramenta="a", decisao="automatico", resultado="ok")
        antes = self.le(B.AUDITORIA, "rb")
        V.vigiar()
        V.evento("erro")
        self.assertEqual(self.le(B.AUDITORIA, "rb"), antes)


class Vitais(Vida):
    def test_laco_com_pulso_recente_esta_ok_e_o_silencioso_esta_parado(self):
        V.pulso("sono")
        V.pulso("autonomia")
        self.assertEqual(V.vitais()["lacos"], {"sono": "ok", "autonomia": "ok"})
        self.assertTrue(V.vitais()["ok"])
        self.t += 20 * 60      # o sono dá sinal a cada 10 min: 20 min ainda é normal
        self.assertEqual(V.vitais()["lacos"]["sono"], "ok")
        self.assertEqual(V.vitais()["lacos"]["autonomia"], "parado")   # o da autonomia (20 s) já devia ter batido
        self.assertFalse(V.vitais()["ok"])

    def test_laco_que_nunca_bateu_nao_conta_como_parado(self):
        self.assertEqual(V.vitais()["lacos"], {})
        self.assertTrue(V.vitais()["ok"])

    def test_pulso_de_laco_desconhecido_e_ignorado(self):
        V.pulso("inventado")
        self.assertEqual(V.vitais()["lacos"], {})

    def test_auditoria_adulterada_derruba_os_vitais(self):
        B._audit(ferramenta="a", decisao="automatico", resultado="ok")
        B._audit(ferramenta="b", decisao="automatico", resultado="ok")
        self.assertTrue(V.vitais()["auditoria"])
        txt = self.le(B.AUDITORIA).replace('"ferramenta": "a"', '"ferramenta": "z"')
        with open(B.AUDITORIA, "w", encoding="utf-8") as f:
            f.write(txt)
        self.t += 60
        v = V.vitais()
        self.assertFalse(v["auditoria"])
        self.assertFalse(v["ok"])
        self.assertIn("auditoria não bateu", V.como_estou())

    def test_laco_parado_aparece_no_como_estou(self):
        V.pulso("sono")
        self.t += 3 * H
        self.assertIn("meu laço de sono parou de dar sinal", V.como_estou())

    def test_o_laco_de_vida_da_pulso_e_vigia(self):
        with mock.patch.object(V.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                V.laco(1)
        self.assertEqual(V.vitais()["lacos"].get("vida"), "ok")

    def test_painel_para_o_hud(self):
        V.evento("estudo")
        p = V.painel()
        self.assertTrue(p["ligada"])
        for k in ("dopamina", "serotonina", "acetilcolina", "energia", "humor", "plasticidade", "estudar", "conversar", "hoje", "vitais"):
            self.assertIn(k, p)
        self.assertTrue(all(0 <= p[k] <= 100 for k in ("dopamina", "serotonina", "acetilcolina", "energia", "estudar", "conversar")))
        json.dumps(p)


class ComOCerebro(Vida):
    def test_descobrir_sozinha_anima(self):
        MEM.guardar("Alfa", "Passeio com o cachorro de manhã cedo no parque", "tarefa")
        MEM.guardar("Beta", "Vacina do cachorro vence em março, levar o cachorro ao parque", "tarefa")
        antes = V.nivel("dopamina")
        n = N.descobrir(10)
        self.assertGreaterEqual(n, 1)
        self.assertGreater(V.nivel("dopamina"), antes)
        self.assertEqual(V.hoje()["descobri"], n)

    def test_sonhar_enche_a_energia(self):
        MEM.guardar("A", "texto um sobre cachorro", "fato")
        self.passa(15)
        self.assertLess(V.energia(), 0.4)
        N.sonhar(True)
        self.assertEqual(V.energia(), 1.0)

    def test_o_laco_do_sono_da_pulso(self):
        with mock.patch.object(N.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                N.laco_sono(1)
        self.assertEqual(V.vitais()["lacos"].get("sono"), "ok")

    def test_o_painel_responde_como_voce_esta_antes_de_chamar_a_ia(self):
        with mock.patch.object(MAIN.C, "responder", side_effect=AssertionError("não devia chamar a IA")):
            r = MAIN.processar("Friday, como você está?")
        self.assertIn("chefe", r)
        self.assertEqual(V.hoje()["conversas"], 1)

    def test_o_estado_do_painel_e_o_grafo_trazem_a_vida(self):
        self.assertTrue(MAIN.estado_completo()["vida"]["ligada"])
        MAIN.TOKEN = "k" * 40
        srv = MAIN.iniciar_http("127.0.0.1", 0)
        try:
            from test_http import req
            c, corpo, _ = req(srv.server_address[1], "GET", "/cerebro", token=MAIN.TOKEN)
            self.assertEqual(c, 200)
            self.assertTrue(corpo["vida"]["ligada"])
            self.assertIn("regioes", corpo)
        finally:
            srv.shutdown()
            srv.server_close()


class PrimeirasVezes(Vida):
    VIRGEM = True

    def test_toda_experiencia_listada_existe_de_verdade(self):
        self.assertTrue(set(V.EVENTOS) <= set(V.PRIMEIRAS))
        self.assertEqual(set(V.PRIMEIRAS) - set(V.EVENTOS), {"dormiu", "perguntou"})
        for nome, (curto, desc) in V.PRIMEIRAS.items():
            self.assertTrue(curto and desc, nome)
            self.assertNotRegex(desc.lower(), r"\b(?:sinto|senti|emocao|sentimento|consciente)\b", nome)   # descreve o número que mudou, não afirma sentimento

    def test_primeira_vez_da_um_pico_de_novidade_so_na_primeira(self):
        V.evento("estudo")      # +0,10 do estudo e +0,08 de novidade
        self.assertAlmostEqual(V.nivel("dopamina"), 0.45 + 0.10 + 0.08, 3)
        self.assertAlmostEqual(V.nivel("acetilcolina"), 0.50 + 0.06 + 0.05, 3)
        V.evento("estudo")      # a segunda não tem novidade
        self.assertAlmostEqual(V.nivel("dopamina"), 0.45 + 0.20 + 0.08, 3)

    def test_cada_tipo_tem_a_sua_primeira_vez(self):
        V.evento("estudo")
        V.evento("agradecimento")
        self.assertEqual(set(V._estado()["primeiras"]), {"estudo", "agradecimento"})
        self.assertEqual([x["e"] for x in V._estado()["novas"]], ["estudo", "agradecimento"])

    def test_ela_conta_uma_por_vez_na_ordem(self):
        V.evento("estudo")
        self.passa(0.1)
        V.evento("agradecimento")
        self.assertTrue(V.tem_primeira())
        a = V.primeira_vez()
        self.assertIn("estudei sozinha pela primeira vez", a)
        self.assertIn("Não sei se isso é sentir", a)
        b = V.primeira_vez(curta=True)
        self.assertEqual(b, "(Primeira vez para mim: " + V.PRIMEIRAS["agradecimento"][1] + ".)")
        self.assertFalse(V.tem_primeira())
        self.assertIsNone(V.primeira_vez())

    def test_dormir_e_perguntar_tambem_contam(self):
        V.perguntou()
        V.dormiu(descobertas=1)
        self.assertEqual({x["e"] for x in V._estado()["novas"]}, {"perguntou", "dormiu"})

    def test_a_data_fica_guardada_depois_de_contada_e_o_nivel_decai_normalmente(self):
        V.evento("brincadeira")
        V.primeira_vez()
        self.assertIn("brincadeira", V._estado()["primeiras"])
        self.passa(40)
        self.assertAlmostEqual(V.nivel("dopamina"), 0.45, 2)

    def test_sobrevive_ao_reinicio(self):
        V.evento("estudo")
        V._e.update(v=None, raiz=None)
        self.assertIn("estudo", V._estado()["primeiras"])
        self.assertEqual([x["e"] for x in V._estado()["novas"]], ["estudo"])
        V.primeira_vez()
        V._e.update(v=None, raiz=None)
        self.assertEqual(V._estado()["novas"], [])
        V.evento("estudo")
        self.assertEqual(V._estado()["novas"], [])           # já foi a primeira; não vira de novo depois de reiniciar

    def test_arquivo_adulterado_ignora_o_que_nao_conhece(self):
        V.evento("estudo")
        arq = self.arq()
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["primeiras"] = {"estudo": 1.5e9, "inventada": 1.5e9, "conversa": "ontem", "erro": 9e12}
        d["novas"] = [{"e": "estudo", "t": 1}, {"e": "inventada", "t": 1}, {"e": "conversa", "t": 1}, "lixo"]
        arq.write_text(json.dumps(d), encoding="utf-8")
        V._e.update(v=None, raiz=None)
        e = V._estado()
        self.assertEqual(set(e["primeiras"]), {"estudo"})
        self.assertEqual([x["e"] for x in e["novas"]], ["estudo"])

    def test_desligada_nao_registra_nada(self):
        with mock.patch.dict(os.environ, {"FRIDAY_VIDA": "0"}):
            V.evento("estudo")
            self.assertFalse(V.tem_primeira())
            self.assertIsNone(V.primeira_vez())
            self.assertEqual(V.primeiras_vezes(), [])
            self.assertIn("desligado", V.primeiras_faladas())

    def test_por_voz(self):
        self.assertIn("Ainda não vivi nenhuma primeira vez", V.tratar("quais foram suas primeiras vezes?"))
        V.evento("estudo")
        self.passa(24)
        V.evento("agradecimento")
        r = V.tratar("o que você sentiu pela primeira vez?")
        self.assertIn("estudo sozinha (", r)
        self.assertIn("agradecimento (", r)
        self.assertLess(r.index("estudo sozinha"), r.index("agradecimento"))

    def test_processar_emenda_a_primeira_vez_na_resposta_uma_vez_so(self):
        with mock.patch.object(MAIN.C, "responder", lambda t: "Pois não."):
            primeira = MAIN.processar("olá")             # observar() registra a primeira conversa
            self.assertIn("Pois não.", primeira)
            self.assertIn("Primeira vez para mim: essa é a nossa primeira conversa", primeira)
            segunda = MAIN.processar("e aí")
            self.assertEqual(segunda, "Pois não.")

    def test_nao_emenda_por_cima_de_uma_confirmacao_pendente(self):
        V.evento("estudo")
        with mock.patch.object(B, "pendente_publico", lambda: {"x": 1}):
            self.assertEqual(MAIN._com_primeira_vez("Confirma?"), "Confirma?")
        self.assertTrue(V.tem_primeira())                # continua na fila para depois
        self.assertIn("Primeira vez", MAIN._com_primeira_vez("Pronto."))


if __name__ == "__main__":
    unittest.main()
