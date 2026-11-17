import subprocess, sys, shutil, os
RAIZ = "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/copia"
MUT = [
 ("friday/curiosidade.py", "or _INJECAO.search(s) or M.sensivel(s)", "or M.sensivel(s)", "test_curiosidade.py", "limpar deixa passar ordens"),
 ("friday/curiosidade.py", "if re.search(r\"\\d{5,}\", q) or \"@\" in q or M.sensivel(q) or _INJECAO.search(q):", "if False:", "test_curiosidade.py", "consulta sem filtro"),
 ("friday/curiosidade.py", "if _nomes_de_pessoas() & set(M._tokens(q)):", "if False:", "test_curiosidade.py", "nome de pessoa vai pro buscador"),
 ("friday/curiosidade.py", "if re.search(r\"[@/\\\\<>={}|\\[\\]]|\\w\\.\\w|://\", bruto):", "if False:", "test_curiosidade.py", "link/e-mail na consulta"),
 ("friday/curiosidade.py", "t = _URL.sub(\" \", t)", "t = t", "test_curiosidade.py", "links ficam no estudo"),
 ("friday/curiosidade.py", "limpo = limpar(_resumir(tema, texto, pedido))", "limpo = _resumir(tema, texto, pedido)", "test_curiosidade.py", "estudo sem limpeza"),
 ("friday/curiosidade.py", "fracao=1.0 if pedido else 0.5", "fracao=1.0", "test_curiosidade.py", "estudo dela come toda a cota de IA"),
 ("friday/curiosidade.py", "if F.em_descanso() or t < e[\"bloq\"]", "if t < e[\"bloq\"]", "test_curiosidade.py", "estuda durante o descanso"),
 ("friday/curiosidade.py", "if not pedido and passou_do_teto(e[\"dia\"][\"n\"]):", "if False:", "test_curiosidade.py", "teto opcional ignorado"),
 ("friday/curiosidade.py", "if V.segundos_desde_conversa() < 90:", "if False:", "test_curiosidade.py", "estuda no meio da conversa"),
 ("friday/conversa.py", "if F.em_descanso() or F.em_silencio():", "if False:", "test_conversa.py", "fala no descanso/silêncio"),
 ("friday/conversa.py", "if p and t - p[\"t\"] < PENDENTE_VALE:\n        return False", "if False:\n        return False", "test_conversa.py", "empilha perguntas"),
 ("friday/conversa.py", "if time.time() - p[\"t\"] > PENDENTE_VALE:\n            return None", "if False:\n            return None", "test_conversa.py", "resposta velha vale"),
 ("friday/conversa.py", "if V.segundos_desde_conversa() < 600:", "if False:", "test_conversa.py", "puxa assunto no meio da conversa"),
 ("friday/conversa.py", "if len(f.split()) > 6:\n            return None", "if False:\n            return None", "test_conversa.py", "charada engole outros assuntos"),
 ("friday/cerebro.py", "if h and h[0][\"role\"] != \"user\":", "if False:", "test_conversa.py", "histórico começa pela IA"),
 ("friday/vida.py", "if nome not in PRIMEIRAS or nome in e[\"primeiras\"]:", "if nome not in PRIMEIRAS:", "test_vida.py", "novidade em toda vez"),
 ("friday/vida.py", "if k in PRIMEIRAS and isinstance(x, (int, float)) and 0 < x <= agora() + 60:", "if True:", "test_vida.py", "arquivo adulterado de primeiras vezes"),
 ("friday/memoria.py", "if sensivel(resumo) or sensivel(tema):", "if False:", "test_curiosidade.py", "guarda estudo sensível"),
 ("friday/neuronios.py", "and _res.get(\"esc\") == M.ESCRITAS[\"n\"]", "", "test_neuronios.py", "contador velho (sem teste dedicado?)"),
]
vivos = []
for arq, velho, novo, teste, nome in MUT:
    cam = os.path.join(RAIZ, arq)
    orig = open(cam, encoding="utf-8").read()
    if velho not in orig:
        print("NÃO ACHEI:", nome); vivos.append(nome + " (trecho não encontrado)"); continue
    open(cam, "w", encoding="utf-8").write(orig.replace(velho, novo, 1))
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", teste], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        morto = r.returncode != 0
    finally:
        open(cam, "w", encoding="utf-8").write(orig)
    print(("morta  " if morto else "VIVA!  ") + nome)
    if not morto: vivos.append(nome)
print("\nsobreviventes:", vivos)
