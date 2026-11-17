"""Fase 1.1 — a busca não pode esquecer memória só porque o cofre cresceu.

Antes: a varredura parava em 3.000 arquivos, em ordem alfabética, somando todas as pastas. Notas "no fim do alfabeto" e as conversas
mais recentes (Conversas vem por último e os arquivos são AAAA-MM-DD) sumiam da busca, do contexto do prompt, de "o que sei sobre você"
e do filtro de nomes de pessoas. Agora a varredura vai até o fim; quem quiser um teto define CEREBRO_MAX_ARQUIVOS (fica o mais recente).
"""
import os, shutil, tempfile, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import memoria as MEM, curiosidade as CUR

T0 = 1_792_000_000.0          # "agora" fixo dos testes de pontuação (outubro de 2026)
DIA = 86400.0


def escrever(pasta, nome, texto, antiguidade_dias=0.0, **meta):
    d = MEM.base() / pasta
    d.mkdir(parents=True, exist_ok=True)
    m = {"tipo": "fato", "importancia": 3, **meta} if pasta != "Conversas" else None
    f = d / f"{nome}.md"
    f.write_text(MEM._montar(m, texto) if m else texto, encoding="utf-8")
    t = T0 - antiguidade_dias * DIA
    os.utime(f, (t, t))
    return f


class Base(unittest.TestCase):
    def prepara_cofre(self):
        self.dir = tempfile.mkdtemp(prefix="cofre-vol-", dir=E.TMP)
        p = mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": self.dir})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        MEM._cache.clear()


class CofreGrande(unittest.TestCase):
    """3.300 notas num cofre só (criado uma vez): as especiais ficam DEPOIS da posição 3.000 na ordem alfabética."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="cofre-grande-", dir=E.TMP)
        cls._env = mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": cls.dir})
        cls._env.start()
        MEM._cache.clear()
        d = MEM.base() / "Memorias"
        d.mkdir(parents=True)
        cab = "---\ntipo: fato\nimportancia: 3\n---\n"
        for i in range(3300):
            (d / f"Nota {i:05d}.md").write_text(f"{cab}assunto comum de enchimento número {i}\n", encoding="utf-8")
        (d / "Zzz Agulha.md").write_text(f"{cab}a palavra rara é zeppelinomega\n", encoding="utf-8")
        (d / "Zzz Essencial.md").write_text("---\ntipo: fato\nimportancia: 5\n---\nnunca esquecer o aniversário da vovó\n", encoding="utf-8")
        (d / "Zzz Zeferino Quintanilha.md").write_text("---\ntipo: pessoa\nimportancia: 3\n---\nvizinho do andar de cima\n", encoding="utf-8")
        c = MEM.base() / "Conversas"
        c.mkdir()
        (c / "2026-10-23.md").write_text("# 2026-10-23\n\n- 10:00 **Você**: combinei a viagem para tangerinaquantica\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        shutil.rmtree(cls.dir, True)
        MEM._cache.clear()

    def setUp(self):
        MEM._cache.clear()
        CUR._cache_nomes.update(t=0.0, v=frozenset(), base=None)

    def test_nota_depois_do_antigo_teto_e_encontrada(self):
        r = MEM.buscar("zeppelinomega", 3)
        self.assertEqual([x["titulo"] for x in r], ["Zzz Agulha"])

    def test_conversa_recente_nao_some_quando_as_memorias_enchem_o_teto(self):
        r = MEM.buscar("tangerinaquantica", 3)
        self.assertEqual([(x["origem"], x["titulo"]) for x in r], [("Conversas", "2026-10-23")])

    def test_essencial_depois_do_teto_entra_no_contexto_do_prompt(self):
        bloco, _ = MEM.contexto_completo("qualquer coisa sem relação")
        self.assertIn("[essencial] Zzz Essencial", bloco)

    def test_sobre_mim_enxerga_o_cofre_inteiro(self):
        # a nota de importância 5 está depois da posição 3.000; "o que sei sobre você" ordena por importância
        self.assertIn("Zzz Essencial", MEM.sobre_mim())

    def test_filtro_de_nomes_de_pessoas_inclui_notas_depois_do_teto(self):
        self.assertIn("quintanilha", CUR._nomes_de_pessoas())

    def test_nova_memoria_liga_a_nota_que_menciona_mesmo_depois_do_teto(self):
        self.assertIn("Zzz Agulha", MEM._relacionadas("falei sobre a zzz agulha de novo", "outra"))


class TetoDoDono(Base):
    """Quem tem aparelho fraco pode limitar (CEREBRO_MAX_ARQUIVOS); o que fica é o mais recente, não o início do alfabeto."""

    def test_teto_do_dono_mantem_o_mais_recente(self):
        self.prepara_cofre()
        for i in range(60):   # i=0 é a mais antiga, i=59 a mais nova; ordem alfabética = ordem de criação
            escrever("Memorias", f"Item {i:02d}", "assunto comum", antiguidade_dias=100 - i)
        with mock.patch.dict(os.environ, {"CEREBRO_MAX_ARQUIVOS": "20"}):
            titulos = {x["titulo"] for x in MEM.buscar("assunto comum", 100)}
        self.assertEqual(len(titulos), 20)
        self.assertIn("Item 59", titulos)
        self.assertNotIn("Item 00", titulos)

    def test_sem_variavel_nao_ha_teto(self):
        self.prepara_cofre()
        for i in range(120):
            escrever("Memorias", f"Item {i:03d}", "assunto comum", antiguidade_dias=i)
        with mock.patch.dict(os.environ, {"CEREBRO_MAX_ARQUIVOS": ""}):
            self.assertEqual(len(MEM.buscar("assunto comum", 500)), 120)

    def test_valor_invalido_vira_sem_teto(self):
        self.prepara_cofre()
        for i in range(30):
            escrever("Memorias", f"Item {i:03d}", "assunto comum", antiguidade_dias=i)
        for ruim in ("abc", "-5", "0"):
            with mock.patch.dict(os.environ, {"CEREBRO_MAX_ARQUIVOS": ruim}):
                self.assertEqual(len(MEM.buscar("assunto comum", 500)), 30, ruim)


class Cache(Base):
    def test_cache_e_limitado_sem_perder_resultado(self):
        self.prepara_cofre()
        for i in range(300):
            escrever("Memorias", f"Item {i:03d}", f"assunto comum numero{i}", antiguidade_dias=i % 50)
        with mock.patch.dict(os.environ, {"CEREBRO_CACHE_NOTAS": "100"}):
            for _ in range(3):
                achados = MEM.buscar("assunto comum", 500)
                self.assertEqual(len(achados), 300)
            self.assertLessEqual(len(MEM._cache), 100)   # o teto do dono (RAM) vale; a busca continua achando tudo, só relê mais
        MEM._cache.clear()
        with mock.patch.dict(os.environ, {"CEREBRO_CACHE_NOTAS": "100"}):
            for i in range(250):
                MEM._ler_nota(MEM.base() / "Memorias" / f"Item {i:03d}.md")
            self.assertLessEqual(len(MEM._cache), 100)

    def test_nota_editada_e_relida(self):
        self.prepara_cofre()
        f = escrever("Memorias", "Gato", "o gato se chama Luna", antiguidade_dias=1)
        self.assertEqual([x["titulo"] for x in MEM.buscar("luna", 3)], ["Gato"])
        f.write_text(MEM._montar({"tipo": "fato", "importancia": 3}, "o gato se chama Mel"), encoding="utf-8")
        os.utime(f, (T0, T0))
        self.assertEqual(MEM.buscar("luna", 3), [])
        self.assertEqual([x["titulo"] for x in MEM.buscar("mel", 3)], ["Gato"])

    def test_nota_apagada_por_fora_sai_da_busca(self):
        self.prepara_cofre()
        f = escrever("Memorias", "Gato", "o gato se chama Luna")
        self.assertTrue(MEM.buscar("luna", 3))
        os.replace(f, f.with_suffix(".bak"))     # o Obsidian moveu o arquivo
        self.assertEqual(MEM.buscar("luna", 3), [])


class CofreExterno(Base):
    """As SUAS outras notas (OBSIDIAN_LER_TUDO=1) continuam com teto, mas agora ele é anunciado em vez de silencioso."""

    def test_corte_do_cofre_externo_e_avisado(self):
        self.prepara_cofre()
        ext = Path(self.dir) / "Notas pessoais"
        ext.mkdir()
        for i in range(12):
            (ext / f"Ideia {i:02d}.md").write_text(f"ideia numero {i} sobre jardinagem\n", encoding="utf-8")
            os.utime(ext / f"Ideia {i:02d}.md", (T0 - i * DIA, T0 - i * DIA))
        with mock.patch.dict(os.environ, {"OBSIDIAN_LER_TUDO": "1"}), mock.patch.object(MEM, "MAX_COFRE_EXTERNO", 5):
            r = MEM.procurar_nas_notas("jardinagem")
        self.assertIn("olhei só as 5 notas mais recentes", r)
        self.assertIn("7 ficaram de fora", r)
        self.assertIn("Ideia 00", r)          # a mais recente entrou
        self.assertNotIn("Ideia 11", r)       # a mais antiga ficou de fora

    def test_sem_corte_sem_aviso(self):
        self.prepara_cofre()
        ext = Path(self.dir) / "Notas pessoais"
        ext.mkdir()
        (ext / "Ideia.md").write_text("ideia sobre jardinagem\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"OBSIDIAN_LER_TUDO": "1"}):
            r = MEM.procurar_nas_notas("jardinagem")
        self.assertIn("Ideia", r)
        self.assertNotIn("ficaram de fora", r)


# Pontuações medidas com o código ANTERIOR à refatoração (varredura e fórmula de relevância), relógio fixo em T0.
# A fórmula não mudou: este teste prova que guardar os termos em cache não altera nenhuma nota nem a ordem.
CONSULTAS_DOURADAS = [
    ("servidor hermes", dict()),
    ("gato luna", dict()),
    ("buracos negros", dict(estudos=True)),
    ("sala janela", dict(visao=True)),
    ("viagem praia", dict()),
    ("redes neurais", dict(ampliado=True)),
    ("projeto friday memoria", dict(ampliado=True, estudos=True, visao=True)),
    ("comum", dict(limite=10)),
    ("inexistente", dict()),
]
DOURADO = {
    "servidor hermes": [("Servidor de casa", 3.705)],
    "gato luna": [("Gato Luna", 3.264), ("2026-10-22", 0.564)],
    "buracos negros": [("Buracos negros", 1.845)],
    "sala janela": [("Gato Luna", 1.717), ("Sala", 1.083), ("2026-10-22", 0.497)],
    "viagem praia": [("Praia", 2.359), ("2026-10-20", 1.061)],
    "redes neurais": [("Redes neurais", 1.848), ("Perfil", 1.092)],
    "projeto friday memoria": [("Projeto Friday", 3.323), ("Gato Luna", 1.187), ("Redes neurais", 0.495)],
    "comum": [("Enchimento 4", 1.183), ("Enchimento 3", 1.044), ("Enchimento 2", 0.891), ("Enchimento 5", 0.814), ("Enchimento 1", 0.712), ("Enchimento 0", 0.47)],
    "inexistente": [],
}


def corpus_dourado():
    escrever("Memorias", "Servidor de casa", "o servidor de casa se chama Hermes e fica no armário", antiguidade_dias=3, importancia=5)
    escrever("Memorias", "Gato Luna", "a gata Luna gosta de dormir na janela da sala", antiguidade_dias=40, importancia=3, tags="[friday, memoria, fato, animal]")
    escrever("Memorias", "Projeto Friday", "projeto da assistente com memória no Obsidian", antiguidade_dias=10, importancia=4, tipo="projeto")
    escrever("Memorias", "Reunião de segunda", "reunião com o time às nove, levar o relatório", antiguidade_dias=200, importancia=2)
    escrever("Memorias", "Praia", "viagem para a praia em dezembro com a família", antiguidade_dias=60, importancia=3)
    for i in range(6):
        escrever("Memorias", f"Enchimento {i}", f"assunto comum {'comum ' * i}de enchimento", antiguidade_dias=5 * i, importancia=1 + i % 5)
    escrever("Topicos", "Redes neurais", "tema que você repete: redes neurais e memória", antiguidade_dias=7, origem="consolidacao")
    escrever("Eu", "Perfil", "gosta de café e de redes neurais", antiguidade_dias=9)
    escrever("Estudos", "Buracos negros", "buracos negros dobram o espaço-tempo; aprendi isso na internet", antiguidade_dias=2, origem="web")
    escrever("Visao", "Sala", "vi uma sala com janela grande e um sofá", antiguidade_dias=1, origem="camera")
    escrever("Conversas", "2026-10-20", "# 2026-10-20\n\n- 09:00 **Você**: vamos planejar a viagem para a praia\n- 09:01 **FRIDAY**: anotado", antiguidade_dias=4)
    escrever("Conversas", "2026-10-22", "# 2026-10-22\n\n- 21:00 **Você**: a gata Luna dormiu na sala\n", antiguidade_dias=2)


class PontuacaoNaoMudou(Base):
    def test_pontuacoes_iguais_as_do_codigo_anterior(self):
        self.prepara_cofre()
        corpus_dourado()
        obtido = {}
        with mock.patch.object(MEM.time, "time", return_value=T0):
            for consulta, kw in CONSULTAS_DOURADAS:
                kw = dict(kw)
                lim = kw.pop("limite", 5)
                MEM._cache.clear()
                obtido[consulta] = [(x["titulo"], x["score"]) for x in MEM.buscar(consulta, lim, **kw)]
                # segunda vez, com o cache quente, tem de dar exatamente o mesmo
                self.assertEqual([(x["titulo"], x["score"]) for x in MEM.buscar(consulta, lim, **kw)], obtido[consulta], consulta)
        self.assertEqual(obtido, DOURADO)


if __name__ == "__main__":
    unittest.main()
