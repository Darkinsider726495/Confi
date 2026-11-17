"""Mutação das defesas da Fase 2: cada mutante é aplicado numa CÓPIA do projeto e a suíte indicada TEM de falhar.
uso: python3 mutar.py <lista.py> <projeto> ; lista.py define MUTANTES = [(nome, arquivo, antigo, novo, [modulos de teste])]"""
import importlib.util, os, shutil, subprocess, sys, tempfile
lista, projeto = sys.argv[1], os.path.abspath(sys.argv[2])
spec = importlib.util.spec_from_file_location("lista", lista); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def copiar():
    d = tempfile.mkdtemp(prefix="mut-")
    cp = os.path.join(d, "p")
    shutil.copytree(projeto, cp, ignore=shutil.ignore_patterns(".git", "__pycache__", "reports", "venv*"))
    return d, cp


def rodar(cp, testes):
    return subprocess.run([sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", *testes], cwd=os.path.join(cp, "tests"), capture_output=True, text=True, timeout=600)


# Linha de base: a suíte indicada TEM de passar na cópia SEM mutação. Senão todo mutante «seria detectado» por motivo errado (ex.: arquivo que só existe fora da cópia).
d0, cp0 = copiar()
for testes in sorted({tuple(x[4]) for x in m.MUTANTES}):
    b = rodar(cp0, testes)
    if b.returncode != 0:
        print("LINHA DE BASE FALHOU para", " ".join(testes)); print(b.stderr[-1500:]); sys.exit(2)
    print("linha de base ok:", " ".join(testes))
shutil.rmtree(d0, ignore_errors=True)
ok = morto = 0
for nome, arq, antigo, novo, testes in m.MUTANTES:
    d = tempfile.mkdtemp(prefix="mut-")
    cp = os.path.join(d, "p")
    shutil.copytree(projeto, cp, ignore=shutil.ignore_patterns(".git", "__pycache__", "reports", "venv*"))
    f = os.path.join(cp, arq)
    s = open(f, encoding="utf-8").read()
    pares = list(zip(antigo, novo)) if isinstance(antigo, (list, tuple)) else [(antigo, novo)]   # várias trocas no mesmo arquivo: defesas em camadas só aparecem quebrando todas
    if any(a not in s for a, _ in pares):
        print(f"[NÃO APLICADO] {nome}: trecho não encontrado em {arq}"); continue
    for a, n in pares:
        s = s.replace(a, n, 1)
    open(f, "w", encoding="utf-8").write(s)
    r = rodar(cp, testes)
    detectado = r.returncode != 0
    redundante = nome.startswith("[redundante]")          # camada que outra camada já cobre: sobreviver é o esperado e fica dito
    if not redundante:
        ok += 1
        morto += detectado
    resumo = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))][:2]
    rotulo = ("DETECTADO" if detectado else "SOBREVIVEU (esperado: camada redundante)") if redundante else ("DETECTADO" if detectado else "SOBREVIVEU")
    print(f"[{rotulo}] {nome}  {' | '.join(resumo)[:150]}")
    shutil.rmtree(d, ignore_errors=True)
print(f"\n{morto} de {ok} mutantes detectados")
sys.exit(0 if morto == ok else 1)
