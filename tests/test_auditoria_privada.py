"""Fase 1.4 — a trilha de auditoria registra o FATO (ferramenta, nível, decisão, código, tamanho), não o conteúdo.

Antes: cada evento guardava em texto simples os argumentos (até 500 caracteres: texto de SMS, título e texto de memória, consultas, links)
e os primeiros 300 caracteres do resultado (o que ela lembrou, leu, anotou...). Agora:
  - argumentos de texto viram «‹texto: N caracteres›»; só ficam em claro os identificadores que a ferramenta declara (relé, alias do contato)
    e, mesmo assim, depois da redação; links ficam só com o servidor;
  - o resultado vira um código («ok», «Erro», «Erro: <Classe>») e o tamanho;
  - tudo que qualquer módulo grava passa por uma redação final (cartão, CPF, telefone, e-mail, chaves, «senha é …», links com chave);
  - a cadeia de hashes continua valendo, inclusive para linhas antigas.
"""
import json, os, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import privacidade as P

BIN, LOG = E.termux_falso()
S = {"type": "string"}
SEGREDOS = ["Rua Augusta 123", "ZXQ-98765-ALFA", "maria@exemplo.com", "4111 1111 1111 1111", "123.456.789-09", "sk-ant-abcdefghijklmnop1234", "+5511999990001"]
TEXTO_PRIVADO = "Maria mora na Rua Augusta 123 e o código de acesso é ZXQ-98765-ALFA; email maria@exemplo.com"


def trilha():
    with open(B.AUDITORIA, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def bruto():
    with open(B.AUDITORIA, encoding="utf-8") as f:
        return f.read()


B.registrar("devolve_privado_teste", "devolve texto privado", {}, [], lambda: TEXTO_PRIVADO, 0)
B.registrar("recebe_texto_teste", "recebe texto livre", {"texto": S, "titulo": S, "nome": S, "contato": S}, ["texto"], lambda **k: "pronto", 1,
            audit_args=("nome", "contato"))
B.registrar("quebra_teste", "falha com mensagem privada", {}, [], lambda: (_ for _ in ()).throw(ValueError(TEXTO_PRIVADO)), 0)
B.registrar("devolve_erro_proprio_teste", "devolve um texto de erro", {}, [], lambda: "Erro: contato Maria Souza não está na lista", 0)
B.registrar("acao_n2_privada_teste", "pendência com texto", {"texto": S}, ["texto"], lambda texto: "feito", 2)


class Base(unittest.TestCase):
    def setUp(self):
        B.PEND = None
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        self.addCleanup(setattr, B, "PEND", None)


class Resultado(Base):
    def test_resultado_nao_vai_em_claro_para_a_trilha(self):
        r = B.executar("devolve_privado_teste", {})
        self.assertEqual(r, TEXTO_PRIVADO)                    # quem pediu continua recebendo tudo
        txt = bruto()
        for s in ("Augusta", "ZXQ-98765", "maria@exemplo.com"):
            self.assertNotIn(s, txt)
        e = trilha()[-1]
        self.assertEqual((e["ferramenta"], e["nivel"], e["decisao"], e["resultado"], e["tam"]), ("devolve_privado_teste", 0, "automatico", "ok", len(TEXTO_PRIVADO)))
        self.assertTrue(e["ts"] and e["hash"] and e["prev"])

    def test_excecao_guarda_a_classe_nao_a_mensagem(self):
        r = B.executar("quebra_teste", {})
        self.assertTrue(r.startswith("Erro: "))
        self.assertIn("Augusta", r)                           # a IA/usuário veem o erro completo
        e = trilha()[-1]
        self.assertEqual(e["resultado"], "Erro: ValueError")
        self.assertNotIn("Augusta", bruto())

    def test_texto_de_erro_devolvido_pela_ferramenta_vira_so_erro(self):
        B.executar("devolve_erro_proprio_teste", {})
        self.assertEqual(trilha()[-1]["resultado"], "Erro")
        self.assertNotIn("Maria Souza", bruto())

    def test_vigilia_do_estado_interno_continua_enxergando_erros(self):
        for f in ("quebra_teste", "devolve_erro_proprio_teste"):
            B.executar(f, {})
        self.assertTrue(all(str(e["resultado"]).startswith("Erro") for e in trilha()))


class Argumentos(Base):
    def test_texto_livre_vira_so_tamanho(self):
        B.executar("recebe_texto_teste", {"texto": TEXTO_PRIVADO, "titulo": "Segredo da Maria"})
        txt = bruto()
        for s in ("Augusta", "ZXQ", "Maria", "Segredo"):
            self.assertNotIn(s, txt)
        args = json.loads(trilha()[-1]["args"])
        self.assertEqual(args["texto"], f"‹texto: {len(TEXTO_PRIVADO)} caracteres›")
        self.assertEqual(args["titulo"], "‹texto: 16 caracteres›")

    def test_identificador_declarado_fica_em_claro(self):
        B.executar("recebe_texto_teste", {"texto": "x", "nome": "tomada", "contato": "mae"})
        args = json.loads(trilha()[-1]["args"])
        self.assertEqual((args["nome"], args["contato"]), ("tomada", "mae"))

    def test_identificador_declarado_passa_pela_redacao(self):
        B.executar("recebe_texto_teste", {"texto": "x", "contato": "+5511999990001"})
        self.assertNotIn("99999", bruto())
        self.assertEqual(json.loads(trilha()[-1]["args"])["contato"], "‹telefone›")

    def test_identificador_longo_demais_vira_tamanho(self):
        B.executar("recebe_texto_teste", {"texto": "x", "nome": "n" * 100})
        self.assertEqual(json.loads(trilha()[-1]["args"])["nome"], "‹texto: 100 caracteres›")

    def test_numeros_e_booleanos_ficam(self):
        B.executar("criar_lembrete", {"minutos": 15, "texto": "pagar o boleto do João"})
        args = json.loads(trilha()[-1]["args"])
        self.assertEqual(args["minutos"], 15)
        self.assertNotIn("boleto", bruto())

    def test_sms_real_guarda_o_alias_e_nao_o_texto(self):
        with mock.patch.dict(os.environ, {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG}):
            B.executar("enviar_sms", {"contato": "mae", "texto": "chego às 19h, a senha do wifi é 12345678"})
            B.confirmar_voz("confirmo")
        txt = bruto()
        self.assertNotIn("19h", txt)
        self.assertNotIn("12345678", txt)
        decisoes = [(e["decisao"], json.loads(e["args"])["contato"]) for e in trilha() if e["ferramenta"] == "enviar_sms" and "args" in e]
        self.assertIn(("pendente", "mae"), decisoes)
        self.assertIn(("confirmado_voz", "mae"), decisoes)

    def test_pendencia_tambem_nao_guarda_o_texto(self):
        B.executar("acao_n2_privada_teste", {"texto": TEXTO_PRIVADO})
        self.assertNotIn("Augusta", bruto())
        self.assertEqual(trilha()[-1]["decisao"], "pendente")

    def test_url_fica_so_com_o_servidor(self):
        with mock.patch("internet._baixar", return_value=("https://exemplo.org/p", "text/html", "<p>oi</p>")):
            B.executar("ler_pagina", {"url": "https://exemplo.org/conta/maria?token=abc123SECRETO&x=1"})
        txt = bruto()
        self.assertNotIn("SECRETO", txt)
        self.assertNotIn("maria", txt)
        self.assertEqual(json.loads(trilha()[-1]["args"])["url"], "https://exemplo.org/…")

    def test_consulta_de_busca_vira_tamanho(self):
        with mock.patch("internet.resultados", return_value=[]):
            B.executar("pesquisar_web", {"consulta": "endereço da clínica da Maria"})
        self.assertNotIn("clínica", bruto())


class RedacaoFinal(Base):
    def test_o_que_qualquer_modulo_grava_passa_pela_redacao(self):
        B._audit(ferramenta="curiosidade", args="buscar a senha é ZXQ-98765-ALFA", nivel=0, decisao="estudo",
                 resultado="Tema (maria@exemplo.com, https://x.org/a?token=SEGREDO123456789012345678901234)")
        txt = bruto()
        for s in ("ZXQ-98765", "maria@exemplo.com", "SEGREDO123"):
            self.assertNotIn(s, txt)
        self.assertEqual(B.verificar_auditoria(), (True, 1))

    def test_campos_de_controle_nao_sao_alterados(self):
        B._audit(ferramenta="rotina:bom dia", decisao="executado", nome="bom dia", hora="08:05")
        e = trilha()[-1]
        self.assertEqual((e["ferramenta"], e["decisao"], e["nome"], e["hora"]), ("rotina:bom dia", "executado", "bom dia", "08:05"))
        self.assertEqual(B.verificar_auditoria(), (True, 1))

    def test_cadeia_de_hashes_continua_valida_e_detecta_adulteracao(self):
        for i in range(3):
            B.executar("devolve_privado_teste", {})
        self.assertEqual(B.verificar_auditoria(), (True, 3))
        linhas = bruto().splitlines()
        e = json.loads(linhas[1])
        e["tam"] = 1
        linhas[1] = json.dumps(e, ensure_ascii=False)
        with open(B.AUDITORIA, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        self.assertFalse(B.verificar_auditoria()[0])

    def test_linhas_antigas_com_texto_em_claro_continuam_verificando(self):
        ev = {"ferramenta": "anotar", "args": '{"texto": "antigo, gravado antes da Fase 1.4"}', "nivel": 1, "decisao": "automatico", "resultado": "Nota salva", "ts": "2026-10-01T10:00:00"}
        ev["prev"] = "0" * 64
        ev["hash"] = B._hash(ev["prev"], ev)
        with open(B.AUDITORIA, "w", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.assertEqual(B.verificar_auditoria(), (True, 1))
        B.executar("devolve_privado_teste", {})
        self.assertEqual(B.verificar_auditoria(), (True, 2))

    def test_ultimos_nao_traz_conteudo(self):
        B.executar("devolve_privado_teste", {})
        self.assertEqual(set(B.ultimos(1)[0]), {"ts", "ferramenta", "decisao", "nivel"})


class Redator(unittest.TestCase):
    CASOS = [
        ("cartão", "paguei com 4111 1111 1111 1111 ontem", "4111"),
        ("cartão colado", "cartão 4111111111111111", "4111111111111111"),
        ("CPF", "meu cpf é 123.456.789-09", "123.456.789"),
        ("CPF sem pontos", "cpf 12345678909", "12345678909"),
        ("CNPJ", "cnpj 12.345.678/0001-95", "12.345.678"),
        ("e-mail", "escreva para maria.souza+x@exemplo.com.br", "maria.souza"),
        ("telefone BR", "ligue (11) 98888-0002", "98888"),
        ("telefone com +55", "ligue +5511999990001", "999990001"),
        ("telefone solto", "11988880002", "88880002"),
        ("telefone internacional", "call +14155552671", "4155552671"),
        ("chave sk-", "a chave é sk-ant-abcdefghijklmnop1234", "abcdefghijklmnop"),
        ("JWT", "token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnopqrstuvwx.yz", "eyJhbGci"),
        ("AWS", "AKIAABCDEFGHIJKLMNOP", "AKIAABCD"),
        ("GitHub", "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdef"),
        ("Bearer", "Authorization: Bearer abc123def456ghi789", "abc123def456"),
        ("senha é", "a senha é Cachorro123", "Cachorro123"),
        ("senha: valor", "senha: 12345678", "12345678"),
        ("pin", "o pin é 4321", "4321"),
        ("senha em inglês", "password = hunter2", "hunter2"),
        ("token longo", "x" + "aB3" * 14, "aB3aB3aB3aB3"),
        ("URL com chave", "veja https://api.exemplo.org/v1/x?key=SEGREDO&u=1", "SEGREDO"),
        ("URL com usuário e senha", "https://joao:senha123@exemplo.org/repo", "senha123"),
    ]

    def test_mascara_cada_tipo(self):
        for nome, texto, segredo in self.CASOS:
            with self.subTest(nome):
                self.assertNotIn(segredo, P.redigir(texto))

    def test_preserva_o_texto_em_volta(self):
        self.assertEqual(P.redigir("paguei com 4111 1111 1111 1111 ontem"), "paguei com ‹número› ontem")
        self.assertEqual(P.redigir("pedido 20261024095612 recebido"), "pedido ‹número› recebido")
        self.assertEqual(P.redigir("cnpj 12.345.678/0001-95 ok"), "cnpj ‹cnpj› ok")

    def test_nao_mexe_em_texto_comum(self):
        for t in ("bom dia", "rotina:bom dia 08:05", "lembrete em 15 minutos", "tomada ligada", "Tema (exemplo.org, outro.org)", "reunião às 14h30 na sala 3"):
            self.assertEqual(P.redigir(t), t)

    def test_limite_de_tamanho(self):
        self.assertLessEqual(len(P.redigir("a " * 500, limite=50)), 51)

    def test_url_so_com_servidor(self):
        self.assertEqual(P.so_servidor("https://usuario:senha@Exemplo.ORG:8443/a/b?c=d#e"), "https://exemplo.org:8443/…")
        self.assertEqual(P.so_servidor("https://exemplo.org"), "https://exemplo.org")
        self.assertEqual(P.so_servidor("nao e url"), "‹link›")

    def test_resumir_args_sozinho_ja_minimiza(self):
        # a camada 1 não depende da redação final (a camada 2 é a rede de segurança)
        r = json.loads(P.resumir_args({"url": "https://exemplo.org/conta/maria?token=SEGREDO", "texto": "oi Maria", "ms": 300, "ligar": True,
                                      "contato": "+5511999990001", "nome": "tomada"}, claros=("contato", "nome")))
        self.assertEqual(r, {"url": "https://exemplo.org/…", "texto": "‹texto: 8 caracteres›", "ms": 300, "ligar": True,
                             "contato": "‹telefone›", "nome": "tomada"})

    def test_idempotente(self):
        t = "senha é X1y2z3 e cpf 123.456.789-09"
        self.assertEqual(P.redigir(P.redigir(t)), P.redigir(t))


if __name__ == "__main__":
    unittest.main()
