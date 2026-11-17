"""Mutação das defesas da Fase 1: cada mutante é aplicado numa CÓPIA do projeto e a suíte indicada TEM de falhar.
uso: python3 mutar_fase1.py <lista.py> <projeto> ; lista.py define MUTANTES = [(nome, arquivo, antigo, novo, [modulos de teste])]"""
import importlib.util, os, shutil, subprocess, sys, tempfile
lista, projeto = sys.argv[1], os.path.abspath(sys.argv[2])
spec = importlib.util.spec_from_file_location("lista", lista); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ok = morto = 0
for nome, arq, antigo, novo, testes in m.MUTANTES:
    d = tempfile.mkdtemp(prefix="mut-")
    cp = os.path.join(d, "p")
    shutil.copytree(projeto, cp, ignore=shutil.ignore_patterns(".git", "__pycache__", "reports", "venv*"))
    f = os.path.join(cp, arq)
    s = open(f, encoding="utf-8").read()
    if antigo not in s:
        print(f"[NÃO APLICADO] {nome}: trecho não encontrado em {arq}"); continue
    open(f, "w", encoding="utf-8").write(s.replace(antigo, novo, 1))
    r = subprocess.run([sys.executable, "-W", "error::ResourceWarning", "-m", "unittest", *testes], cwd=os.path.join(cp, "tests"), capture_output=True, text=True, timeout=600)
    detectado = r.returncode != 0
    ok += 1
    morto += detectado
    resumo = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))][:2]
    print(f"[{'DETECTADO' if detectado else 'SOBREVIVEU'}] {nome}  {' | '.join(resumo)[:150]}")
    shutil.rmtree(d, ignore_errors=True)
print(f"\n{morto} de {ok} mutantes detectados")
sys.exit(0 if morto == ok else 1)
