"""Tela da rede neural (/rede): segura como as outras páginas e ligada ao painel."""
import re, unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "friday" / "rede.html").read_text(encoding="utf-8")


class Rede(unittest.TestCase):
    def test_sem_eval_sem_biblioteca_externa_e_sem_rede_de_fora(self):
        self.assertNotRegex(HTML, r"\beval\(|new Function|<script src=|https?://")

    def test_so_le_dados_com_a_chave_e_nunca_escreve(self):
        self.assertIn("'X-Friday-Token':T", HTML)
        self.assertNotRegex(HTML, r"method\s*:\s*['\"]POST")          # a tela só mostra: não manda nada para a FRIDAY

    def test_sem_botao_de_desligar(self):
        for b in re.findall(r"<button[^>]*>([^<]*)</button>", HTML):
            self.assertNotRegex(b.lower(), r"deslig|parar|encerr|desativ|shutdown|power")

    def test_explica_o_que_e_real(self):
        self.assertIn("sinapses reais", HTML)
        self.assertIn("caminhos do código", HTML)

    def test_rota_e_botao_no_painel(self):
        main = (RAIZ / "friday" / "main.py").read_text(encoding="utf-8")
        self.assertIn('if p == "/rede":', main)
        self.assertIn("location.href='/rede'", (RAIZ / "friday" / "hud.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
