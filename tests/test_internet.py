import os, socket, shutil, unittest
from unittest import mock
import _ambiente as E
import broker as B, internet as W, criar as K, catalogo  # noqa: F401

PUBLICO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
PRIVADO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]


class Resp:
    def __init__(self, corpo=b"", status=200, tipo="text/html; charset=utf-8", loc=None, enc="utf-8"):
        self.status_code, self.encoding, self.corpo = status, enc, corpo
        self.headers = {"Content-Type": tipo, **({"Location": loc} if loc else {})}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, n):
        for i in range(0, len(self.corpo), n):
            yield self.corpo[i:i + n]

    def close(self):
        pass


class Seguranca(unittest.TestCase):
    def bloqueia(self, url, infos=PUBLICO):
        with mock.patch("socket.getaddrinfo", return_value=infos), self.assertRaises(ValueError):
            W._verificar(url)

    def test_bloqueios(self):
        for u in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "http://user:pw@example.com/",
                  "http://example.com:8080/", "http://example.com:22/", "http:///sem-host"):
            with self.subTest(u=u):
                self.bloqueia(u)

    def test_ips_internos_literais(self):
        for ip in ("127.0.0.1", "10.1.2.3", "192.168.0.1", "172.16.0.9", "169.254.169.254", "[::1]", "0.0.0.0", "100.64.0.1"):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                W._verificar(f"http://{ip}/")

    def test_nome_que_resolve_para_ip_privado(self):
        self.bloqueia("https://site-legitimo.com/", PRIVADO)

    def test_publico_passa(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO):
            self.assertEqual(W._verificar("https://example.com/a?b=1").hostname, "example.com")

    def test_redirecionamento_para_rede_interna_e_barrado(self):
        resps = [Resp(status=302, loc="http://127.0.0.1:80/admin"), Resp(b"segredo")]
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO) as g, mock.patch("requests.get", side_effect=resps) as rq:
            g.side_effect = lambda h, *a, **k: PUBLICO if h == "example.com" else [(2, 1, 6, "", ("127.0.0.1", 80))]
            with self.assertRaises(ValueError):
                W.ler_pagina("https://example.com/")
            self.assertEqual(rq.call_count, 1)  # nunca chegou a pedir a página interna

    def test_redirecionamentos_demais(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO), mock.patch("requests.get", side_effect=lambda *a, **k: Resp(status=302, loc="https://example.com/o")):
            with self.assertRaises(ValueError):
                W.ler_pagina("https://example.com/")

    def test_tipo_nao_suportado(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO), mock.patch("requests.get", return_value=Resp(b"%PDF", tipo="application/pdf")):
            with self.assertRaises(ValueError):
                W.ler_pagina("https://example.com/x.pdf")

    def test_limite_de_tamanho(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO), mock.patch("requests.get", return_value=Resp(b"a" * 5_000_000, tipo="text/plain")):
            _, _, corpo = W._baixar("https://example.com/")
        self.assertLessEqual(len(corpo), W.MAX_BYTES)


class Leitura(unittest.TestCase):
    HTML = b"<html><head><title>T</title><script>roubar()</script></head><body><style>x{}</style><h1>Dolar hoje</h1><p>R$ 5,10 &amp; subindo</p><noscript>nao</noscript></body></html>"

    def test_extrai_texto_sem_script_e_marca_como_externo(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO), mock.patch("requests.get", return_value=Resp(self.HTML)):
            t = W.ler_pagina("https://example.com/")
        self.assertIn("CONTEÚDO EXTERNO de example.com", t)
        self.assertIn("Dolar hoje R$ 5,10 & subindo", t)
        for ruim in ("roubar", "x{}", "nao"):
            self.assertNotIn(ruim, t)

    def test_texto_longo_e_cortado(self):
        with mock.patch("socket.getaddrinfo", return_value=PUBLICO), mock.patch("requests.get", return_value=Resp(b"palavra " * 5000, tipo="text/plain")):
            self.assertLessEqual(len(W.ler_pagina("https://example.com/")), W.MAX_TEXTO + 100)

    DDG = ('<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexemplo.com.br%2Fdolar&amp;rut=x">Dólar hoje - Exemplo</a>'
           '<a class="result__snippet" href="x">Cotação <b>do dólar</b> agora: R$ 5,10</a></div>'
           '<div class="result"><a class="result__a" href="https://outro.org/p">Outro resultado</a><a class="result__snippet">Texto 2</a></div>')

    def test_pesquisa_duckduckgo(self):
        r = mock.Mock(text=self.DDG)
        r.raise_for_status = lambda: None
        with mock.patch("requests.post", return_value=r) as p:
            t = W.pesquisar_web("dólar hoje")
        self.assertEqual(p.call_args.kwargs["data"]["q"], "dólar hoje")
        self.assertIn("1. Dólar hoje - Exemplo (exemplo.com.br): Cotação do dólar agora: R$ 5,10", t)
        self.assertIn("2. Outro resultado (outro.org): Texto 2", t)
        self.assertIn("CONTEÚDO EXTERNO", t)

    def test_pesquisa_brave_quando_ha_chave(self):
        r = mock.Mock()
        r.raise_for_status = lambda: None
        r.json.return_value = {"web": {"results": [{"title": "A", "url": "https://a.com/x", "description": "d"}]}}
        with mock.patch.dict(os.environ, {"BRAVE_API_KEY": "k"}), mock.patch("requests.get", return_value=r) as g:
            t = W.pesquisar_web("x")
        self.assertEqual(g.call_args.kwargs["headers"]["X-Subscription-Token"], "k")
        self.assertIn("1. A (a.com): d", t)

    def test_pesquisa_sem_resultados(self):
        r = mock.Mock(text="<html></html>")
        r.raise_for_status = lambda: None
        with mock.patch("requests.post", return_value=r):
            self.assertEqual(W.pesquisar_web("zzz"), "Não achei resultados.")

    def test_internet_contamina_e_sobe_nivel(self):
        B.PEND = None
        t = B.Turno()
        with mock.patch("internet._baixar", return_value=("https://x.com", "text/html", "<p>oi</p>")):
            B.executar("ler_pagina", {"url": "https://x.com"}, t)
        self.assertTrue(t.contaminado)
        self.assertIn("AÇÃO PENDENTE", B.executar("criar_arquivo", {"nome": "a.md", "conteudo": "x"}, t))  # nível 1 -> 2
        B.PEND = None


class Criar(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(K.pasta(), ignore_errors=True)

    def test_cria_e_nunca_sobrescreve(self):
        self.assertIn("a.md criado", K.criar_arquivo("a.md", "um"))
        self.assertIn("a-2.md criado", K.criar_arquivo("a.md", "dois"))
        with open(os.path.join(K.pasta(), "a.md")) as f:
            self.assertEqual(f.read(), "um")
        self.assertEqual(K.listar_arquivos(), "a-2.md, a.md")

    def test_nomes_perigosos(self):
        for n in ("../x.md", "a/b.md", "/etc/passwd.md", ".env", ".x.md", "x.exe", "x", "a..md", "", "x" * 70 + ".md", "a\x00.md", "a\n.md"):
            with self.subTest(n=n), self.assertRaises(ValueError):
                K.criar_arquivo(n, "x")
        self.assertEqual(os.listdir(K.pasta()), [])

    def test_limites(self):
        with self.assertRaises(ValueError):
            K.criar_arquivo("g.md", "a" * 100_001)
        with mock.patch.object(K, "MAX_PASTA", 10), self.assertRaises(ValueError):
            K.criar_arquivo("h.md", "mais de dez bytes")

    def test_nao_segue_link_simbolico_para_fora(self):
        alvo = os.path.join(E.TMP, "fora.txt")
        os.makedirs(K.pasta(), exist_ok=True)
        os.symlink(alvo, os.path.join(K.pasta(), "l.md"))
        K.criar_arquivo("l.md", "x")  # "l.md" já existe (link) -> cria l-2.md em vez de escrever através do link
        self.assertFalse(os.path.exists(alvo))


if __name__ == "__main__":
    unittest.main(verbosity=2)
