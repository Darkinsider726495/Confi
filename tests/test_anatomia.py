import os, re, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import anatomia as AN, neuronios as N, memoria as MEM
from test_neuronios import Cerebro

AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, "..", "friday", "cerebro3d.js"), encoding="utf-8") as _f:
    JS = _f.read()


class Tabela(unittest.TestCase):
    def test_toda_regiao_tem_o_que_a_pagina_diz_e_o_que_ela_e_na_friday(self):
        self.assertEqual(set(AN.ORDEM), set(AN.REGIOES))
        for k, r in AN.REGIOES.items():
            for campo in ("nome", "ufes", "friday", "cor", "pos", "lado", "modulos"):
                self.assertIn(campo, r, f"{k} sem {campo}")
            self.assertGreaterEqual(len(r["ufes"]), 4, k)
            self.assertGreater(len(r["friday"]), 20, k)
            self.assertEqual(len(r["cor"]), 3)
            self.assertTrue(all(isinstance(c, int) and 0 <= c <= 255 for c in r["cor"]), k)
            self.assertEqual(len(r["pos"]), 3)

    def test_cores_das_regioes_sao_todas_diferentes(self):
        cores = [tuple(r["cor"]) for r in AN.REGIOES.values()]
        self.assertEqual(len(set(cores)), len(cores))

    def test_o_motor_3d_usa_a_mesma_ordem_de_regioes(self):
        m = re.search(r"const ORD_REG = \[([^\]]*)\]", JS)
        self.assertTrue(m)
        self.assertEqual(re.findall(r"'(\w+)'", m.group(1)), AN.ORDEM)

    def test_o_que_nao_esta_na_pagina_nao_vira_regiao(self):
        # a página da UFES não cita estas estruturas: não podem aparecer como se fossem dela
        proibidas = {"talamo", "hipotalamo", "amigdala", "ganglios da base", "sono"}
        for k, r in AN.REGIOES.items():
            self.assertNotIn(AN._dobrar(r["nome"]), proibidas, k)
            self.assertNotIn(k, proibidas)
            for p in proibidas:
                self.assertNotIn(p, AN._dobrar(r["ufes"]), f"{k}: «{r['ufes']}»")

    def test_cada_ancora_esta_dentro_da_forma_do_cerebro(self):
        """O motor desenha dois elipsoides (hemisférios), um cerebelo e um tronco: o centro de cada região tem de cair em algum deles."""
        def hemisferio(x, y, z):
            z = abs(z)
            return (x / .98) ** 2 + ((y + .05) / .70) ** 2 + ((z - .33) / .36) ** 2 <= 1
        def cerebelo(x, y, z):
            return ((x + .58) / .26) ** 2 + ((y - .55) / .17) ** 2 + (z / .30) ** 2 <= 1.15
        def tronco(x, y, z):
            t = (y - .35) / .60
            return -.02 <= t <= 1.02 and abs(x - (-.05 - .18 * t)) <= .14 and abs(z) <= .12
        for k, r in AN.REGIOES.items():
            x, y, z = r["pos"]
            self.assertTrue(hemisferio(x, y, z) or cerebelo(x, y, z) or tronco(x, y, z), f"{k} {r['pos']} fora do cérebro")
        # regiões de linha média não têm lado; as demais têm os dois
        self.assertFalse(AN.REGIOES["tronco"]["lado"])
        self.assertFalse(AN.REGIOES["mesencefalo"]["lado"])
        self.assertTrue(AN.REGIOES["frontal"]["lado"])

    def test_sistemas_citados_na_pagina_nao_sao_regioes_mas_mecanismos(self):
        for k in ("corpo_caloso", "autonomo", "sensorial", "plasticidade", "neurotransmissores"):
            self.assertIn(k, AN.SISTEMAS)
            self.assertNotIn(k, AN.REGIOES)
        self.assertIn("A página não diz o papel de cada um", AN.SISTEMAS["neurotransmissores"]["friday"])


class Mapa(unittest.TestCase):
    def test_tipo_de_memoria_vai_para_a_regiao_certa(self):
        casos = {"decisao": "frontal", "projeto": "frontal", "tarefa": "frontal", "pedido": "frontal", "fato": "temporal", "topico": "temporal",
                 "estudo": "parietal", "conversa": "hipocampo", "pessoa": "limbico", "preferencia": "limbico"}
        for g, r in casos.items():
            self.assertEqual(AN.regiao_de(g, "qualquer"), r, g)

    def test_grupo_desconhecido_cai_no_temporal_e_nunca_levanta(self):
        for g in ("", "xyz", None, 7):
            self.assertIn(AN.regiao_de(g, "t"), AN.REGIOES)

    def test_autoconhecimento_vai_pela_natureza_da_nota(self):
        r = lambda t: AN.regiao_de("eu", t, AN.regioes_das_ferramentas(B.FERRAMENTAS))
        self.assertEqual(r("FRIDAY (eu)"), "tronco")
        self.assertEqual(r("Regras de segurança"), "tronco")
        self.assertEqual(r("Memória e cérebro"), "hipocampo")
        self.assertEqual(r("Voz e sentidos"), "mesencefalo")
        self.assertEqual(r("Protocolos"), "cerebelo")
        self.assertEqual(r("protocolo noite"), "cerebelo")
        self.assertEqual(r("Autonomia e rotinas"), "cerebelo")
        self.assertEqual(r("Pedidos de evolução"), "frontal")
        self.assertEqual(r("Sentidos (nível 0)"), "parietal")
        self.assertEqual(r("Ações com confirmação (nível 2)"), "cortex_motor")
        self.assertEqual(r("Regiões do cérebro"), "tronco")
        self.assertEqual(r("Vida e humor"), "limbico")
        self.assertEqual(r("nota que não conheço"), "tronco")

    def test_ferramentas_caem_onde_a_natureza_delas_manda(self):
        m = AN.regioes_das_ferramentas(B.FERRAMENTAS)
        r = lambda n: m["ferramenta " + n.replace("_", " ")]
        self.assertEqual(r("pesquisar_web"), "parietal")
        self.assertEqual(r("localizacao"), "parietal")     # sente o mundo, mesmo sendo nível 1
        self.assertEqual(r("lembrar"), "temporal")
        self.assertEqual(r("guardar_memoria"), "hipocampo")
        self.assertEqual(r("criar_lembrete"), "frontal")
        self.assertEqual(r("listar_protocolos"), "cerebelo")
        self.assertEqual(r("enviar_sms"), "cortex_motor")
        self.assertEqual(r("rele"), "cortex_motor")

    def test_toda_ferramenta_registrada_tem_regiao_valida(self):
        m = AN.regioes_das_ferramentas(B.FERRAMENTAS)
        self.assertEqual(len(m), len(B.FERRAMENTAS))
        self.assertTrue(set(m.values()) <= set(AN.REGIOES))
        for nome in AN._POR_FERRAMENTA:
            self.assertIn(nome, B.FERRAMENTAS, f"a tabela cita «{nome}», que não existe mais")

    def test_ferramenta_nova_sem_lugar_na_tabela_cai_pelo_nivel(self):
        falsas = {"ver_algo": {"nivel": 0}, "mexer_algo": {"nivel": 2}, "var": {"nivel": lambda a: 1}}
        m = AN.regioes_das_ferramentas(falsas)
        self.assertEqual(m["ferramenta ver algo"], "parietal")
        self.assertEqual(m["ferramenta mexer algo"], "cortex_motor")
        self.assertEqual(m["ferramenta var"], "cortex_motor")

    def test_o_occipital_e_o_lugar_da_visao_e_so_dela(self):
        # só as coisas que ela aprendeu a ver e a nota de autoconhecimento da visão caem no lobo occipital; nenhuma ferramenta (a câmera não é ferramenta da IA)
        self.assertEqual({k for k, v in AN._TIPO_PARA_REGIAO.items() if v == "occipital"}, {"visao"})
        self.assertEqual({k for k, v in AN._EU_FIXAS.items() if v == "occipital"}, {"visao e lobo occipital"})
        self.assertNotIn("occipital", set(AN._POR_FERRAMENTA.values()))
        self.assertEqual(AN.regiao_de("visao", "Caneca (visão)"), "occipital")


class Fala(unittest.TestCase):
    def test_resumo_falado_cita_as_mais_povoadas_e_a_regiao_vazia(self):
        c = {k: 0 for k in AN.REGIOES}
        c.update(frontal=9, hipocampo=5, temporal=2)
        t = AN.falar(c, {"hipocampo": 40, "frontal": 3})
        self.assertIn("lobo frontal com 9", t)
        self.assertIn("hipocampo com 5", t)
        self.assertIn("A que mais uso é o hipocampo", t)
        self.assertIn("lobo occipital está vazio", t)

    def test_sem_neuronios_ela_diz_que_ainda_nao_tem_nenhum(self):
        self.assertIn("Ainda não tenho neurônios", AN.falar({k: 0 for k in AN.REGIOES}))

    def test_descrever_cada_regiao_e_sistema_por_varios_nomes(self):
        for k, r in AN.REGIOES.items():
            for nome in (k, r["nome"], r["nome"].lower()):
                t = AN.descrever(nome)
                self.assertTrue(t and "UFES" in t and r["friday"] in t, nome)
        for k, v in AN.SISTEMAS.items():
            self.assertTrue(AN.descrever(v["nome"]), k)
        self.assertTrue(AN.descrever("frontal").startswith("Lobo frontal"))
        self.assertIsNone(AN.descrever("amígdala"))   # a página não cita: ela não inventa
        self.assertIsNone(AN.descrever("talamo"))

    def test_perguntas_por_voz(self):
        f = MEM._fold
        self.assertTrue(AN.eh_lista(f("Quais são as suas regiões do cérebro")))
        self.assertTrue(AN.eh_lista(f("como é seu cérebro por dentro")))
        self.assertFalse(AN.eh_lista(f("quais são as regiões do Brasil")))
        self.assertIn("UFES", AN.eh_pergunta_de_regiao(f("o que é o hipocampo")))
        self.assertIn("UFES", AN.eh_pergunta_de_regiao(f("Friday, fale do cerebelo")))
        self.assertIsNone(AN.eh_pergunta_de_regiao(f("o que é isso")))
        self.assertIsNone(AN.eh_pergunta_de_regiao(f("o que é a amigdala")))


class NoGrafo(Cerebro):
    def populacao(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Mae", "Minha mãe se chama Ana", "pessoa")
        MEM.guardar("Café", "Gosto de café sem açúcar", "preferencia")
        MEM.guardar("Fato", "A capital do Brasil é Brasília", "fato")
        self.dia(0, [("09:00", "bom dia", "bom dia")])
        N.autoconhecer()

    def test_todo_neuronio_tem_uma_regiao_valida_e_as_contagens_batem(self):
        self.populacao()
        g = N.grafo()
        self.assertTrue(all(n["rg"] in AN.REGIOES for n in g["nos"]))
        c = g["stats"]["regioes"]
        self.assertEqual(sum(c.values()), g["stats"]["neuronios"])
        self.assertEqual({k: v["n"] for k, v in g["regioes"].items()}, c)
        por = {n["t"]: n["rg"] for n in g["nos"]}
        self.assertEqual(por["Servidor"], "frontal")
        self.assertEqual(por["Mae"], "limbico")
        self.assertEqual(por["Café"], "limbico")
        self.assertEqual(por["Fato"], "temporal")
        self.assertEqual(por["ferramenta pesquisar web"], "parietal")
        self.assertEqual(c["occipital"], 1)   # a nota de autoconhecimento «Visão e lobo occipital»; sem câmera ainda não há coisas vistas

    def test_o_grafo_inclui_o_mapa_das_regioes_para_o_3d(self):
        self.populacao()
        g = N.grafo()
        self.assertEqual(set(g["regioes"]), set(AN.REGIOES))
        self.assertEqual(g["regioes"]["frontal"]["pos"], AN.REGIOES["frontal"]["pos"])
        self.assertEqual(set(N.grafo()["regioes"]), set(AN.REGIOES))
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            off = N.grafo()
            self.assertFalse(off["ativo"])
            self.assertEqual(set(off["regioes"]), set(AN.REGIOES))

    def test_nota_privada_nao_ganha_regiao_porque_nem_entra_no_grafo(self):
        self.nota("Memorias", "Segredo", "isso é meu", privado="true")
        self.assertNotIn("Segredo", [n["t"] for n in N.grafo()["nos"]])

    def test_a_pasta_eu_ganha_as_notas_de_regioes_e_vida_ligadas_ao_hub(self):
        N.autoconhecer()
        t = self.base("Eu", "Regiões do cérebro.md").read_text(encoding="utf-8")
        self.assertIn("UFES", t)
        self.assertIn("[[FRIDAY (eu)]]", t)
        self.assertIn("não é consciência nem biologia", t)
        for r in AN.REGIOES.values():
            self.assertIn(r["nome"], t)
        self.assertIn("[[Regiões do cérebro]]", self.base("Eu", "FRIDAY (eu).md").read_text(encoding="utf-8"))
        self.assertIn("[[Vida e humor]]", self.base("Eu", "FRIDAY (eu).md").read_text(encoding="utf-8"))

    def test_uso_por_regiao_mostra_onde_ela_mais_pensa(self):
        self.populacao()
        MEM.lembrar("servidor ollama")
        MEM.lembrar("servidor ollama casa")
        u = N.usos_por_regiao()
        self.assertGreater(u.get("frontal", 0), 0)
        self.assertEqual(u.get("limbico", 0), 0)

    def test_comandos_de_voz(self):
        self.populacao()
        self.assertIn("regiões", N.tratar("Quais são as suas regiões?"))
        self.assertIn("regiões", N.tratar("me fale das suas regiões do cérebro"))
        self.assertIn("UFES", N.tratar("o que é o hipocampo?"))
        self.assertIn("UFES", N.tratar("o que é o corpo caloso"))
        self.assertIsNone(N.tratar("o que é a amígdala?"))
        self.assertIsNone(N.tratar("o que é a capital da França"))

    def test_nota_publica_traz_a_regiao(self):
        self.populacao()
        self.assertEqual(N.nota_publica("Memorias/Servidor")["regiao"], "frontal")

    def test_export_html_leva_as_regioes_e_o_botao(self):
        self.populacao()
        with open(N.exportar_html(os.path.join(self.dir, "c.html")), encoding="utf-8") as f:
            h = f.read()
        self.assertIn('"regioes"', h)
        self.assertIn('"rg": "frontal"', h)
        self.assertIn('id="bm"', h)
        self.assertIn("C.legenda()", h)


if __name__ == "__main__":
    unittest.main()
