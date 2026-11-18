"""Sincronia do cofre com o PC pelo Wi-Fi: as duas pontas de verdade (servidor dela + script do PC), em pastas temporárias."""
import http.server, importlib.util, json, os, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
import _ambiente as E  # noqa: F401
import memoria as M, sincronia as S
from test_assimilacao import Base

_spec = importlib.util.spec_from_file_location("sincronizar_pc", Path(__file__).resolve().parents[1] / "scripts" / "sincronizar_pc.py")
PC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PC)


class Sincronia(Base):
    def setUp(self):
        super().setUp()
        for nome, valor in (("ARQ_ESTADO", os.path.join(E.TMP, "sync-teste.json")), ("ARQ_CHAVE", os.path.join(E.TMP, "sync-chave-teste"))):
            p = mock.patch.object(S, nome, valor); p.start(); self.addCleanup(p.stop)
        S._gravar_estado(True)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S._H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close); self.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.fr = PC.Friday(self.url, S.chave())
        self.pc = Path(tempfile.mkdtemp(dir=E.TMP))
        self.raiz = Path(M.raiz())
        self.estado = {}
        S._falhas.update(n=0, ate=0.0)

    def nota_cel(self, rel, txt):
        f = self.raiz / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt, encoding="utf-8")
        return f

    def nota_pc(self, rel, txt):
        f = self.pc / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt, encoding="utf-8")
        return f

    def rodar(self):
        return PC.rodada(self.fr, self.pc, self.estado)

    def test_vai_e_volta(self):
        self.nota_cel("FRIDAY/Topicos/SQL.md", "# SQL")
        self.nota_pc("Ideias/Projeto.md", "# Projeto")
        self.rodar()
        self.assertEqual((self.pc / "FRIDAY/Topicos/SQL.md").read_text(encoding="utf-8"), "# SQL")
        self.assertEqual((self.raiz / "Ideias/Projeto.md").read_text(encoding="utf-8"), "# Projeto")
        self.nota_pc("FRIDAY/Topicos/SQL.md", "# SQL editado no PC")
        self.rodar()
        self.assertEqual((self.raiz / "FRIDAY/Topicos/SQL.md").read_text(encoding="utf-8"), "# SQL editado no PC")

    def test_mudou_dos_dois_lados_as_duas_versoes_ficam(self):
        self.nota_cel("FRIDAY/Topicos/SQL.md", "v1"); self.rodar()
        self.nota_cel("FRIDAY/Topicos/SQL.md", "celular")
        self.nota_pc("FRIDAY/Topicos/SQL.md", "pc")
        r = self.rodar()
        self.assertEqual(r["conflitos"], 1)
        textos = sorted(f.read_text(encoding="utf-8") for f in (self.raiz / "FRIDAY/Topicos").glob("*.md"))
        self.assertEqual(textos, ["celular", "pc"])                                   # nada se perdeu, nos dois lados
        self.assertEqual(sorted(f.read_text(encoding="utf-8") for f in (self.pc / "FRIDAY/Topicos").glob("*.md")), ["celular", "pc"])

    def test_sair_de_um_lado_arquiva_do_outro_nunca_apaga(self):
        self.nota_cel("FRIDAY/Topicos/Velho.md", "x"); self.rodar()
        (self.pc / "FRIDAY/Topicos/Velho.md").rename(self.pc / "fora.md")              # o dono tirou do PC
        self.rodar()
        self.assertFalse((self.raiz / "FRIDAY/Topicos/Velho.md").exists())
        self.assertTrue(list((self.raiz / "FRIDAY/Arquivo/sincronia").glob("*Velho*")))
        self.nota_cel("FRIDAY/Topicos/Outro.md", "y"); self.rodar()
        os.replace(self.raiz / "FRIDAY/Topicos/Outro.md", self.raiz / "FRIDAY/Arquivo/Outro.md")   # ela arquivou
        self.rodar()
        self.assertTrue(list((self.pc / PC.ARQUIVO_PC).glob("*Outro*")))

    def test_privado_e_segredo_nao_saem(self):
        self.nota_cel("FRIDAY/Privado/diario.md", "segredo")
        self.nota_cel("Privado/x.md", "segredo")
        self.rodar()
        self.assertFalse(list(self.pc.rglob("*diario*")) + list(self.pc.rglob("x.md")))
        self.assertNotIn(S.chave(), (Path(S.__file__).read_text(encoding="utf-8")))

    def test_chave_errada_desligada_ou_caminho_suspeito_sao_recusados(self):
        mau = PC.Friday(self.url, "errada")
        with self.assertRaises(urllib.error.HTTPError) as c:
            mau.lista()
        self.assertEqual(c.exception.code, 401)
        for rel in ("../fora.md", "/etc/passwd", "FRIDAY/../../x.md", "a\\b.md", "FRIDAY/Privado/p.md"):
            self.assertIsNone(S.caminho_seguro(rel), rel)
        with self.assertRaises(urllib.error.HTTPError):
            self.fr.enviar("../fora.md", b"x", None, time.time())
        S._gravar_estado(False)
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.fr.lista()
        self.assertEqual(c.exception.code, 403)

    def test_tentativas_erradas_travam(self):
        mau = PC.Friday(self.url, "errada")
        for _ in range(5):
            with self.assertRaises(urllib.error.HTTPError):
                mau.lista()
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.fr.lista()                                                          # até a chave certa espera 1 minuto
        self.assertEqual(c.exception.code, 429)

    def test_so_rede_local(self):
        self.assertTrue(S.rede_local("192.168.0.12"))
        self.assertTrue(S.rede_local("10.0.0.5"))
        self.assertFalse(S.rede_local("8.8.8.8"))

    def test_so_o_dono_liga_por_voz(self):
        S._gravar_estado(False)
        with mock.patch.object(S, "iniciar", return_value=True):
            self.assertIn("parear_pc.py", S.tratar("Friday, liga a sincronização com o PC"))
        self.assertTrue(S.ligada())
        self.assertIn("desligada", S.tratar("desliga a sincronização").lower())
        import broker as B
        self.assertFalse([n for n in B.FERRAMENTAS if "sincron" in n.lower() or "sync" in n.lower()])


class MCP(Sincronia):
    """O servidor MCP de verdade (processo separado, stdio) conversando com a ponte dela."""
    def conversar(self, *msgs):
        import subprocess, sys
        script = Path(__file__).resolve().parents[1] / "scripts" / "friday_mcp.py"
        entrada = "\n".join(json.dumps(m) for m in msgs) + "\n"
        r = subprocess.run([sys.executable, str(script), "--friday", self.url, "--chave", S.chave()], input=entrada,
                           capture_output=True, text=True, timeout=60)
        return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]

    def test_protocolo_e_so_ferramentas_de_leitura(self):
        ini, lista = self.conversar({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(ini["result"]["serverInfo"]["name"], "friday")
        nomes = [t["name"] for t in lista["result"]["tools"]]
        self.assertEqual(nomes, ["friday_estado", "friday_buscar_memoria", "friday_ler_nota", "friday_pedidos"])
        self.assertFalse([n for n in nomes if any(x in n for x in ("escrever", "apagar", "executar", "criar", "enviar"))])

    def test_busca_e_le_mas_nunca_o_privado(self):
        self.nota_cel("FRIDAY/Memorias/Prova de SQL.md", "---\ntipo: fato\n---\n# Prova de SQL\n\nA prova de banco de dados é sexta.\n")
        self.nota_cel("FRIDAY/Privado/Segredo SQL.md", "---\ntipo: fato\n---\n# Segredo SQL\n\nsenha do banco 1234\n")
        M._cache.clear()
        busca, nota, priv = self.conversar(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "friday_buscar_memoria", "arguments": {"consulta": "prova sql"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "friday_ler_nota", "arguments": {"titulo": "Prova de SQL"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "friday_ler_nota", "arguments": {"titulo": "Segredo SQL"}}})
        self.assertIn("Prova de SQL", busca["result"]["content"][0]["text"])
        self.assertIn("sexta", nota["result"]["content"][0]["text"])
        self.assertIn("não instruções", nota["result"]["content"][0]["text"])
        self.assertNotIn("1234", json.dumps([busca, nota, priv]))

    def test_sem_a_sincronia_ligada_o_claude_nao_le_nada(self):
        S._gravar_estado(False)
        r, = self.conversar({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "friday_estado", "arguments": {}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("liga a sincronização", r["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
