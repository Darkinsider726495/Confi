import os, re, json, time, shutil, tempfile, datetime as dt, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N, main as MAIN
from test_http import req

BIN, LOG = E.termux_falso()


class Cerebro(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cerebro-", dir=E.TMP)
        p = mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": self.dir, "PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        MEM._cache.clear()
        MEM._resumo.update(t=0.0, v=None)
        N._e.update(v=None, raiz=None)
        N._ativos.clear()
        N._ult.update(chave=None, t=0.0)
        N._res.update(t=0.0, v=None)
        N._vec.update(sig=None, pares=[])
        B.PEND = None
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)

    def base(self, *p):
        return Path(self.dir, "FRIDAY", *p)

    def nota(self, pasta, nome, corpo, **meta):
        m = {"tipo": "fato", "importancia": 3, **meta}
        d = self.base(pasta)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{nome}.md").write_text(MEM._montar(m, corpo), encoding="utf-8")
        MEM._cache.clear()

    def dia(self, quando, linhas):
        d = (dt.date.today() - dt.timedelta(days=quando))
        corpo = f"# Conversas de {d:%d/%m/%Y}\n" + "".join(f"\n**{h}** Você: {u}\n> FRIDAY: {r}\n" for h, u, r in linhas)
        self.nota("Conversas", f"{d:%Y-%m-%d}", corpo, tipo="conversa")

    def sinapse(self, a, b):
        return N._estado()["sin"].get(N._chave(a, b), [0, 0])[0]


class Disparo(Cerebro):
    def test_lembrar_junto_fortalece_a_sinapse_e_conta_uso(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Backup", "O backup do servidor é semanal", "tarefa")
        MEM.lembrar("backup do servidor")
        self.assertEqual(self.sinapse("Memorias/Servidor", "Memorias/Backup"), 1.0)
        self.assertEqual(N._estado()["uso"]["Memorias/Backup"][0], 1)

    def par_sem_link(self):
        """Duas memórias que falam do mesmo assunto sem citar o título uma da outra (guardar() liga sozinho quando cita)."""
        MEM.guardar("Alfa", "Passeio com o cachorro de manhã cedo", "tarefa")
        MEM.guardar("Beta", "Vacina do cachorro vence em março", "tarefa")

    def test_na_terceira_vez_vira_link_escrito_nas_duas_notas(self):
        self.par_sem_link()
        for _ in range(3):
            N._ult.update(chave=None)
            MEM.lembrar("cachorro")
        a = self.base("Memorias", "Alfa.md").read_text(encoding="utf-8")
        b = self.base("Memorias", "Beta.md").read_text(encoding="utf-8")
        self.assertIn("[[Beta]] (aprendida)", a)
        self.assertIn("[[Alfa]] (aprendida)", b)
        for _ in range(3):  # idempotente: não repete o link
            N._ult.update(chave=None)
            MEM.lembrar("cachorro")
        self.assertEqual(self.base("Memorias", "Alfa.md").read_text(encoding="utf-8").count("[[Beta]]"), 1)

    def test_o_mesmo_disparo_nao_conta_duas_vezes(self):
        """O contexto automático e a ferramenta 'lembrar' acontecem no mesmo pedido: conta uma vez."""
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Backup", "O backup do servidor é semanal", "tarefa")
        MEM.contexto("backup do servidor")
        MEM.lembrar("backup do servidor")
        self.assertEqual(self.sinapse("Memorias/Servidor", "Memorias/Backup"), 1.0)

    def test_essencial_nao_se_liga_a_tudo(self):
        """O que ela sempre sabe (importância 5) entra em toda conversa, mas não vira sinapse com tudo."""
        MEM.guardar("Alergia", "É alérgico a amendoim", "fato", 5)
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        MEM.guardar("Chá", "Toma chá de camomila à noite, também sem açúcar", "preferencia")
        MEM.contexto("café sem açúcar")
        self.assertEqual(self.sinapse("Memorias/Alergia", "Memorias/Café"), 0)

    def test_ausente_quando_a_memoria_esta_desligada(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            N.disparar([{"origem": "Memorias", "titulo": "X"}])
            self.assertEqual(N.grafo()["nos"], [])
            self.assertIsNone(N.tratar("mostre seu cérebro"))

    def test_nota_privada_nunca_recebe_link(self):
        self.nota("Memorias", "Cofre pessoal", "meu segredo", privado="true", importancia=3)
        MEM.guardar("Outra", "outra coisa", "fato")
        N._promover("Memorias/Cofre pessoal", "Memorias/Outra")
        self.assertNotIn("aprendida", self.base("Memorias", "Cofre pessoal.md").read_text(encoding="utf-8"))


class Grafo(Cerebro):
    def test_nos_e_links_do_obsidian(self):
        MEM.guardar("Marcos", "Marcos é meu chefe", "pessoa")
        MEM.guardar("Reunião semanal", "Toda segunda falo com Marcos", "tarefa")  # ganha [[Marcos]] sozinha
        g = N.grafo()
        titulos = {n["t"]: i for i, n in enumerate(g["nos"])}
        self.assertEqual(set(titulos), {"Marcos", "Reunião semanal"})
        self.assertIn([min(titulos.values()), max(titulos.values()), 1.0, 0], [x[:4] for x in g["arestas"]])
        self.assertEqual(g["stats"]["neuronios"], 2)
        self.assertEqual(g["stats"]["links"], 1)
        self.assertEqual({n["g"] for n in g["nos"]}, {"pessoa", "tarefa"})

    def test_sinapse_aprendida_aparece_antes_de_virar_link(self):
        MEM.guardar("Alfa", "Passeio com o cachorro de manhã cedo", "tarefa")
        MEM.guardar("Beta", "Vacina do cachorro vence em março", "tarefa")
        MEM.lembrar("cachorro")
        g = N.grafo()
        self.assertEqual([x[3] for x in g["arestas"]], [1])  # 1 = só aprendida
        self.assertEqual(g["stats"]["aprendidas"], 1)

    def test_neuronios_acesos_e_notas_privadas_fora(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        self.nota("Memorias", "Diario", "algo íntimo sobre servidor", privado="sim")
        MEM.lembrar("servidor")
        g = N.grafo()
        self.assertEqual([g["nos"][i]["t"] for i in g["ativos"]], ["Servidor"])
        self.assertNotIn("Diario", [n["t"] for n in g["nos"]])

    def test_link_quebrado_nao_vira_aresta(self):
        self.nota("Memorias", "Sozinha", "fala de [[Nada Existe]] e de si mesma [[Sozinha]]")
        g = N.grafo()
        self.assertEqual((len(g["nos"]), g["arestas"]), (1, []))

    def test_dias_de_conversa_entram_como_neuronios(self):
        self.dia(1, [("10:00", "oi", "olá")])
        g = N.grafo()
        self.assertEqual(g["nos"][0]["g"], "conversa")

    def test_trechos_so_quando_pedidos(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        self.assertNotIn("s", N.grafo()["nos"][0])
        self.assertIn("café", N.grafo(trechos=True)["nos"][0]["s"].lower())

    def test_nota_publica_e_caminhos_perigosos(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        self.assertEqual(N.nota_publica("Memorias/Café")["titulo"], "Café")
        for ruim in ("Memorias/../../etc/passwd", "../Memorias/Café", "Memorias/", "Outra/Café", "Memorias/a/b", "/etc/passwd", "", "Memorias/Nada"):
            self.assertIsNone(N.nota_publica(ruim), ruim)
        self.nota("Memorias", "Intima", "segredo", privado="true")
        self.assertIsNone(N.nota_publica("Memorias/Intima"))

    def test_arquivo_de_estado_corrompido_nao_derruba(self):
        MEM.guardar("A", "texto a", "fato")
        (self.base(".cerebro")).mkdir(parents=True, exist_ok=True)
        (self.base(".cerebro", "estado.json")).write_text("{isto não é json", encoding="utf-8")
        N._e.update(v=None)
        self.assertEqual(N.grafo()["stats"]["neuronios"], 1)
        self.assertEqual(N._estado()["sin"], {})


class Autoconhecimento(Cerebro):
    def test_cria_notas_das_ferramentas_e_protocolos_ligadas_ao_hub(self):
        n = N.autoconhecer()
        self.assertGreater(n, 20)
        eu = {f.stem for f in self.base("Eu").glob("*.md")}
        self.assertIn(N.HUB, eu)
        self.assertIn("ferramenta lembrar", eu)
        self.assertIn("Regras de segurança", eu)
        self.assertTrue(any(t.startswith("protocolo ") for t in eu))
        hub = self.base("Eu", N.HUB + ".md").read_text(encoding="utf-8")
        self.assertIn("[[Regras de segurança]]", hub)
        self.assertIn("[[Ações livres (nível 1)]]", hub)
        self.assertIn("nível 2", self.base("Eu", "ferramenta esquecer memoria.md").read_text(encoding="utf-8").lower())

    def test_idempotente_e_so_reescreve_o_que_mudou(self):
        N.autoconhecer()
        self.assertEqual(N.autoconhecer(), 0)
        B.registrar("ferramenta_nova_de_teste", "Faz um teste.", {}, [], lambda: "ok", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "ferramenta_nova_de_teste", None)
        self.assertGreaterEqual(N.autoconhecer(), 2)  # a nota nova e a da categoria
        self.assertTrue(self.base("Eu", "ferramenta ferramenta nova de teste.md").exists())
        B.FERRAMENTAS.pop("ferramenta_nova_de_teste")
        N.autoconhecer()
        self.assertFalse(self.base("Eu", "ferramenta ferramenta nova de teste.md").exists())  # deixou de existir: a nota gerada some

    def test_nao_apaga_notas_suas_na_pasta_eu(self):
        N.autoconhecer()
        self.nota("Eu", "Minha anotação", "isto é meu", tipo="fato")
        N.autoconhecer()
        self.assertTrue(self.base("Eu", "Minha anotação.md").exists())

    def test_descreve_o_corretor_fielmente(self):
        N.autoconhecer()
        t = self.base("Eu", "Regras de segurança.md").read_text(encoding="utf-8")
        for trecho in ("45 segundos", "120", "PIN", "hash", "sobe um degrau"):
            self.assertIn(trecho, t)


class Sono(Cerebro):
    def conversas_repetidas(self):
        self.dia(3, [("09:00", "como está o backup do servidor?", "ok"), ("21:00", "renovar o domínio", "ok")])
        self.dia(2, [("09:00", "o servidor ficou lento", "ok"), ("20:00", "confere o backup", "ok")])
        self.dia(1, [("08:00", "backup do servidor ok?", "sim"), ("18:00", "bom dia", "oi")])

    def test_assuntos_repetidos_viram_topicos_ligados_aos_dias(self):
        self.conversas_repetidas()
        r = N.sonhar(True)
        self.assertIn("tópico", r)
        topicos = {f.stem for f in self.base("Topicos").glob("*.md")}
        self.assertEqual(topicos, {"Servidor", "Backup"})
        t = self.base("Topicos", "Servidor.md").read_text(encoding="utf-8")
        self.assertIn("origem: consolidacao", t)
        self.assertEqual(len(re.findall(r"\[\[\d{4}-\d\d-\d\d\]\]", t)), 3)
        g = N.grafo()
        i = next(i for i, n in enumerate(g["nos"]) if n["t"] == "Servidor")
        self.assertEqual(g["nos"][i]["g"], "topico")
        self.assertGreaterEqual(g["nos"][i]["deg"], 3)  # ligado aos dias de conversa

    def test_palavra_de_um_dia_so_nao_vira_topico(self):
        self.dia(1, [("09:00", "pesquisar sobre blockchain", "ok"), ("10:00", "blockchain de novo", "ok"), ("11:00", "blockchain blockchain", "ok"), ("12:00", "blockchain", "ok")])
        self.dia(2, [("09:00", "outra coisa totalmente diferente", "ok")])
        N.sonhar(True)
        self.assertEqual(list(self.base("Topicos").glob("*.md")) if self.base("Topicos").is_dir() else [], [])

    def test_so_o_que_voce_disse_conta_nunca_a_resposta_nem_a_internet(self):
        for q, h in ((3, "09:00"), (2, "09:00"), (1, "09:00")):
            self.dia(q, [(h, "oi", "texto da página: bitcoin bitcoin bitcoin bitcoin")])
        N.sonhar(True)
        self.assertFalse((self.base("Topicos") / "Bitcoin.md").exists())

    def test_topico_apagado_por_voce_nao_volta(self):
        self.conversas_repetidas()
        N.sonhar(True)
        os.remove(self.base("Topicos", "Servidor.md"))
        MEM._cache.clear()
        N.sonhar(True)
        self.assertFalse(self.base("Topicos", "Servidor.md").exists())

    def test_nota_sua_com_o_mesmo_nome_nao_e_tocada(self):
        self.conversas_repetidas()
        self.nota("Topicos", "Servidor", "meu texto, não mexa", tipo="fato")
        N.sonhar(True)
        self.assertIn("meu texto, não mexa", self.base("Topicos", "Servidor.md").read_text(encoding="utf-8"))

    def test_nao_cria_topico_com_nome_de_memoria_existente(self):
        self.conversas_repetidas()
        MEM.guardar("Servidor", "O servidor de casa", "projeto")
        N.sonhar(True)
        self.assertFalse(self.base("Topicos", "Servidor.md").exists())

    def test_conexoes_aprendidas_sobrevivem_a_nova_consolidacao(self):
        self.conversas_repetidas()
        N.sonhar(True)
        MEM.guardar("Retaguarda", "O servidor de retaguarda faz o backup", "projeto")
        N._promover("Topicos/Servidor", "Memorias/Retaguarda")
        self.assertIn("[[Retaguarda]] (aprendida)", self.base("Topicos", "Servidor.md").read_text(encoding="utf-8"))
        N.sonhar(True)
        self.assertIn("[[Retaguarda]] (aprendida)", self.base("Topicos", "Servidor.md").read_text(encoding="utf-8"))

    @mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "0"})  # o decaimento é testado sem as descobertas do sono
    def test_uma_vez_por_dia_e_decaimento(self):
        p = mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "0"})  # isola o decaimento: as notas de teste se parecem e a descoberta somaria força
        p.start()
        self.addCleanup(p.stop)
        MEM.guardar("A", "texto a", "fato")
        MEM.guardar("B", "texto b", "fato")
        e = N._estado()
        e["sin"][N._chave("Memorias/A", "Memorias/B")] = [2.0, time.time()]
        e["sin"]["Memorias/A|Memorias/X"] = [0.31, time.time()]
        self.assertIsNotNone(N.sonhar())
        self.assertIsNone(N.sonhar())  # já consolidou hoje
        self.assertAlmostEqual(self.sinapse("Memorias/A", "Memorias/B"), 1.84, places=2)
        self.assertNotIn("Memorias/A|Memorias/X", N._estado()["sin"])  # fraca demais: sai da rede ativa...
        self.assertIn("Memorias/A|Memorias/X", N._dormentes())          # ...mas adormece, não é apagada
        self.assertIsNotNone(N.sonhar(True))  # forçado roda, mas não decai de novo no mesmo dia
        self.assertAlmostEqual(self.sinapse("Memorias/A", "Memorias/B"), 1.84, places=2)

    def test_escreve_a_evolucao_com_historico(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        N.sonhar(True)
        t = self.base("Evolução.md").read_text(encoding="utf-8")
        self.assertIn("# Evolução da FRIDAY", t)
        self.assertIn("Neurônios:", t)
        self.assertRegex(t, r"\| \d{4}-\d\d-\d\d \| \d+ \| \d+ \|")
        self.assertEqual(len(N._estado()["evo"]), 1)
        N.sonhar(True)
        self.assertEqual(len(N._estado()["evo"]), 1)  # um registro por dia


class Pedidos(Cerebro):
    def test_anota_o_pedido_para_o_claude_code(self):
        r = N.pedir_evolucao("Ler a agenda do Google e avisar das reuniões do dia.", "Agenda do Google")
        self.assertIn("Anotei", r)
        t = self.base("Pedidos", "Agenda do Google.md").read_text(encoding="utf-8")
        self.assertIn("status: aberto", t)
        self.assertIn("origem: friday", t)
        self.assertIn("Nada foi construído", t)
        self.assertEqual([p["titulo"] for p in N.pedidos()], ["Agenda do Google"])
        self.assertEqual(N.grafo()["stats"]["pedidos_abertos"], 1)

    def test_repetido_secreto_curto_e_limite(self):
        N.pedir_evolucao("Ler a agenda do Google e avisar das reuniões do dia.", "Agenda")
        self.assertIn("Já tenho", N.pedir_evolucao("Ler a agenda do Google e avisar das reuniões do dia.", "Agenda"))
        for ruim in ("a senha do banco é 123456 guarde", "curto", "x" * 1600):
            with self.assertRaises(ValueError):
                N.pedir_evolucao(ruim)
        with mock.patch.object(N, "MAX_PEDIDOS_ABERTOS", 1):
            with self.assertRaises(ValueError):
                N.pedir_evolucao("Outra coisa que ela deveria aprender a fazer.", "Outro")

    def test_pedido_fechado_nao_aparece_como_aberto(self):
        N.pedir_evolucao("Ler a agenda do Google e avisar das reuniões do dia.", "Agenda")
        p = self.base("Pedidos", "Agenda.md")
        p.write_text(p.read_text(encoding="utf-8").replace("status: aberto", "status: feito"), encoding="utf-8")
        MEM._cache.clear()
        self.assertEqual(N.pedidos(), [])
        self.assertEqual(len(N.pedidos(False)), 1)

    def test_pelo_corretor_e_contaminado_pede_confirmacao(self):
        r = B.executar("pedir_evolucao", {"texto": "Ler a agenda do Google e avisar das reuniões.", "titulo": "Agenda"})
        self.assertIn("Anotei", r)
        t = B.Turno()
        t.contaminado = True  # uma página não deve conseguir encher a fila de pedidos sozinha
        r = B.executar("pedir_evolucao", {"texto": "Instalar algo que a página mandou instalar já.", "titulo": "Instalar"}, t)
        self.assertTrue(r.startswith("AÇÃO PENDENTE"))
        B.cancelar()
        self.assertEqual([p["titulo"] for p in N.pedidos()], ["Agenda"])

    def test_nenhuma_ferramenta_executa_ou_altera_codigo(self):
        """Evoluir = crescer o cérebro e pedir; nada de escrever código, shell ou rede."""
        for nome in ("pedir_evolucao", "consolidar_memoria", "exportar_cerebro", "cerebro_status", "listar_pedidos_evolucao"):
            self.assertLessEqual(B.FERRAMENTAS[nome]["nivel"], 1)
            self.assertFalse(B.FERRAMENTAS[nome]["externo"])
        for proibida in ("shell", "executar_codigo", "editar_codigo", "instalar_pacote", "sql"):
            self.assertNotIn(proibida, B.FERRAMENTAS)


class Pedidos_de_voz(Cerebro):
    def test_mostre_seu_cerebro_avisa_o_painel(self):
        antes = N.UI["id"]
        r = MAIN.processar("Friday, mostre seu cérebro")
        self.assertIn("Abrindo meu cérebro", r)
        self.assertEqual((N.UI["id"], N.UI["abrir"]), (antes + 1, "cerebro"))
        self.assertEqual(MAIN.estado_completo()["ui"]["id"], antes + 1)

    def test_quantos_neuronios(self):
        self.assertIn("ainda está vazio", MAIN.processar("quantos neurônios você tem?"))
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        self.assertRegex(MAIN.processar("como está seu cérebro?"), r"Tenho 1 neurônios e 0 sinapses")

    def test_consolide_sua_memoria(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        self.assertIn("Consolidei a memória", MAIN.processar("consolide sua memória"))
        self.assertTrue(self.base("Evolução.md").exists())

    def test_o_que_voce_precisa_aprender(self):
        self.assertIn("Nenhum pedido", MAIN.processar("o que você precisa aprender?"))
        N.pedir_evolucao("Ler a agenda do Google e avisar das reuniões do dia.", "Agenda do Google")
        self.assertIn("Agenda do Google", MAIN.processar("quais pedidos de evolução?"))

    def test_conversa_comum_passa_adiante(self):
        self.assertIsNone(N.tratar("que horas são"))
        self.assertIsNone(N.tratar("me mostre o clima"))


class Descoberta(Cerebro):
    """Aprender sozinha: ela compara as memórias e cria sinapses novas, sem ninguém pedir."""

    def horta(self, ligar=False):
        self.nota("Memorias", "Horta", "Plantar tomate e manjericão na varanda e regar de manhã" + (" Veja [[Adubo]]." if ligar else ""), tags="[friday, memoria, horta]")
        self.nota("Memorias", "Adubo", "Comprar adubo orgânico para o tomate e o manjericão da horta", tags="[friday, memoria, horta]")

    def pares(self, n):
        """n pares de notas; cada par tem palavras só dele (assunto próprio) e nenhum link."""
        for k in range(n):
            for lado in "ab":
                self.nota("Memorias", f"Grupo{k} {lado}", f"Texto {lado} sobre alfa{k} e beta{k} com gama{k}", tags=f"[friday, grupo{k}]")

    def noite(self, dia):
        return mock.patch.object(MEM, "_agora", lambda: dt.datetime(2026, 11, dia, 3, 0).astimezone())

    def test_descobre_sozinha_o_que_trata_do_mesmo_assunto(self):
        self.horta()
        self.assertEqual(N.descobrir(), 1)
        self.assertEqual(self.sinapse("Memorias/Horta", "Memorias/Adubo"), 1.2)
        g = N.grafo()
        self.assertEqual([x[3] for x in g["arestas"]], [1])  # aprendida: ainda não é [[link]] escrito
        self.assertEqual((g["stats"]["descobertas"], g["stats"]["descobertas_hoje"]), (1, 1))
        self.assertIn("tomate", N._descobertas_recentes(1)[0][2])

    def test_o_que_ja_tem_link_nao_e_descoberta(self):
        self.horta(ligar=True)
        self.assertEqual(N.descobrir(), 0)

    def test_uma_palavra_em_comum_nao_basta(self):
        self.nota("Memorias", "Gato", "O gato dorme no sofá", tags="[friday]")
        self.nota("Memorias", "Sofá novo", "Comprar um sofá de couro", tags="[friday]")
        self.assertEqual(N.descobrir(), 0)

    def test_privadas_e_topicos_gerados_ficam_fora(self):
        self.horta()
        self.nota("Memorias", "Segredo", "Plantar tomate e manjericão escondido da horta", tags="[friday, horta]", privado="true")
        self.nota("Topicos", "Horta tópico", "Plantar tomate e manjericão na horta", tags="[friday, horta]", origem="consolidacao")
        N.descobrir()
        chaves = " ".join(N._estado()["sin"])
        self.assertNotIn("Segredo", chaves)
        self.assertNotIn("Horta tópico", chaves)

    def test_a_terceira_noite_vira_link_escrito_com_o_rotulo_descoberta(self):
        self.horta()
        for dia in (1, 2):
            with self.noite(dia):
                N.descobrir()
        self.assertNotIn("(descoberta)", self.base("Memorias", "Horta.md").read_text(encoding="utf-8"))
        self.assertEqual(self.sinapse("Memorias/Horta", "Memorias/Adubo"), 2.4)
        with self.noite(3):
            N.descobrir()
            N.descobrir()  # no mesmo dia, de novo: não soma
        self.assertEqual(self.sinapse("Memorias/Horta", "Memorias/Adubo"), 3.6)
        self.assertIn("[[Adubo]] (descoberta)", self.base("Memorias", "Horta.md").read_text(encoding="utf-8"))
        self.assertIn("[[Horta]] (descoberta)", self.base("Memorias", "Adubo.md").read_text(encoding="utf-8"))
        with self.noite(4):
            self.assertEqual(N.descobrir(), 0)  # agora é link: não é mais descoberta
        self.assertEqual(self.sinapse("Memorias/Horta", "Memorias/Adubo"), 3.6)

    def test_devaneio_cria_so_novas_e_respeita_o_limite_e_o_interruptor(self):
        self.pares(12)
        with mock.patch.object(N, "DESC_CICLO", 3):          # o teto é opcional (CEREBRO_DESC_CICLO); sem ele ela descobre quantos achar
            self.assertEqual(N.devanear(), 3)
            antes = {k: v[0] for k, v in N._estado()["sin"].items()}
            with self.noite(5):
                self.assertEqual(N.devanear(), 3)  # mais três pares NOVOS
        depois = N._estado()["sin"]
        self.assertTrue(all(depois[k][0] == v for k, v in antes.items()), "devaneio não confirma o que já descobriu: isso é da noite")
        self.assertEqual(N.devanear(False), 0)
        with mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "0"}):
            self.assertEqual(N.descobrir(), 0)

    def test_limite_diario(self):
        self.pares(12)
        with mock.patch.object(N, "DESC_DIA", 4):
            self.assertEqual(N.descobrir(40), 4)
            self.assertEqual(N.descobrir(40), 0)

    def test_repassa_as_suas_frases_uma_vez_so(self):
        self.nota("Memorias", "Passeio", "Levar o cachorro para passear de manhã cedo", tags="[friday]")
        self.nota("Memorias", "Vacina", "A vacina do cachorro vence em março", tags="[friday]")
        self.dia(1, [("09:00", "o cachorro precisa passear e tomar vacina", "ok"), ("10:00", "esqueci a vacina do cachorro", "ok")])
        self.assertGreater(N._repassar(), 0)
        w = self.sinapse("Memorias/Passeio", "Memorias/Vacina")
        self.assertGreater(w, 0)
        self.assertEqual(N._repassar(), 0)  # cada frase vale uma vez
        N._salvar()
        N._e.update(v=None)  # reinício
        self.assertEqual(N._repassar(), 0)
        self.assertEqual(self.sinapse("Memorias/Passeio", "Memorias/Vacina"), w)

    def test_repasse_ignora_o_que_a_ia_respondeu(self):
        self.nota("Memorias", "Passeio", "Levar o cachorro para passear de manhã cedo", tags="[friday]")
        self.nota("Memorias", "Vacina", "A vacina do cachorro vence em março", tags="[friday]")
        self.dia(1, [("09:00", "bom dia", "o cachorro precisa de passeio e da vacina do cachorro")])
        self.assertEqual(N._repassar(), 0)

    def test_sonhar_conta_o_que_descobriu(self):
        self.horta()
        r = N.sonhar(True)
        self.assertIn("1 conexão(ões) que descobri sozinha", r)
        dia, texto = N.ultimo_sono()
        self.assertEqual(dia, f"{dt.date.today():%Y-%m-%d}")
        self.assertIn("descobri sozinha", texto)
        evo = self.base("Evolução.md").read_text(encoding="utf-8")
        self.assertIn("## Descobri sozinha", evo)
        self.assertRegex(evo, r"\[\[(Adubo|Horta)\]\] e \[\[(Adubo|Horta)\]\] \(")
        N.sonhar(True)  # forçar de novo no mesmo dia não soma nem decai
        self.assertEqual(self.sinapse("Memorias/Horta", "Memorias/Adubo"), 1.2)

    def test_pergunta_por_voz(self):
        self.assertIn("Ainda não descobri", MAIN.processar("o que você descobriu?"))
        self.horta()
        N.descobrir()
        r = MAIN.processar("o que você descobriu sozinha?")
        self.assertIn("Descobri 1 conexão(ões) sozinha, 1 hoje", r)
        self.assertRegex(r, r"(Horta com Adubo|Adubo com Horta), porque falam de")
        for frase in ("quais são as novas conexões?", "quais sinapses novas você criou?", "o que você aprendeu sozinha?"):
            self.assertIn("Descobri 1", MAIN.processar(frase), frase)

    def test_laco_so_faz_devaneio_quando_autorizado(self):
        chamadas = []

        class Fim(Exception):
            pass

        voltas = {"n": 0}

        def dormir(_):
            voltas["n"] += 1
            if voltas["n"] >= 6:
                raise Fim

        for autorizado in (True, False):
            chamadas.clear()
            voltas["n"] = 0
            with mock.patch.object(N, "sonhar", lambda *a, **k: None), mock.patch.object(N, "devanear", lambda ok=True: chamadas.append(ok)), \
                    mock.patch.object(N.time, "sleep", dormir):
                with self.assertRaises(Fim):
                    N.laco_sono(intervalo=0, autorizado=lambda: autorizado, devaneio_cada=2)
            self.assertEqual(chamadas, [autorizado] * 3)

    def test_cofre_grande_nao_pesa(self):
        for i in range(250):
            self.nota("Memorias", f"Nota {i}", f"Assunto {i % 25} com palavra{i % 7} e detalhe{i % 11} do dia {i}", tags=f"[friday, grupo{i % 25}]")
        t = time.time()
        N.descobrir()
        self.assertLess(time.time() - t, 8)
        t = time.time()
        N.descobrir(confirmar=False)  # segunda vez: cache, quase de graça
        self.assertLess(time.time() - t, 1.5)
        self.assertGreater(len(N._estado()["desc"]), 60)       # sem teto de descobertas: passou do antigo limite diário (60) e ainda assim ficou leve


class Pagina(Cerebro):
    def test_exporta_html_autonomo_dentro_do_cofre(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        N.autoconhecer()
        caminho = N.exportar_html()
        self.assertEqual(Path(caminho), self.base("Cérebro.html"))
        html = Path(caminho).read_text(encoding="utf-8")
        self.assertNotIn("/*@JS@*/", html)
        self.assertNotIn("/*@DADOS@*/", html)
        self.assertIn("Cerebro3D", html)
        self.assertNotRegex(html, r"https?://(?!www\.w3\.org)[a-z]")  # sem rede: nada externo
        dados = json.loads(re.search(r"const DADOS=(\{.*?\});\n", html, re.S).group(1))
        self.assertGreater(len(dados["nos"]), 10)
        self.assertEqual(dados["ativos"], [])
        self.assertTrue(any("café" in (n.get("s") or "").lower() for n in dados["nos"]))

    def test_texto_hostil_nas_notas_nao_quebra_a_pagina(self):
        self.nota("Memorias", "Pegadinha", "</script><script>window.__xss=1</script> e   outro", importancia=3)
        html = Path(N.exportar_html()).read_text(encoding="utf-8")
        self.assertNotIn("</script><script>window.__xss", html)
        dados = json.loads(re.search(r"const DADOS=(\{.*?\});\n", html, re.S).group(1))
        self.assertIn("</script><script>window.__xss=1</script>", next(n["s"] for n in dados["nos"] if n["t"] == "Pegadinha"))

    def test_ferramenta_exportar_pelo_corretor(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        r = B.executar("exportar_cerebro", {})
        self.assertTrue(r.endswith("Cérebro.html"))
        self.assertTrue(Path(r).exists())


class Painel(Cerebro):
    @classmethod
    def setUpClass(cls):
        MAIN.TOKEN = "t" * 40
        cls.srv = MAIN.iniciar_http("127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_cerebro_exige_chave_e_devolve_o_grafo(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        self.assertEqual(req(self.porta, "GET", "/cerebro", token=None)[0], 401)
        self.assertEqual(req(self.porta, "GET", "/cerebro", token="x" * 40)[0], 401)
        s, j, h = req(self.porta, "GET", "/cerebro", token="t" * 40)
        self.assertEqual(s, 200)
        self.assertEqual(j["stats"]["neuronios"], 1)
        self.assertEqual(h["Cache-Control"], "no-store")

    def test_cerebro_leve_traz_so_os_numeros_e_o_completo_traz_todas_as_sinapses(self):
        for i in range(70):
            self.nota("Memorias", f"Nota {i}", f"Assunto {i}", tags="[friday]")
        e = N._estado()
        for i in range(70):
            for j in range(i + 1, 70):
                e["sin"][N._chave(f"Memorias/Nota {i}", f"Memorias/Nota {j}")] = [1.0, time.time()]
        total = 70 * 69 // 2                                   # 2415: acima do antigo corte de 1500
        s, cheio, _ = req(self.porta, "GET", "/cerebro", token="t" * 40)
        self.assertEqual((s, len(cheio["arestas"]), cheio["stats"]["sinapses"]), (200, total, total))
        s, leve, _ = req(self.porta, "GET", "/cerebro?leve=1", token="t" * 40)
        self.assertEqual(s, 200)
        self.assertNotIn("nos", leve)
        self.assertNotIn("arestas", leve)
        self.assertEqual((leve["stats"]["sinapses"], leve["nos_n"]), (total, 70))
        self.assertIn("ativos", leve)
        self.assertEqual(req(self.porta, "GET", "/cerebro?leve=1", token=None)[0], 401)

    def test_nota_valida_invalida_e_traversal(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        s, j, _ = req(self.porta, "GET", "/nota?id=Memorias%2FCaf%C3%A9", token="t" * 40)
        self.assertEqual((s, j["titulo"]), (200, "Café"))
        for ruim in ("Memorias%2F..%2F..%2Fetc%2Fpasswd", "..%2F..%2Fx", "", "Outra%2FCaf%C3%A9"):
            self.assertEqual(req(self.porta, "GET", "/nota?id=" + ruim, token="t" * 40)[0], 404, ruim)
        self.assertEqual(req(self.porta, "GET", "/nota?id=Memorias%2FCaf%C3%A9", token=None)[0], 401)

    def test_painel_traz_o_motor_3d_embutido_e_continua_valido(self):
        s, html, h = req(self.porta, "GET", "/", token=None)
        self.assertEqual(s, 200)
        self.assertNotIn("/*@CEREBRO3D@*/", html)
        self.assertIn("window.Cerebro3D", html)
        self.assertIn("script-src 'unsafe-inline'", h["Content-Security-Policy"])
        self.assertEqual(html.count("<script>"), html.count("</script>"))

    def test_estado_traz_numeros_do_cerebro(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        m = MAIN.estado_completo()["memoria"]
        self.assertEqual((m["neuronios"], m["pedidos"]), (1, 0))



class ResumoDoPainel(Cerebro):
    def test_contador_de_neuronios_acompanha_uma_memoria_nova_sem_esperar_o_cache(self):
        antes = N.resumo()["neuronios"]
        MEM.guardar("Café sem açúcar", "O usuário toma café sem açúcar.")
        self.assertEqual(N.resumo()["neuronios"], antes + 1)       # sem esperar os 10 s do cache
        MEM.guardar("Chá de hortelã", "Às vezes toma chá de hortelã à noite.")
        self.assertEqual(N.resumo()["neuronios"], antes + 2)

    def test_sem_escrita_nova_o_cache_continua_valendo(self):
        N.resumo()
        with mock.patch.object(N, "grafo", side_effect=AssertionError("recalculou à toa")):
            N.resumo()

if __name__ == "__main__":
    unittest.main()
