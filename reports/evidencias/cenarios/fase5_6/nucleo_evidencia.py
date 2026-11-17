"""Evidência para a decisão sobre `friday/nucleo.py` (Fase 5). Só lê e executa o módulo em memória; não altera nada no projeto.

Uso (da raiz do projeto):  python3 reports/evidencias/cenarios/fase5_6/nucleo_evidencia.py

Mostra, com números:
  1. quem importa `nucleo` no código e nos testes (esperado: ninguém);
  2. o que `nucleo.liberar()` faz com dois impulsos (um age, o outro espera; e há 20 s de pausa depois) — o contrário da decisão do dono;
  3. o que o foco de 7 vagas faz com 12 sinais notados (o excedente sai do foco);
  4. o mesmo cenário de dois impulsos sem conflito no coordenador: os dois saem juntos.
"""
import ast, os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RAIZ / "friday"))
os.environ["FRIDAY_VIDA"] = "0"
_TMP = tempfile.mkdtemp(prefix="friday-nucleo-evid-")
os.environ["OBSIDIAN_VAULT"] = os.path.join(_TMP, "cofre")      # o coordenador grava a decisão num cofre: aqui, um temporário (nada do cofre real é tocado)
os.environ["FRIDAY_DB"] = os.path.join(_TMP, "t.db")
os.environ["FRIDAY_AUDITORIA"] = os.path.join(_TMP, "aud.jsonl")


def importadores():
    achados = []
    for pasta in ("friday", "tests", "termux", "servidor"):
        for arq in sorted((RAIZ / pasta).rglob("*.py")) if (RAIZ / pasta).exists() else []:
            if arq.name == "nucleo.py":
                continue
            try:
                arv = ast.parse(arq.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for n in ast.walk(arv):
                nomes = [a.name for a in n.names] if isinstance(n, ast.Import) else ([n.module or ""] + [a.name for a in n.names]) if isinstance(n, ast.ImportFrom) else []
                if any(x.split(".")[0] == "nucleo" for x in nomes):
                    achados.append(f"{arq.relative_to(RAIZ)}:{n.lineno}")
    return achados


print("== 1. quem importa nucleo.py")
imp = importadores()
print("importadores:", imp or "ninguém")
print("main.py inicia o núcleo?", "nucleo" in (RAIZ / "friday" / "main.py").read_text(encoding="utf-8"))

import nucleo as NU  # noqa: E402

print("\n== 2. seleção de impulsos (relógio controlado, 20 s de inibição padrão)")
NU.zerar_para_teste()
t0 = 1_000_000.0
with NU.agir("estudar"):
    print("estudar agindo -> pode conversar?", NU.liberar("conversar", t0 + 1), "| pode olhar?", NU.liberar("olhar", t0 + 1))
    print("esperando:", NU.esperando(t0 + 1))
fim = NU._fim["estudar"]
print("estudar terminou; 5 s depois, pode conversar?", NU.liberar("conversar", fim + 5))
print("30 s depois, pode conversar?", NU.liberar("conversar", fim + 30))

print("\n== 3. foco com vagas limitadas (7 por padrão)")
NU.zerar_para_teste()
for i in range(12):
    NU.perceber("fala", f"pedido{i}", f"pedido {i}", chave=f"fala:{i}", agora=t0 + i)
p = NU.painel(t0 + 12)
print(f"sinais notados={p['notados']} no foco={len(p['foco'])} (vagas={p['vagas']}) saíram do foco={p['saiu']}")

print("\n== 4. o mesmo caso no coordenador (dois impulsos sem conflito de recurso)")
import coordenador as CO  # noqa: E402

CO.reiniciar()
d = CO.avaliar([
    {"id": "estudar", "modulo": "curiosidade", "relevancia": 0.5, "urgencia": 0.3, "custo": 0.2, "risco": 0.0, "incerteza": 0.5, "recursos": [("cofre", "comp")]},
    {"id": "conversar", "modulo": "conversa", "relevancia": 0.4, "urgencia": 0.3, "custo": 0.1, "risco": 0.0, "incerteza": 0.5, "recursos": [("cofre", "comp")]},
])
for x in d:
    print(f"{x['id']}: {x['decisao']} — {x['motivo']}")
