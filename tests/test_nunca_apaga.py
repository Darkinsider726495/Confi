"""«Nunca apague»: nada do que ela aprendeu some. Memória vai para Arquivo, sinapse fraca adormece (e acorda quando relembrada)."""
import os, re, json, time, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N
from test_neuronios import Cerebro

FRIDAY = Path(__file__).resolve().parent.parent / "friday"
APAGAR = re.compile(r"\b(?:os\.remove|os\.unlink|os\.rmdir|shutil\.rmtree|shutil\.move)\b|\.unlink\(|\.rmdir\(")
# as ÚNICAS exceções: arquivos temporários que nunca foram conhecimento dela (o WAV da voz e a foto da câmera, apagada de propósito depois da olhada)
# e o laboratório de engenharia (laboratorio.py): apaga SÓ DENTRO de .lab/ (caminho validado por _validar_caminho, recusa fuga e symlink),
# sempre depois de tirar snapshot — o conteúdo fica recuperável em .versoes/. O teste_confinamento_do_laboratorio abaixo prova isso.
PERMITIDO = {"android.py": 1, "visao.py": 1, "laboratorio.py": 2}


class SemApagar(unittest.TestCase):
    def test_o_codigo_nao_tem_chamada_de_apagar_arquivo_fora_da_lista(self):
        achados = {}
        for f in sorted(FRIDAY.glob("*.py")):
            n = len(APAGAR.findall(f.read_text(encoding="utf-8")))
            if n:
                achados[f.name] = n
        self.assertEqual(achados, PERMITIDO, "apagar arquivo é proibido: arquive (mova para Arquivo) em vez disso")

    def test_as_excecoes_sao_so_de_arquivo_temporario(self):
        a = (FRIDAY / "android.py").read_text(encoding="utf-8")
        v = (FRIDAY / "visao.py").read_text(encoding="utf-8")
        self.assertRegex(a, r"os\.remove\(caminho\)")                 # o WAV temporário que acabou de tocar
        self.assertRegex(v, r"shutil\.rmtree\(pasta, ignore_errors=True\)")   # a pasta temporária da foto da câmera
        self.assertIn('tempfile.mkdtemp(prefix="friday-olho-")', v)

    def test_cada_apagada_do_laboratorio_usa_o_alvo_validado(self):
        """No laboratório, tudo que é apagado é `alvo`, e todo `alvo` veio de _validar_caminho (que recusa
        fuga de caminho, caminho absoluto, extensão proibida e symlink, e resolve o realpath dentro de LAB_ROOT).
        Se alguém acrescentar uma apagada que não passe por isso, este teste falha."""
        txt = (FRIDAY / "laboratorio.py").read_text(encoding="utf-8")
        linhas = txt.splitlines()
        # cada função que apaga valida o caminho ANTES (janela de 20 linhas cobre o corpo das operações curtas do módulo)
        blocos = re.split(r"\ndef ", txt)
        for b in blocos:
            if not APAGAR.search(b):
                continue
            nome = b.split("(", 1)[0]
            self.assertGreaterEqual(b.count("_validar_caminho"), 1,
                                    f"{nome}: apaga sem validar o caminho contra o confinamento do laboratório")
        for i, l in enumerate(linhas):
            if "os.remove(" in l or ".unlink(" in l:
                self.assertRegex(l, r"os\.remove\(alvo\)|\.unlink\(\)", f"linha {i + 1} apaga algo que não é o alvo validado")


class Sinapses(Cerebro):
    def setUp(self):
        super().setUp()
        N._dorm.update(v=None, raiz=None, sujo=False)
        p = mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "0"})
        p.start(); self.addCleanup(p.stop)

    def arquivo(self):
        return self.base(".cerebro", "dormentes.json")

    def test_sinapse_fraca_adormece_em_arquivo_e_nao_some(self):
        MEM.guardar("A", "texto a", "fato")
        MEM.guardar("B", "texto b", "fato")
        e = N._estado()
        e["sin"]["Memorias/A|Memorias/X"] = [0.31, time.time()]
        N.sonhar(True)
        self.assertNotIn("Memorias/A|Memorias/X", e["sin"])
        d = json.loads(self.arquivo().read_text(encoding="utf-8"))
        self.assertIn("Memorias/A|Memorias/X", d)
        self.assertAlmostEqual(d["Memorias/A|Memorias/X"][0], 0.29, places=2)

    def test_o_que_adormeceu_sobrevive_a_reiniciar(self):
        MEM.guardar("A", "texto a", "fato")
        N._estado()["sin"]["Memorias/A|Memorias/X"] = [0.31, time.time()]
        N.sonhar(True)
        N._dorm.update(v=None, raiz=None)
        self.assertIn("Memorias/A|Memorias/X", N._dormentes())

    def test_relembrar_acorda_com_vantagem_sobre_aprender_do_zero(self):
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        MEM.guardar("Backup", "O backup do servidor é semanal", "tarefa")
        k = N._chave("Memorias/Servidor", "Memorias/Backup")
        N._adormecer(k, [0.28, time.time()])
        N._salvar_dormentes()
        MEM.lembrar("backup do servidor")
        self.assertEqual(self.sinapse("Memorias/Servidor", "Memorias/Backup"), 1.5)     # do zero seria 1.0
        self.assertNotIn(k, N._dormentes())
        N._salvar_dormentes()
        self.assertNotIn(k, json.loads(self.arquivo().read_text(encoding="utf-8")))

    def test_acima_do_limite_as_mais_fracas_adormecem_em_vez_de_sumir(self):
        e = N._estado()
        for i in range(6):
            e["sin"][f"Memorias/A{i}|Memorias/B{i}"] = [float(i + 1), time.time()]
        with mock.patch.object(N, "MAX_SINAPSES", 3):
            N._salvar()
        self.assertEqual(len(e["sin"]), 3)
        self.assertEqual(sorted(N._dormentes()), [f"Memorias/A{i}|Memorias/B{i}" for i in range(3)])
        self.assertEqual(len(json.loads(self.arquivo().read_text(encoding="utf-8"))), 3)

    def test_arquivo_de_dormentes_adulterado_e_ignorado_com_seguranca(self):
        self.arquivo().parent.mkdir(parents=True, exist_ok=True)
        self.arquivo().write_text(
                                  json.dumps({"ok|par": [0.2, 5], "ruim": [1, 2], "x|y": "texto", "a|b": [1]}), encoding="utf-8")
        N._dorm.update(v=None, raiz=None)
        self.assertEqual(list(N._dormentes()), ["ok|par"])

    def test_o_resumo_do_sono_diz_que_ficou_guardado(self):
        MEM.guardar("A", "texto a", "fato")
        N._estado()["sin"]["Memorias/A|Memorias/X"] = [0.31, time.time()]
        N.sonhar(True)
        self.assertIn("Adormeci 1 sinapses fracas", N._estado()["resumo_sono"])
        self.assertNotIn("Podei", N._estado()["resumo_sono"])


class Notas(Cerebro):
    def tudo(self):
        return {str(p.relative_to(self.base())) for p in self.base().rglob("*.md")}

    def test_o_sono_nunca_faz_nenhuma_nota_sumir(self):
        MEM.guardar("Café", "Toma café sem açúcar", "preferencia")
        MEM.guardar("Servidor", "O servidor de casa roda Ollama", "projeto")
        self.dia(1, [("10:00", "como está o servidor?", "Está no ar.")])
        antes = self.tudo()
        N.sonhar(True)
        N.sonhar(True)
        self.assertLessEqual(antes, self.tudo())

    def test_nota_de_autoconhecimento_que_deixou_de_existir_vai_para_arquivo(self):
        N.autoconhecer()
        velha = self.base("Eu", "ferramenta antiga que nao existe mais.md")
        velha.write_text(MEM._montar({"tipo": "eu", "origem": "sistema"}, "# ferramenta antiga\n\nera uma ferramenta.\n"), encoding="utf-8")
        MEM._cache.clear()
        N.autoconhecer()
        self.assertFalse(velha.exists())
        arq = list(self.base("Arquivo").glob("Eu ferramenta antiga*.md"))
        self.assertEqual(len(arq), 1)
        self.assertIn("era uma ferramenta", arq[0].read_text(encoding="utf-8"))

    def test_nota_sua_na_pasta_eu_nunca_e_tocada(self):
        N.autoconhecer()
        sua = self.base("Eu", "minha anotacao.md")
        sua.write_text(MEM._montar({"tipo": "eu", "origem": "usuario"}, "# minha anotacao\n\nminha.\n"), encoding="utf-8")
        MEM._cache.clear()
        N.autoconhecer()
        self.assertTrue(sua.exists())

    def test_estudos_acima_do_limite_vao_para_arquivo(self):
        with mock.patch.object(MEM, "MAX_ESTUDOS", 2):
            for t in ("alfa", "beta", "gama", "delta"):
                MEM.guardar_estudo(t, f"Texto de estudo sobre {t} com bastante conteúdo para passar do mínimo exigido pela gravação.", ["site.example"])
                time.sleep(0.01)
        self.assertEqual(len(list(self.base("Estudos").glob("*.md"))), 2)
        self.assertEqual(len(list(self.base("Arquivo").glob("Estudo *.md"))), 2)

    def test_esquecer_so_arquiva(self):
        MEM.guardar("Segredinho", "algo que ela não deve mais usar", "fato")
        MEM.esquecer("Segredinho")
        self.assertEqual(len(list(self.base("Arquivo").glob("Segredinho*.md"))), 1)

    def test_atualizacao_nunca_sobrescreve_acrescenta(self):
        MEM.guardar("Plano", "primeira versão do plano", "projeto")
        MEM.guardar("Plano", "segunda versão do plano", "projeto")
        t = self.base("Memorias", "Plano.md").read_text(encoding="utf-8")
        self.assertIn("primeira versão", t)
        self.assertIn("segunda versão", t)


if __name__ == "__main__":
    unittest.main()
