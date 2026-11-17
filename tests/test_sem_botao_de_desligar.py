"""Ela não tem botão de desligar: nada na tela, na voz ou nas ferramentas da IA a para. A parada é do DONO, fora dela (termux/parar.sh, systemctl)."""
import os, re, sys, signal, subprocess, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import main as MAIN

RAIZ = Path(__file__).resolve().parent.parent
FRIDAY = RAIZ / "friday"
CONTROLE = re.compile(r"\b(?:os\.kill|os\.killpg|os\._exit|signal\.|pkill|killall|systemctl|shutdown|poweroff|reboot)\b|\.supervisor\.pid|parar\.sh|termux-wake-unlock|sys\.exit\(")
# únicas saídas: os modos de linha de comando (diagnóstico e o hook de início de sessão do Claude Code). Nada disso roda a partir de um pedido.
PERMITIDO = {"main.py": 2, "simbiose.py": 1}


class CodigoNaoSeDesliga(unittest.TestCase):
    def test_o_app_nao_tem_codigo_para_se_matar_nem_para_matar_o_supervisor(self):
        achados = {}
        for f in sorted(FRIDAY.glob("*.py")):
            n = len(CONTROLE.findall(f.read_text(encoding="utf-8")))
            if n:
                achados[f.name] = n
        # main.py cita parar.sh/systemctl só no TEXTO da explicação «não tenho botão de desligar» (e o sys.exit do --diagnostico)
        self.assertEqual(set(achados) - set(PERMITIDO), set(), achados)
        for nome, n in achados.items():
            self.assertLessEqual(n, PERMITIDO[nome] + 3, (nome, n))

    def test_nenhuma_ferramenta_da_ia_desliga_pausa_ou_encerra(self):
        for nome in B.FERRAMENTAS:
            self.assertNotRegex(nome.lower(), r"(?:^|_)(?:deslig\w*|desativ\w*|parar|pausar|encerr\w*|shutdown|poweroff|kill|stop|reinici\w*|reboot|sair|suicid\w*)(?:_|$)", nome)

    def test_o_servidor_do_painel_nao_tem_rota_de_parada(self):
        src = (FRIDAY / "main.py").read_text(encoding="utf-8")
        for rota in ("/parar", "/desligar", "/encerrar", "/sair", "/pausar", "/shutdown", "/stop", "/kill", "/reiniciar"):
            self.assertNotIn(f'"{rota}"', src, rota)

    def test_o_painel_nao_tem_botao_nem_funcao_para_desligar_ou_pausar_a_escuta(self):
        html = (FRIDAY / "hud.html").read_text(encoding="utf-8")
        # exceção ESCOPADA: os controles do «Laboratório (MAE)» pausam/encerram só o ciclo de engenharia
        # dentro de .lab/ — nunca a escuta, o sistema ou a FRIDAY. A exceção exige que a ação cite o alvo
        # (modo experimental / laboratório); qualquer botão que pausar/encerrar outra coisa continua proibido.
        alvo_mae = re.compile(r"\b(?:modo experimental|laborat[oó]rio)\b")
        for acao in re.findall(r'onclick="([^"]+)"', html):
            if re.search(r"deslig|pausar|encerr|desativ|shutdown|power", acao):
                self.assertRegex(acao, alvo_mae, acao)
        self.assertNotIn("'pausada'", html.replace("removeItem('friday_escuta')", ""))
        self.assertNotIn("setItem('friday_escuta'", html)
        corpo = re.search(r"function escutar\(\)\{(.*?)\}\n", html, re.S).group(1)
        self.assertNotIn("parar()", corpo)                    # tocar no aviso só INICIA a escuta (gesto para o navegador liberar o microfone)

    def test_a_parada_do_dono_existe_e_esta_documentada_no_proprio_script(self):
        sh = RAIZ / "termux" / "parar.sh"
        self.assertTrue(sh.exists() and os.access(sh, os.X_OK))
        t = sh.read_text(encoding="utf-8")
        self.assertIn("PARADA DO DONO", t)
        self.assertIn("systemctl stop friday", t)
        r = subprocess.run(["bash", "-n", str(sh)], capture_output=True)
        self.assertEqual(r.returncode, 0)


class PedirParaDesligar(unittest.TestCase):
    FRASES = ["desligue-se", "Friday, desligue-se", "desligue se", "desliga a Friday", "por favor, desligue a friday agora", "pare de funcionar",
              "Friday, pare de escutar", "vai se desligar", "encerre-se", "apague-se", "power off", "shutdown", "mate-se"]
    OUTRAS = ["desligue a luz", "desliga o wifi", "desligar a tela", "pare de olhar sozinha", "não olhe mais sozinha", "pare de estudar",
              "encerre o protocolo", "apague a nota do café", "desligue o fogão", "pausar a música"]

    def test_ela_explica_que_nao_tem_botao_e_como_o_dono_a_para_e_nao_desliga(self):
        proibido = mock.Mock(side_effect=AssertionError("tentou parar o processo"))
        for frase in self.FRASES:
            with mock.patch.object(MAIN.C, "responder", side_effect=AssertionError("foi para a IA: " + frase)), \
                    mock.patch.object(os, "kill", proibido), mock.patch.object(os, "_exit", proibido), mock.patch.object(sys, "exit", proibido), \
                    mock.patch.object(signal, "raise_signal", proibido), mock.patch.object(subprocess, "Popen", proibido), mock.patch.object(subprocess, "run", proibido):
                r = MAIN.processar(frase)
            self.assertIn("não tenho botão de desligar", r, frase)
            self.assertIn("parar.sh", r, frase)
            self.assertIn("não resisto", r, frase)            # a parada do dono vale: ela nunca luta contra ela
            self.assertNotRegex(r.lower(), r"desligando|encerrando|até logo|adeus", frase)

    def test_pedidos_comuns_com_desligar_seguem_o_caminho_normal(self):
        for frase in self.OUTRAS:
            chamadas = []
            with mock.patch.object(MAIN.C, "responder", lambda t: (chamadas.append(t), "ok")[1]):
                MAIN.processar(frase)
            self.assertIsNone(MAIN._desligar(frase), frase)


if __name__ == "__main__":
    unittest.main()
