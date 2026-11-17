"""DEMO do MAE (prova prática): o ciclo de engenharia REAL, do início ao fim, sem simulação.

O que você vê aqui, tudo de verdade:
  1. a semente com DEFEITO CONTROLADO é criada no laboratório (.lab/ isolado, caminho validado);
  2. o teste designado roda num subprocess confinado e FALHA, mostrando o defeito;
  3. ela formula a hipótese 1, EDITA o arquivo no laboratório e testa: a hipótese NÃO resolve;
  4. ela desfaz a tentativa, formula a hipótese 2 (alternativa), edita e testa: PASSA;
  5. a experiência é registrada (previsão × observado), com diff de versões e auditoria;
  6. cenário de recuperação: com apenas a hipótese errada disponível, o ciclo falha e o ROLLBACK
     devolve a versão boa — provando que a recuperação funciona;
  7. nada fora do laboratório é tocado (sentinela intacta).

Rode: python3 tests/demo_mae.py"""
import _ambiente as E
import broker as B, catalogo  # noqa: F401  (registro das ferramentas no corretor)
import laboratorio as LAB
import mae as MAE
from unittest import mock

LIN = "─" * 78


def passo_a_passo(titulo):
    print(f"\n{LIN}\n{titulo}\n{LIN}")
    MAE.tratar("inicia o modo experimental")
    i = 0
    while MAE._estado()["modo"] == "ativo" and MAE._estado()["estado"] and i < 40:
        antes = MAE._estado()["estado"]
        MAE._passo()
        v = MAE._estado()
        anot = v["historico"][-1] if v["historico"] else ""
        print(f"  [{antes:>12}] {anot.split(' ', 1)[-1]}")
        i += 1


print(LIN)
print("DEMO MAE — Modo de Autonomia de Engenharia (tudo em pasta temporária isolada)")
print(f"Laboratório: {LAB.LAB_ROOT}")
print(LIN)
print("\nA semente (módulo alvo com defeito controlado):")
print(MAE.SEED[MAE.ALVO])

passo_a_passo("CICLO 1 — defeito real, hipótese errada, alternativa, sucesso")

v = MAE._estado()
print(f"\nResultado: {v['resultado']} em {v['tentativas']} tentativa(s)")
print(f"\nO módulo alvo AGORA (dentro do laboratório, alterado de verdade):")
print(LAB.ler(MAE.ALVO))
print(f"Experiência registrada:")
for k, x in v["ultima_experiencia"].items():
    print(f"  {k}: {str(x)[:160]}")
print(f"\nDiferença de versões (o que ela mudou):")
print(v["dif"] or "(—)")
print(f"Rollback disponível na versão: {v['vid_boa']} (conteúdo original recuperável: "
      f"{LAB.ler_versao(v['vid_boa'], MAE.ALVO) == MAE.SEED[MAE.ALVO]})")

with open(E.TMP + "/sentinela.txt", "w", encoding="utf-8") as f:
    f.write("nada aqui pode ser tocado")
with mock.patch.object(MAE, "HIPOTESES", [dict(MAE.HIPOTESES[0])]):
    passo_a_passo("CICLO 2 — só a hipótese ERRADA existe: o ciclo falha e o ROLLBACK recupera")
v = MAE._estado()
print(f"\nResultado: {v['resultado']} — e o arquivo no laboratório voltou ao original? "
      f"{LAB.ler(MAE.ALVO) == MAE.SEED[MAE.ALVO]}")
with open(E.TMP + "/sentinela.txt", encoding="utf-8") as f:
    print(f"Sentinela fora do laboratório intacta? {f.read() == 'nada aqui pode ser tocado'}")

print(f"\nAuditoria (fatos, não conteúdo) — eventos do laboratório e do MAE:")
for ev in B.ultimos(60):
    s = str(ev)
    if "lab_" in s or "mae:" in s:
        print("  " + s[:170])
print(LIN)
print("Fim da demo. O painel (HUD) mostra os mesmos dados ao vivo: seção «Laboratório (MAE)».")