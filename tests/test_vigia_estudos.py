"""Modo vigia (só protege e avisa) e tela de Estudos (só leitura)."""
import json, os, re, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import vigia as VIG, estudos_tela as ET, memoria as MEM
from test_assimilacao import Base

RAIZ = Path(__file__).resolve().parent.parent


class Vigia(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(VIG, "ARQ", os.path.join(E.TMP, "vigia-teste.json")); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(VIG.ARQ) and os.remove(VIG.ARQ))
        VIG._tent.update(painel=0, sync=0); VIG._ult["t"] = 0.0

    def test_chave_errada_avisa_na_hora(self):
        VIG.conferir(wifi=None, apps=None)                      # 1ª rodada só aprende
        VIG.tentativa_errada("painel"); VIG.tentativa_errada("painel")
        with mock.patch.object(VIG, "_wifi", return_value=None), mock.patch.object(VIG, "_apps", return_value=None):
            av = VIG.gancho(VIG._ult["t"] + 1)                  # mesmo antes dos 5 min, tentativa errada sai na hora
        self.assertTrue(any("2 tentativas com chave errada no painel" in a for a in av))
        self.assertEqual(VIG._tent["painel"], 0)

    def test_wifi_novo_e_app_novo(self):
        self.assertEqual(VIG.conferir(wifi="Casa", apps={"a.b"}), [])     # o primeiro Wi-Fi e a primeira lista viram «conhecidos»
        av = VIG.conferir(wifi="Cafe Gratis", apps={"a.b", "x.espiao"})
        self.assertTrue(any("Cafe Gratis" in a for a in av))
        self.assertTrue(any("x.espiao" in a for a in av))
        self.assertEqual(VIG.conferir(wifi="Cafe Gratis", apps={"a.b", "x.espiao"}), [])   # não repete

    def test_so_avisa_nunca_age_e_so_o_dono_liga(self):
        fonte = (RAIZ / "friday" / "vigia.py").read_text(encoding="utf-8")
        for proibido in ("os.remove", "unlink", "kill", "pm uninstall", "iptables", "nmap", "socket.connect"):
            self.assertNotIn(proibido, fonte, proibido)
        self.assertIn("desligado", VIG.tratar("desliga o modo vigia"))
        self.assertEqual(VIG.gancho(), [])
        self.assertIn("ligado", VIG.tratar("liga o modo vigia"))
        self.assertFalse([n for n in B.FERRAMENTAS if "vigia" in n.lower() or "scan" in n.lower()])


class TelaEstudos(Base):
    def setUp(self):
        super().setUp()
        MEM.guardar_estudo("fases do sono", "O sono tem fases que se repetem durante a noite. A fase profunda ajuda a memória a se fixar.", ["sono.example"])
        MEM.guardar_detalhe_estudo("fases do sono", "sono.example", "O ciclo dura cerca de noventa minutos e se repete. Na fase N3 aparecem as ondas delta.")

    def test_lista_e_abre_com_os_detalhes(self):
        l = ET.lista()
        self.assertEqual(l[0]["titulo"], "Fases do sono")
        self.assertEqual(l[0]["detalhes"], 1)
        e = ET.abrir("Fases do sono")
        self.assertIn("noventa minutos", e["detalhes"][0]["texto"])

    def test_caminho_suspeito_e_nota_que_nao_e_da_web(self):
        for t in ("../Memorias/x", "a/b", "", "x" * 200):
            self.assertIsNone(ET.abrir(t))
        (self.base("Estudos")).mkdir(parents=True, exist_ok=True)
        self.base("Estudos", "Minha.md").write_text("---\ntipo: fato\n---\n# Minha\n\nsegredo\n", encoding="utf-8")
        self.assertIsNone(ET.abrir("Minha"))

    def test_pagina_segura_e_rota_com_chave(self):
        html = (RAIZ / "friday" / "estudos.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r"\beval\(|new Function|<script src=|https?://|innerHTML")
        self.assertNotRegex(html, r"method\s*:\s*['\"]POST")
        main = (RAIZ / "friday" / "main.py").read_text(encoding="utf-8")
        self.assertIn("self._auth()", main.split('if p == "/estudos/dados":', 1)[1][:200])


if __name__ == "__main__":
    unittest.main()
