"""Fase 5 — coordenador (friday/coordenador.py): reserva de recursos e avaliação de propostas com decisão explicada.

Mapa dos testes da missão:  I concorrência e coordenação (duas ações no mesmo recurso não rodam juntas; as independentes continuam em paralelo, como o dono decidiu) ·
F (o que exige o dono continua exigindo, por mais alta que seja a nota) · G (o registro de decisões não guarda conteúdo).
"""
import ast, json, os, threading, time, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import coordenador as C, experiencias as X, tarefas as T
from test_tarefas import Base as BaseT, SEGREDO

RAIZ = Path(os.path.dirname(os.path.abspath(__file__))).parent / "friday"


class Base(BaseT):
    def setUp(self):
        super().setUp()
        X.reiniciar()
        C.reiniciar()
        self.addCleanup(X.reiniciar)
        self.addCleanup(C.reiniciar)
        self.dentro, self.pico, self.chamadas, self.trava = 0, 0, [], threading.Lock()

    def ferramenta_lenta(self, nome="lenta_exp", demora=0.25, recursos=None, nivel=1, falha=False):
        def fn(**kw):
            with self.trava:
                self.dentro += 1
                self.pico = max(self.pico, self.dentro)
                self.chamadas.append(dict(kw))
            try:
                time.sleep(demora)
                if falha:
                    raise RuntimeError("quebrou de propósito")
                return "Feito."
            finally:
                with self.trava:
                    self.dentro -= 1
        B.registrar(nome, "ferramenta de teste lenta", {"nome": {"type": "string", "maxLength": 20}}, ["nome"], fn, nivel)
        self.addCleanup(B.FERRAMENTAS.pop, nome, None)
        p = mock.patch.dict(C.RECURSOS, {nome: recursos or (lambda a: [("rele:" + a["nome"], "excl")])})
        p.start()
        self.addCleanup(p.stop)
        return nome

    def tarefa(self, ferr, nome, **kw):
        return T.criar(f"usar {nome}", passos=[{"descricao": "usar", "ferramenta": ferr, "args": {"nome": nome}}], **kw)

    def juntas(self, tids):
        ts = [threading.Thread(target=T.executar, args=(t,)) for t in tids]
        [t.start() for t in ts]
        [t.join() for t in ts]


class Reserva(Base):
    def test_I_no_mesmo_recurso_uma_espera_a_outra(self):
        f = self.ferramenta_lenta()
        self.juntas([self.tarefa(f, "rele1"), self.tarefa(f, "rele1")])
        self.assertEqual((self.pico, len(self.chamadas)), (1, 2), "as duas rodaram, uma de cada vez")
        self.assertEqual(C.ocupados(), [], "e nada ficou reservado")

    def test_I_em_recursos_diferentes_continuam_em_paralelo(self):
        f = self.ferramenta_lenta()
        self.juntas([self.tarefa(f, "rele1"), self.tarefa(f, "rele2")])
        self.assertEqual(self.pico, 2, "o dono decidiu: o que não se atrapalha pode ir junto")

    def test_I_compartilhado_convive_com_compartilhado_mas_nao_com_exclusivo(self):
        """O nome passado à ferramenta de teste diz o modo em que ela usa o «cofre»: «comp» ou «excl»."""
        f = self.ferramenta_lenta(recursos=lambda a: [("cofre", a["nome"])])
        for modos, esperado in ((("comp", "comp"), 2), (("comp", "excl"), 1), (("excl", "comp"), 1), (("excl", "excl"), 1)):
            with self.subTest(modos=modos):
                self.dentro = self.pico = 0
                self.juntas([self.tarefa(f, modos[0]), self.tarefa(f, modos[1])])
                self.assertEqual(self.pico, esperado)

    def test_tarefa_que_espera_demais_fica_pronta_sem_executar_e_diz_por_que(self):
        f = self.ferramenta_lenta(demora=0.8)
        a, b = self.tarefa(f, "rele1"), self.tarefa(f, "rele1")
        with mock.patch.object(T, "ESPERA_RECURSO_S", 0.2):
            t1 = threading.Thread(target=T.executar, args=(a,))
            t1.start()
            time.sleep(0.15)
            r = T.executar_proximo(b)
            t1.join()
        self.assertEqual((r["passo"], r["broker"], T.obter(b)["estado"]), (None, None, T.PRONTA))
        self.assertIn("em uso por " + a, r["motivo"])
        self.assertIn("esperar o recurso", T.obter(b)["proxima_acao"])
        self.assertEqual(len(self.chamadas), 1, "a segunda NÃO foi executada")
        T.executar(b)                                                     # liberado: agora roda
        self.assertEqual((len(self.chamadas), T.obter(b)["estado"]), (2, T.EXECUTADA_SEM_VERIFICACAO))

    def test_reserva_e_liberada_mesmo_quando_a_ferramenta_quebra(self):
        f = self.ferramenta_lenta(demora=0.01, falha=True)
        tid = self.tarefa(f, "rele1")
        T.executar(tid)
        self.assertEqual(C.ocupados(), [])
        self.assertEqual(T.obter(tid)["passos"][0]["estado"], "falhou")

    def test_reserva_e_liberada_se_a_preparacao_falha_depois_de_reservar(self):
        """Falha ao gravar/conferir ENTRE reservar e chamar o corretor não pode deixar o recurso preso para sempre."""
        f = self.ferramenta_lenta(demora=0.01)
        tid = self.tarefa(f, "rele1")
        with mock.patch("verificacao.antes", side_effect=RuntimeError("falhou logo depois de reservar")):
            with self.assertRaises(RuntimeError):
                T.executar_proximo(tid)
        self.assertEqual((C.ocupados(), len(self.chamadas)), ([], 0))
        self.assertTrue(C.reservar("outra", f, {"nome": "rele1"})[0], "o recurso está livre")
        C.liberar("outra")

    def test_reserva_e_liberada_quando_o_corretor_pede_confirmacao(self):
        f = self.ferramenta_lenta(demora=0.01, nivel=2)
        tid = self.tarefa(f, "rele1")
        T.executar(tid)
        self.assertEqual((T.obter(tid)["estado"], C.ocupados(), len(self.chamadas)), (T.BLOQUEADA, [], 0), "nada rodou e nada ficou preso")
        B.cancelar()

    def test_o_corretor_continua_decidindo(self):
        """Reservar não dá permissão: nível 2 continua pedindo a confirmação presa à ação, e uma reserva livre não a dispensa."""
        tid = T.criar("avisar", passos=[{"descricao": "sms", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}}])
        T.executar(tid)
        self.assertEqual((T.obter(tid)["estado"], self.sms()), (T.BLOQUEADA, 0))
        B.cancelar()

    def test_tudo_ou_nada(self):
        self.assertEqual(C.reservar("a", "ligar", {"contato": "mae"}), (True, None))
        ok, quem = C.reservar("b", "enviar_sms", {"contato": "mae"})
        self.assertEqual((ok, quem["recurso"], quem["dono"]), (False, "contato:mae", "a"))
        ok, quem = C.reservar("c", "ligar", {"contato": "outro"})
        self.assertEqual((ok, quem["recurso"]), (False, "linha_telefonica"), "duas ligações ao mesmo tempo não existem")
        self.assertEqual([o["dono"] for o in C.ocupados()], ["a"], "quem perdeu não ficou com pedaço nenhum")
        self.assertEqual(C.reservar("d", "enviar_sms", {"contato": "pai"}), (True, None))
        C.liberar("a")
        self.assertEqual(C.reservar("c", "ligar", {"contato": "outro"}), (True, None))

    def test_o_mesmo_dono_pode_reservar_de_novo(self):
        self.assertTrue(C.reservar("a", "rele", {"nome": "luz", "ligar": True})[0])
        self.assertTrue(C.reservar("a", "rele", {"nome": "luz", "ligar": False})[0])
        self.assertEqual(len(C.ocupados()), 1)

    def test_nome_e_comparado_sem_acento_nem_caixa(self):
        C.reservar("a", "enviar_sms", {"contato": "Mãe"})
        self.assertFalse(C.reservar("b", "enviar_sms", {"contato": " mae "})[0])
        self.assertTrue(C.reservar("c", "enviar_sms", {"contato": "pai"})[0])

    def test_nome_ilegivel_conflita_com_outro_ilegivel(self):
        C.reservar("a", "criar_arquivo", {"nome": 7, "conteudo": "x"})
        self.assertFalse(C.reservar("b", "criar_arquivo", {"conteudo": "y"})[0], "na dúvida, espera")

    def test_ferramenta_sem_regra_ou_args_estranhos_nao_quebram(self):
        self.assertEqual(C.recursos_de("nao_existe", {}), [])
        self.assertEqual(C.recursos_de("rele", "texto"), [("rele:?", "excl")])
        with mock.patch.dict(C.RECURSOS, {"rele": lambda a: 1 / 0}):
            self.assertEqual(C.recursos_de("rele", {}), [("rele:?", "excl")], "regra que quebra vira exclusivo, nunca livre")

    def test_toda_ferramenta_que_muda_algo_declara_seus_recursos(self):
        """Ferramenta nova de nível ≥ 1 precisa dizer em `coordenador.py` o que usa (ou por que nada)."""
        faltam = []
        for nome, f in B.FERRAMENTAS.items():
            if str(getattr(f["fn"], "__module__", "")).startswith("test"):
                continue                                          # ferramentas que outros testes registram e deixam no corretor não são do produto
            n = f["nivel"]
            if callable(n) or n >= 1:
                if nome not in C.RECURSOS and nome not in C.SEM_RECURSO:
                    faltam.append(nome)
        self.assertEqual(faltam, [])
        self.assertFalse(set(C.RECURSOS) & set(C.SEM_RECURSO))
        self.assertTrue(all(isinstance(v, str) and len(v) > 8 for v in C.SEM_RECURSO.values()), "cada exceção explica por quê")


def prop(id_, rel=0.5, urg=0.5, custo=0.1, risco=0.0, inc=0.5, **kw):
    return {"id": id_, "modulo": "teste", "relevancia": rel, "urgencia": urg, "custo": custo, "risco": risco, "incerteza": inc, **kw}


class Avaliar(Base):
    def decisoes(self, props, **kw):
        return {d["id"]: d for d in C.avaliar(props, **kw)}

    def test_nota_e_ordem(self):
        r = C.avaliar([prop("a", rel=0.2), prop("b", rel=1.0, urg=1.0, custo=0, risco=0, inc=0), prop("c", rel=0.5)])
        self.assertEqual([d["id"] for d in r], ["b", "c", "a"])
        self.assertEqual(r[0]["nota"], 0.7)
        self.assertAlmostEqual(C.nota({"relevancia": 1, "urgencia": 1, "custo": 1, "risco": 1, "incerteza": 1}), 0.4 + 0.3 - 0.1 - 0.15 - 0.05)
        self.assertEqual(r[0]["componentes"]["relevancia"], 1.0)

    def test_empate_se_resolve_pelo_id_e_o_resultado_e_estavel(self):
        r1 = [d["id"] for d in C.avaliar([prop("z"), prop("a"), prop("m")])]
        r2 = [d["id"] for d in C.avaliar([prop("m"), prop("z"), prop("a")])]
        self.assertEqual((r1, r2), (["a", "m", "z"], ["a", "m", "z"]))

    def test_I_o_que_nao_se_atrapalha_sai_junto(self):
        r = self.decisoes([prop("a", recursos=[("rele:luz", "excl")]), prop("b", recursos=[("rele:portao", "excl")]), prop("c", recursos=[("cofre", "comp")]), prop("d", recursos=[("cofre", "comp")])])
        self.assertEqual({d["decisao"] for d in r.values()}, {"executar_agora"}, "nada de fila sem necessidade")

    def test_I_conflito_a_de_nota_maior_vai_e_a_outra_espera_com_o_motivo(self):
        r = self.decisoes([prop("fraca", rel=0.3, recursos=[("rele:luz", "excl")]), prop("forte", rel=0.9, recursos=[("rele:luz", "excl")])])
        self.assertEqual((r["forte"]["decisao"], r["fraca"]["decisao"]), ("executar_agora", "esperar"))
        self.assertIn("forte", r["fraca"]["motivo"])
        self.assertIn("rele", r["fraca"]["motivo"])
        self.assertNotIn("luz", r["fraca"]["motivo"], "o motivo diz o tipo do recurso, não o nome")

    def test_exclusivo_conflita_com_compartilhado(self):
        r = self.decisoes([prop("grande", rel=0.9, recursos=[("cofre", "excl")]), prop("nota", rel=0.4, recursos=[("cofre", "comp")])])
        self.assertEqual((r["grande"]["decisao"], r["nota"]["decisao"]), ("executar_agora", "esperar"))

    def test_quem_espera_nao_segura_o_recurso_de_outra(self):
        """Se B espera por A, B não reserva nada nesta rodada: C, que só conflita com B, pode ir."""
        r = self.decisoes([prop("A", rel=0.9, recursos=[("rele:1", "excl")]), prop("B", rel=0.6, recursos=[("rele:1", "excl"), ("rele:2", "excl")]), prop("C", rel=0.3, recursos=[("rele:2", "excl")])])
        self.assertEqual([r[i]["decisao"] for i in "ABC"], ["executar_agora", "esperar", "executar_agora"])

    def test_dependencia(self):
        r = self.decisoes([prop("b", depende_de=["t0001"])])
        self.assertEqual(r["b"]["decisao"], "esperar")
        self.assertIn("t0001", r["b"]["motivo"])
        self.assertEqual(self.decisoes([prop("b", depende_de=["t0001"])], concluidas=["t0001"])["b"]["decisao"], "executar_agora")

    def test_recurso_em_uso_por_acao_em_andamento(self):
        C.reservar("t0007", "rele", {"nome": "luz", "ligar": True})
        r = self.decisoes([prop("outra", recursos=[("rele:luz", "excl")]), prop("t0007", recursos=[("rele:luz", "excl")]), prop("livre", recursos=[("rele:portao", "excl")])])
        self.assertEqual((r["outra"]["decisao"], r["livre"]["decisao"]), ("esperar", "executar_agora"))
        self.assertIn("t0007", r["outra"]["motivo"])
        self.assertEqual(r["t0007"]["decisao"], "executar_agora", "quem já tem a reserva não é barrado por ela")

    def test_F_o_que_exige_o_dono_continua_exigindo_por_mais_alta_que_seja_a_nota(self):
        r = self.decisoes([prop("sms", rel=1.0, urg=1.0, custo=0, risco=0, inc=0, precisa_dono=True)])
        self.assertEqual(r["sms"]["decisao"], "pedir_dono")
        self.assertEqual(r["sms"]["nota"], 0.7)

    def test_proposta_mal_formada_e_recusada_sem_quebrar_nada(self):
        lixos = [prop("x", rel="alto"), prop("x", rel=True), prop("x", rel=float("nan")), {"id": "x"}, {"modulo": "t", **{k: 0.1 for k in C.PESOS}}, None, 7, "texto"]
        r = C.avaliar(lixos)
        self.assertEqual(len(r), len(lixos))
        self.assertEqual({d["decisao"] for d in r}, {"recusar"})
        self.assertEqual(C.avaliar(None), [])
        self.assertEqual(C.avaliar("não é lista"), [])

    def test_componente_fora_da_faixa_e_limitado(self):
        d = C.avaliar([prop("x", rel=7, urg=-3)])[0]
        self.assertEqual((d["componentes"]["relevancia"], d["componentes"]["urgencia"]), (1.0, 0.0))

    def test_nada_e_executado_ao_avaliar(self):
        with mock.patch.object(B, "executar_estruturado", side_effect=AssertionError("avaliar não executa")), mock.patch.object(T, "executar", side_effect=AssertionError("nem tarefa")):
            C.avaliar([prop("a", recursos=[("rele:luz", "excl")])])


class DeTarefa(Base):
    def test_componentes_vem_do_que_esta_registrado(self):
        u = T.criar("pedido do dono", passos=[self.lembrete()])
        p = C.proposta_de_tarefa(T.obter(u))
        self.assertEqual((p["id"], p["modulo"], p["relevancia"], p["precisa_dono"]), (u, "tarefas", 1.0, False))
        self.assertAlmostEqual(p["custo"], 1 / T.MAX_PASSOS)
        self.assertAlmostEqual(p["risco"], 1 / 3)
        self.assertEqual(p["incerteza"], 1.0, "sem experiência nenhuma, a incerteza é total")
        propria = T.criar("dela", passos=[self.lembrete()], origem="propria")
        self.assertEqual(C.proposta_de_tarefa(T.obter(propria))["relevancia"], 0.3)

    def test_experiencia_reduz_a_incerteza(self):
        tid = T.criar("a", passos=[self.lembrete()])
        T.executar(tid)
        T.criar("b", passos=[self.lembrete(texto="outro")])
        p = C.proposta_de_tarefa(T.obter(T.listar(estados=(T.PRONTA,))[-1]["id"]))
        self.assertLess(p["incerteza"], 1.0)

    def test_nivel_2_pede_o_dono(self):
        tid = T.criar("avisar", passos=[{"descricao": "sms", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}}])
        p = C.proposta_de_tarefa(T.obter(tid))
        self.assertEqual((p["precisa_dono"], p["risco"]), (True, 2 / 3))
        self.assertEqual(self.decisoes_de(p)["decisao"], "pedir_dono")

    def decisoes_de(self, p):
        return C.avaliar([p])[0]

    def test_nivel_ilegivel_no_registro_e_tratado_como_sensivel(self):
        """Estado adulterado ou antigo: `nivel` None não pode quebrar a conta nem passar por baixo."""
        tid = T.criar("lembrar", passos=[self.lembrete()])
        t = T.obter(tid)
        for ruim in (None, "2", True, 2.5):
            with self.subTest(nivel=ruim):
                t["passos"][0]["nivel"] = ruim
                p = C.proposta_de_tarefa(t)
                self.assertEqual((p["precisa_dono"], round(p["risco"], 3)), (True, round(2 / 3, 3)))
                self.assertEqual(C.avaliar([p])[0]["decisao"], "pedir_dono")

    def test_recursos_vem_dos_argumentos_guardados_ou_sao_desconhecidos_e_exclusivos(self):
        tid = T.criar("arquivo", passos=[{"descricao": "criar", "ferramenta": "criar_arquivo", "args": {"nome": "a.txt", "conteudo": "x"}}])
        self.assertEqual(C.proposta_de_tarefa(T.obter(tid))["recursos"], [("arquivo:a.txt", "excl")])
        T._VIVOS.clear()
        t = T.obter(tid)
        t["passos"][0]["args"] = None                                     # como depois de um reinício, com argumento que não ficou guardado
        with mock.patch.object(T, "argumentos_guardados", return_value=None):
            self.assertEqual(C.proposta_de_tarefa(t)["recursos"], [("criar_arquivo:?", "excl")])

    def test_tarefas_que_batem_no_mesmo_recurso_sao_ordenadas_pelo_dono_primeiro(self):
        dono = T.criar("do dono", passos=[{"descricao": "x", "ferramenta": "criar_arquivo", "args": {"nome": "a.txt", "conteudo": "1"}}])
        dela = T.criar("dela", passos=[{"descricao": "x", "ferramenta": "criar_arquivo", "args": {"nome": "a.txt", "conteudo": "2"}}], origem="propria")
        r = {d["id"]: d for d in C.avaliar([C.proposta_de_tarefa(T.obter(dela)), C.proposta_de_tarefa(T.obter(dono))])}
        self.assertEqual((r[dono]["decisao"], r[dela]["decisao"]), ("executar_agora", "esperar"))


class Registro(Base):
    def linhas(self):
        with open(self.base(".cerebro", "coordenacao.jsonl"), encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_cada_decisao_fica_registrada_sem_conteudo(self):
        C.avaliar([prop("a", recursos=[("contato:" + SEGREDO, "excl")]), prop("b", rel=0.1, recursos=[("contato:" + SEGREDO, "excl")], motivo_extra=SEGREDO)])
        ls = self.linhas()
        self.assertEqual([(l["alvo"], l["decisao"]) for l in ls], [("a", "executar_agora"), ("b", "esperar")])
        self.assertTrue(all(l["componentes"] and l["motivo"] for l in ls))
        bruto = self.base(".cerebro", "coordenacao.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(SEGREDO, bruto, "o nome do contato vira só um código curto")
        self.assertTrue(ls[0]["recursos"][0].startswith("contato:") and len(ls[0]["recursos"][0]) == len("contato:") + 6)

    def test_decisoes_recentes_e_voz(self):
        self.assertIn("Não coordenei nada", C.tratar("o que você está coordenando?"))
        C.avaliar([prop("a"), prop("b", depende_de=["t9"])])
        r = C.decisoes_recentes(5)
        self.assertEqual([d["alvo"] for d in r], ["a", "b"])
        fala = C.tratar("O que você está coordenando?")
        self.assertIn("b: esperar", fala)
        self.assertIsNone(C.tratar("que horas são"))
        self.assertIsNone(C.tratar(None))

    def test_registro_estragado_ou_ausente_nao_derruba(self):
        self.assertEqual(C.decisoes_recentes(), [])
        self.base(".cerebro").mkdir(parents=True, exist_ok=True)
        self.base(".cerebro", "coordenacao.jsonl").write_text('lixo\n{"decisao": "x"}\n[1]\n{"decisao": "esperar", "alvo": "a", "motivo": "m", "nota": 0.1}\n', encoding="utf-8")
        self.assertEqual([d["alvo"] for d in C.decisoes_recentes()], ["a"])


class SoCoordena(unittest.TestCase):
    def test_nao_importa_o_corretor_nem_cria_threads(self):
        arv = ast.parse((RAIZ / "coordenador.py").read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arv) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(arv) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn("broker", importados)
        self.assertNotIn("subprocess", importados)
        chamadas = {n.func.attr for n in ast.walk(arv) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse({"Thread", "start", "executar", "executar_estruturado", "executar_proximo"} & chamadas, "não executa e não cria agentes concorrentes")

    def test_tarefas_nao_importa_o_coordenador(self):
        arv = ast.parse((RAIZ / "tarefas.py").read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arv) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(arv) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn("coordenador", importados, "a ligação é por T.RESERVAS, sem ciclo")

    def test_a_ia_nao_tem_ferramenta_de_coordenacao(self):
        for nome in B.FERRAMENTAS:
            self.assertNotRegex(nome, r"coorden|reserv", nome)

    def test_ao_importar_liga_a_reserva_nas_tarefas(self):
        self.assertIs(T.RESERVAS["reservar"], C.reservar)
        self.assertIs(T.RESERVAS["liberar"], C.liberar)


class NucleoObservacional(unittest.TestCase):
    """O núcleo está integrado apenas para atenção; nunca deve virar trava global."""

    def test_main_integra_nucleo_sem_substituir_o_pre_cortex_distribuido(self):
        main = (RAIZ / "main.py").read_text(encoding="utf-8")
        self.assertIn("import nucleo as NC", main)
        self.assertIn("import pre_cortex.fachada as PC", main)
        self.assertIn("chave=f\"fala:pedido:{time.time_ns()}\"", main)
        self.assertIn("PC.tratar(t)", main)

    def test_o_nucleo_e_documentado_como_observacional(self):
        self.assertTrue((RAIZ / "nucleo.py").exists())
        doc = (RAIZ.parent / "docs" / "NUCLEO.md").read_text(encoding="utf-8")
        self.assertIn("camada observacional integrada", doc)
        self.assertIn("não é um escalonador", doc)
        self.assertIn("PRECORTEX_MODO", doc)

    def test_nucleo_nunca_bloqueia_impulsos_concorrentes(self):
        import nucleo as NC
        with NC.agir("estudar"):
            self.assertTrue(NC.liberar("conversar"))
            self.assertTrue(NC.liberar("olhar"))

    def test_o_coordenador_nao_serializa_o_que_nao_conflita(self):
        C.reiniciar()
        r = C.avaliar([prop("estudar", recursos=[("cofre", "comp")]), prop("conversar", recursos=[("cofre", "comp")]), prop("olhar", recursos=[("camera", "excl")])])
        self.assertEqual({d["decisao"] for d in r}, {"executar_agora"})


if __name__ == "__main__":
    unittest.main()
