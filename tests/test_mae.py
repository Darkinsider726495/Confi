"""MAE — o ciclo de engenharia real: semear, identificar, hipotetizar, propor, modificar (de verdade, no
laboratório), testar, analisar (tentativa → falha → alternativa), registrar; comandos são SÓ do dono; nada
fora de .lab/ é tocado; rollback garantido quando nada funciona; estado adulterado nunca vira ação."""
import os, json, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import laboratorio as LAB
import mae as MAE


SENTINELA = os.path.join(E.TMP, "mae_fora.txt")


def rodar_ciclo(max_passos=40):
    n = 0
    v = MAE._estado()
    while v["modo"] == "ativo" and v["estado"] and n < max_passos:
        MAE._passo()
        v = MAE._estado()
        n += 1
    return n


class Base(unittest.TestCase):
    def setUp(self):
        MAE.reiniciar()
        try:
            os.remove(MAE._arq())
        except OSError:
            pass
        LAB._lab_absoluto()
        import shutil
        for raiz, dirs, arqs in os.walk(LAB.LAB_ROOT, topdown=False):
            for a in arqs:
                os.remove(os.path.join(raiz, a))
            for d in dirs:
                p = os.path.join(raiz, d)
                os.remove(p) if os.path.islink(p) else shutil.rmtree(p)
        with open(SENTINELA, "w", encoding="utf-8") as f:
            f.write("intacto")


class CicloCompleto(Base):
    def test_o_ciclo_conserta_o_defeito_de_verdade_com_tentativa_e_alternativa(self):
        """A PROVA PRÁTICA: a alteração é real (o arquivo no lab muda), a 1ª hipótese falha no teste, o
        ciclo tenta a alternativa e o teste passa; tudo fica registrado (experiência, diff, auditoria)."""
        r = MAE.tratar("inicia o modo experimental")
        self.assertIn("iniciado", r)
        rodar_ciclo()
        v = MAE._estado()
        self.assertEqual(v["modo"], "encerrado")
        self.assertEqual(v["resultado"], "sucesso")
        self.assertEqual(v["tentativas"], 2)                       # 1ª hipótese falhou, a alternativa resolveu
        self.assertEqual(v["arquivos_modificados"], [MAE.ALVO])
        self.assertTrue(v["vid_boa"])                              # ponto de rollback guardado
        # a alteração é REAL: o arquivo no laboratório agora está corrigido (não é simulação)
        codigo = LAB.ler(MAE.ALVO)
        self.assertIn("n * 2", codigo)
        self.assertNotIn("n * 2 + 1", codigo)
        self.assertNotIn("DEFEITO CONTROLADO", codigo)
        # a versão de antes do ciclo é recuperável
        self.assertEqual(LAB.ler_versao(v["vid_boa"], MAE.ALVO), MAE.SEED[MAE.ALVO])
        # e o teste de verdade passa no arquivo modificado
        ok, texto = MAE._corr("lab_testar", rel=MAE.TESTE)
        self.assertTrue(ok)
        self.assertTrue(texto.startswith("PASSOU"))
        # a experiência foi registrada com previsão × observado
        exp = v["ultima_experiencia"]
        self.assertEqual(exp["resultado"], "sucesso")
        self.assertIn("previsao", exp)
        self.assertIn("PASSOU", exp["observado"])
        self.assertEqual(exp["arquivos_modificados"], [MAE.ALVO])
        self.assertTrue(v["dif"])                                  # comparação de versões para o painel
        # auditoria registrou o ciclo
        self.assertTrue(any("mae:ciclo" in str(x) for x in B.ultimos(40)))

    def test_nada_fora_do_laboratorio_e_tocado_pelo_ciclo(self):
        MAE.tratar("inicia o modo experimental")
        rodar_ciclo()
        with open(SENTINELA, encoding="utf-8") as f:
            self.assertEqual(f.read(), "intacto")
        self.assertFalse(os.path.exists(os.path.join(E.TMP, "alvo.py")))
        self.assertEqual(sorted(LAB.listar()), [MAE.ALVO, MAE.TESTE])

    def test_hipotese_unica_errada_termina_em_rollback(self):
        """Se NENHUMA hipótese funcionar, o ciclo restaura a versão boa e registra a falha — recuperação testada."""
        with mock.patch.object(MAE, "HIPOTESES", [dict(MAE.HIPOTESES[0])]):
            MAE.tratar("inicia o modo experimental")
            rodar_ciclo()
        v = MAE._estado()
        self.assertEqual(v["resultado"], "falha")
        self.assertEqual(v["tentativas"], 1)
        self.assertEqual(LAB.ler(MAE.ALVO), MAE.SEED[MAE.ALVO])    # rollback: o código voltou ao original
        self.assertTrue(v["ultima_experiencia"])
        self.assertEqual(v["ultima_experiencia"]["resultado"], "falha")

    def test_semente_passando_de_primeira_registra_inconclusivo(self):
        com = mock.patch.dict(MAE.SEED, {MAE.ALVO: MAE.SEED[MAE.ALVO].replace("n * 2 + 1", "n * 2")})
        with com:
            MAE.tratar("inicia o modo experimental")
            rodar_ciclo()
        v = MAE._estado()
        self.assertEqual(v["resultado"], "inconclusivo")
        self.assertEqual(v["tentativas"], 0)


class DonoManda(Base):
    def test_iniciar_pausar_retomar_encerrar_sao_do_dono(self):
        r = MAE.tratar("pausa o laboratório")
        self.assertIn("não está ativo", r)                          # pausar sem estar ativo: resposta honesta
        self.assertIn("iniciado", MAE.tratar("inicia o modo experimental"))
        self.assertEqual(MAE._estado()["modo"], "ativo")
        self.assertIn("Pausado", MAE.tratar("pausar o modo experimental"))
        self.assertEqual(MAE._estado()["modo"], "pausado")
        self.assertEqual(MAE._estado()["estado"], "examinar")       # pausa guarda o estado do ciclo
        n = rodar_ciclo()
        self.assertEqual(n, 0)                                      # pausado: o ciclo NÃO avança
        self.assertIn("Retomado", MAE.tratar("retoma o laboratório"))
        rodar_ciclo()
        self.assertIn("encerrado", MAE.tratar("encerra o modo experimental"))
        self.assertEqual(MAE._estado()["modo"], "encerrado")

    def test_encerrar_no_meio_do_ciclo_rollback(self):
        MAE.tratar("inicia o modo experimental")
        MAE._passo()                                                # examinar: semeou
        MAE._passo()                                                # identificar
        self.assertIn("encerrado", MAE.tratar("encerra o modo experimental"))
        v = MAE._estado()
        self.assertEqual(v["modo"], "encerrado")
        self.assertEqual(v["estado"], "")

    def test_a_ia_nao_tem_como_mudar_o_modo(self):
        """Nenhuma ferramenta do corretor inicia/pausa/encerra o MAE: só o dono, pela conversa ou painel."""
        for nome in B.FERRAMENTAS:
            self.assertFalse(nome.startswith("mae"), nome)

    def test_consulta_de_estado_e_registros(self):
        self.assertIn("ocioso", MAE.tratar("como vai o laboratório?"))
        MAE.tratar("inicia o modo experimental")
        rodar_ciclo()
        self.assertIn("última experiência", MAE.tratar("como vai o laboratório?"))
        self.assertIn("Registros", MAE.tratar("registros do laboratório"))

    def test_o_laco_nao_muda_o_modo_nem_derruba_nada(self):
        chamadas = []
        with mock.patch.object(MAE, "time") as t:
            t.sleep.side_effect = RuntimeError("para o laço após 1 volta")
            try:
                MAE.laco(falar=chamadas.append, intervalo=0)
            except RuntimeError:
                pass
        self.assertEqual(chamadas, [])                              # encerrado: o laço não inventa atividade


class Estado(Base):
    def test_arquivo_adulterado_nunca_vira_acao(self):
        MAE.tratar("inicia o modo experimental")
        with open(MAE._arq(), "w", encoding="utf-8") as f:
            f.write('{"modo": "destruir", "estado": "destruir", "hipoteses": "nao-sou-lista", "tentativas": 99999}')
        MAE.reiniciar()
        v = MAE._estado()
        self.assertEqual(v["modo"], "encerrado")                    # modo ilegível → padrão
        self.assertEqual(v["estado"], "")
        self.assertEqual(v["hipoteses"], [])
        self.assertEqual(v["tentativas"], 0)

    def test_arquivo_ausente_comeca_do_zero(self):
        MAE.reiniciar()
        v = MAE._estado()
        self.assertEqual(v["modo"], "encerrado")
        self.assertEqual(MAE.tratar("o que voce fez no laboratorio"), "Sem registros do laboratório ainda.")

    def test_resumo_tem_os_itens_do_painel(self):
        MAE.tratar("inicia o modo experimental")
        rodar_ciclo()
        r = MAE.resumo()
        for chave in ("modo", "estado", "objetivo", "problema", "hipotese", "arquivos_analise", "arquivos_modificados",
                      "arquivos_excluidos", "teste_em_andamento", "resultado_teste", "dif", "versao", "rollback",
                      "ultima_experiencia", "historico", "recursos"):
            self.assertIn(chave, r, chave)
        self.assertEqual(r["recursos"]["raiz"], LAB.LAB_ROOT)
        self.assertGreater(r["recursos"]["versoes"], 0)             # snapshots de verdade aconteceram

    def test_passo_com_erro_vira_falha_registrada(self):
        MAE.tratar("inicia o modo experimental")
        with mock.patch.object(MAE, "_corr", side_effect=RuntimeError("boom")):
            MAE._passo()
        v = MAE._estado()
        self.assertEqual(v["estado"], "registrar")                  # erro do passo → registrar, nunca travar
        self.assertIn("erro no passo", " ".join(v["historico"]))


if __name__ == "__main__":
    unittest.main()