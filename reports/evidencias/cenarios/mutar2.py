import subprocess, sys, os
RAIZ = "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/copia"
V, NA, SL, SB, AU = "test_visao.py", "test_nunca_apaga.py", "test_sinapses_sem_limite.py", "test_sem_botao_de_desligar.py", "test_autonomia.py"
MUT = [
 ("friday/visao.py", "if f in _VAGAS or PESSOAS.search(f) or M.sensivel(s):", "if f in _VAGAS or M.sensivel(s):", V, "palavra de pessoa vira «coisa»"),
 ("friday/visao.py", "if CUR._nomes_de_pessoas() & set(M._tokens(f)):", "if False:", V, "nome de pessoa vira «coisa»"),
 ("friday/visao.py", "if not PESSOAS.search(M._fold(s)))", "if True)", V, "frase sobre pessoas fica na cena"),
 ("friday/visao.py", "return buf.getvalue(), \"image/jpeg\", escura", "return dados, \"image/jpeg\", escura", V, "EXIF/GPS vai junto (com Pillow)"),
 ("friday/visao.py", "dados = _sem_metadados_jpeg(dados)", "dados = dados", V, "EXIF/GPS vai junto (sem Pillow)"),
 ("friday/visao.py", "if ev is None or time.time() - _nav[\"pedido\"] > ESPERA_NAVEGADOR + 5 or not _tipo(bytes(dados[:16])):", "if not _tipo(bytes(dados[:16])):", V, "aceita imagem que ninguém pediu"),
 ("friday/visao.py", "if M.sensivel(cena_bruta + \" \" + \" \".join(brutas)):", "if False:", V, "guarda cena com dado sensível"),
 ("friday/visao.py", "igual = len(a & b) / max(1, len(a | b)) >= 0.8", "igual = False", V, "cena repetida enche o cofre"),
 ("friday/visao.py", "if not _nav[\"dono\"] or _nav[\"dono\"] == painel or agora - _nav[\"dono_visto\"] > 3.0:", "if True:", V, "todo painel abre a câmera"),
 ("friday/visao.py", "if F.em_descanso() or F.em_silencio() or t < e[\"bloq\"] or pedido_pendente():", "if t < e[\"bloq\"] or pedido_pendente():", V, "olha no descanso/silêncio"),
 ("friday/visao.py", "if V.segundos_desde_conversa() < 60:", "if False:", V, "olha no meio da conversa"),
 ("friday/memoria.py", "return ROTULO_ESTUDO in str(texto) or ROTULO_VISAO in str(texto)", "return ROTULO_ESTUDO in str(texto)", V, "o que veio da câmera não contamina o pedido"),
 ("friday/cerebro.py", "os.getenv(\"VISAO_NUVEM\", \"1\") != \"0\" and ", "", V, "VISAO_NUVEM=0 ignorado"),
 ("friday/main.py", "if not 0 < n <= LIM_IMAGEM:", "if False:", V, "imagem de qualquer tamanho"),
 ("friday/main.py", "if not self.headers.get(\"Content-Type\", \"\").startswith(\"image/\"):", "if False:", V, "aceita qualquer tipo em /olhar"),
 ("friday/neuronios.py", "_adormecer(k, [w, _num(e[\"sin\"][k], 1)])\n            del e[\"sin\"][k]", "del e[\"sin\"][k]", NA, "sinapse fraca é apagada em vez de adormecer"),
 ("friday/neuronios.py", "ACORDAR_BONUS = 0.5", "ACORDAR_BONUS = 0.0", NA, "relembrar não acorda com vantagem"),
 ("friday/neuronios.py", "LIMIAR_LINK = 3.0", "LIMIAR_LINK = 3.0\nos.unlink", NA, "código ganha um apagar arquivo"),
 ("friday/neuronios.py", "if limite and len(e[chave]) > limite:", "if len(e[chave]) > 4000:", SL, "teto de 4000 sinapses volta"),
 ("friday/neuronios.py", "MAX_SINAPSES, MAX_USO, MAX_DESC = _teto(\"MAX_SINAPSES\")", "MAX_SINAPSES, MAX_USO, MAX_DESC = 4000", SL, "teto padrão de sinapses volta"),
 ("friday/neuronios.py", "key=lambda x: -x[2])   # TODAS", "key=lambda x: -x[2])[:1500]   # TODAS", SL, "painel recebe só 1500 sinapses"),
 ("friday/neuronios.py", "DESC_DIA = _teto(\"DESC_NOITE\"), _teto(\"DESC_CICLO\"), _teto(\"DESC_DIA\")", "DESC_DIA = 40, 3, 60", SL, "limite de descobertas volta"),
 ("friday/neuronios.py", "if MAX_DESC and len(e[\"desc\"]) > MAX_DESC:", "if len(e[\"desc\"]) > 800:", SL, "candidatas apagadas acima de 800"),
 ("friday/neuronios.py", "if HOMEOSTASE_CAP <= 0:\n        return 0", "pass", SL, "CEREBRO_HOMEOSTASE=0 ignorado"),
 ("friday/main.py", "r = _desligar(t)  #", "r = None  #", SB, "«desligue-se» vai para a IA"),
 ("friday/main.py", "    if p == \"/saude\":", "    if p == \"/parar\":\n            os._exit(0)\n        if p == \"/saude\":", SB, "rota que desliga o processo"),
 ("friday/hud.html", "try{localStorage.removeItem('friday_escuta')}catch(_){}", "try{localStorage.setItem('friday_escuta','pausada')}catch(_){}", SB, "pausa da escuta volta ao painel"),
 ("friday/hud.html", "function escutar(){if(modo=='continuo')return;", "function escutar(){if(modo=='continuo'){parar();return}", SB, "tocar no aviso pausa a escuta"),
 ("termux/parar.sh", "kill -TERM \"$pid\" 2>/dev/null\n", "true\n", AU, "parar.sh não para o supervisor"),
 ("termux/supervisor.sh", "sleep \"$CHECK\" & wait $!", "sleep \"$CHECK\"", AU, "parada espera o intervalo de verificação"),
]
vivos = []
for arq, velho, novo, teste, nome in MUT:
    cam = os.path.join(RAIZ, arq)
    orig = open(cam, encoding="utf-8").read()
    if orig.count(velho) < 1:
        print("NÃO ACHEI:", nome); vivos.append(nome + " (trecho não encontrado)"); continue
    open(cam, "w", encoding="utf-8").write(orig.replace(velho, novo, 1))
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", teste], cwd=RAIZ, capture_output=True, text=True, timeout=400)
        morto = r.returncode != 0
    finally:
        open(cam, "w", encoding="utf-8").write(orig)
    print(("morta  " if morto else "VIVA!  ") + nome, flush=True)
    if not morto: vivos.append(nome)
print("\nsobreviventes:", vivos)
