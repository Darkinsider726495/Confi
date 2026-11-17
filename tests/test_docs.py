"""A documentação acompanha o código: toda variável de ambiente nova está no .env.example e os arquivos citados existem."""
import re, unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class Variaveis(unittest.TestCase):
    def test_toda_variavel_de_visao_e_cerebro_esta_no_env_example(self):
        env = (RAIZ / ".env.example").read_text(encoding="utf-8")
        usadas = set()
        for f in (RAIZ / "friday").glob("*.py"):
            usadas |= set(re.findall(r'"((?:VISAO|CEREBRO)_[A-Z_]+)"', f.read_text(encoding="utf-8")))
            usadas |= {"CEREBRO_" + n for n in re.findall(r'_teto\("([A-Z_]+)"', f.read_text(encoding="utf-8"))}
        usadas.add("VISAO_FONTE")
        self.assertGreaterEqual(len(usadas), 12)
        faltam = sorted(u for u in usadas if u not in env)
        self.assertEqual(faltam, [], "documente no .env.example")

    def test_env_example_nao_tem_segredo(self):
        env = (RAIZ / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(env, r"sk-ant-[A-Za-z0-9_-]{10,}")
        self.assertNotRegex(env, r"eyJ[A-Za-z0-9_-]{20,}")


DOCS = ["README.md", "CLAUDE.md", "servidor/README.md"] + sorted(str(p.relative_to(RAIZ)) for p in (RAIZ / "docs").glob("*.md"))
EXTENSOES = r"(?:md|py|sh|html|js|json|txt|yml|svg|png)"


class Links(unittest.TestCase):
    """Fase 1.6: documento que cita um arquivo que não existe engana quem lê. Links Markdown e caminhos entre crases têm de apontar para algo real."""

    def test_links_markdown_apontam_para_arquivos_que_existem(self):
        faltam = []
        for nome in DOCS:
            texto = (RAIZ / nome).read_text(encoding="utf-8")
            for alvo in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", texto):
                if re.match(r"[a-z]+:", alvo):
                    continue
                if not (RAIZ / nome).parent.joinpath(alvo).exists():
                    faltam.append(f"{nome} -> {alvo}")
        self.assertEqual(faltam, [])

    def test_caminhos_citados_entre_crases_existem(self):
        faltam = []
        padrao = r"`((?:docs|friday|tests|termux|servidor|reports|\.claude)/[A-Za-z0-9_./-]*[A-Za-z0-9_]\." + EXTENSOES + r")`"
        for nome in DOCS:
            for caminho in sorted(set(re.findall(padrao, (RAIZ / nome).read_text(encoding="utf-8")))):
                if not (RAIZ / caminho).exists():
                    faltam.append(f"{nome} cita {caminho}")
        self.assertEqual(faltam, [])

    def test_codigo_nao_cita_documento_que_nao_existe(self):
        faltam = []
        for f in sorted((RAIZ / "friday").glob("*.py")):
            for caminho in set(re.findall(r"\b(docs/[A-Za-z0-9_./-]+\.md)\b", f.read_text(encoding="utf-8"))):
                if not (RAIZ / caminho).exists():
                    faltam.append(f"{f.name} cita {caminho}")
        self.assertEqual(faltam, [], "nucleo.py cita docs/NUCLEO.md: ver a decisão sobre esse módulo (docs/ARQUITETURA.md)")


if __name__ == "__main__":
    unittest.main()
