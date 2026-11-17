import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M
pasta = M.base() / "Memorias"; pasta.mkdir(parents=True, exist_ok=True)
cab = "---\ntipo: fato\ncriado: 2026-10-01T10:00:00-03:00\nimportancia: 3\norigem: usuario\ntags: [friday, memoria, fato]\n---\n"
N_ = 3200
for i in range(N_):
    nome = f"Nota {i:05d}"
    corpo = "assunto comum de enchimento" if i not in (10, 3150) else ("zeppelinalfa unico" if i == 10 else "zeppelinomega unico")
    (pasta / f"{nome}.md").write_text(f"{cab}# {nome}\n\n{corpo}\n", encoding="utf-8")
print("notas no cofre:", len(list(pasta.glob('*.md'))), "| MAX_ARQUIVOS:", M.MAX_ARQUIVOS)
print("busca 'zeppelinalfa' (nota 10, início da ordem):", [x["titulo"] for x in M.buscar("zeppelinalfa", 3)])
print("busca 'zeppelinomega' (nota 3150, depois do teto):", [x["titulo"] for x in M.buscar("zeppelinomega", 3)])
