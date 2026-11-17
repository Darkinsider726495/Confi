"""Mede a busca da memória com vários tamanhos de cofre (instrumento, não faz parte da suíte: o nome não começa com test_).

  python3 tests/bench_busca.py            # 500, 2000, 5000 e 20000 notas
  python3 tests/bench_busca.py 1000 8000  # tamanhos à escolha

Tudo roda em pasta temporária (tests/_ambiente.py). Cada tamanho mede:
  frio     = primeira busca (cache de notas vazio)
  quente   = mesma busca de novo (cache preenchido)
  contexto = contexto_completo(), o bloco de memória que entra no prompt a cada pedido
  agulha   = a nota que só existe no FIM da ordem alfabética é encontrada? (antes: nunca, passado de 3.000)
Os números dependem da máquina; o que importa é comparar antes × depois no mesmo lugar.
"""
import os, random, sys, tempfile, time
import _ambiente as E
import memoria as M

CAB = "---\ntipo: fato\ncriado: 2026-10-01T10:00:00-03:00\nimportancia: 3\norigem: usuario\ntags: [friday, memoria, fato]\n---\n"


def popular(n, rng):
    vocab = [f"palavra{i:04d}" for i in range(3000)]
    pasta = M.base() / "Memorias"
    pasta.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        corpo = " ".join(rng.choice(vocab) for _ in range(60))
        if i == n - 1:
            corpo += " zeppelinomega agulha"
        (pasta / f"Nota {i:06d}.md").write_text(f"{CAB}# Nota {i:06d}\n\n{corpo}\n", encoding="utf-8")
    conv = M.base() / "Conversas"
    conv.mkdir(parents=True, exist_ok=True)
    for d in range(1, 29):
        (conv / f"2026-10-{d:02d}.md").write_text(f"# 2026-10-{d:02d}\n\n- 10:00 **Você**: conversa recente número {d} sobre palavra0001\n", encoding="utf-8")


def ms(f):
    t = time.perf_counter()
    r = f()
    return (time.perf_counter() - t) * 1000, r


def medir(n):
    os.environ["OBSIDIAN_VAULT"] = tempfile.mkdtemp(prefix="cofre-bench-", dir=E.TMP)   # um cofre novo por tamanho (nada é apagado)
    M._cache.clear()
    popular(n, random.Random(7))
    M._cache.clear()
    frio, _ = ms(lambda: M.buscar("palavra0001 palavra0002", 5))
    quente, _ = ms(lambda: M.buscar("palavra0001 palavra0002", 5))
    ctx, _ = ms(lambda: M.contexto_completo("palavra0001 palavra0002"))
    _, ag = ms(lambda: M.buscar("zeppelinomega", 3))
    _, rec = ms(lambda: M.buscar("conversa recente número 28", 3))
    achou_conv = any(x["origem"] == "Conversas" for x in rec)
    print(f"{n + 28:>6} arquivos | frio {frio:7.0f} ms | quente {quente:7.0f} ms | contexto {ctx:7.0f} ms | "
          f"agulha(última nota): {'achou' if ag else 'NÃO achou'} | conversa recente: {'achou' if achou_conv else 'NÃO achou'}")


if __name__ == "__main__":
    tam = [int(a) for a in sys.argv[1:]] or [500, 2000, 5000, 20000]
    print(f"MAX_ARQUIVOS={getattr(M, 'MAX_ARQUIVOS', 'n/d')}  CEREBRO_MAX_ARQUIVOS={os.getenv('CEREBRO_MAX_ARQUIVOS', '(não definido)')}")
    for n in tam:
        medir(n)
