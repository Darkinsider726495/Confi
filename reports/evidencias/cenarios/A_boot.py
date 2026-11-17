import sys, os, subprocess, time, json, http.client, signal
sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb
base = sys.argv[1]; env = amb.preparar(base, vida="1"); env.update(HUD_PORTA="18091", HUD_HOST="127.0.0.1", PYTHONDONTWRITEBYTECODE="1", PATH=os.environ["PATH"], HOME=base)
e = {**{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG")}, **env}
p = subprocess.Popen([sys.executable, amb.COPIA + "/friday/main.py", "--teclado"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=e, cwd=base)
time.sleep(1.0); p.stdin.write("lembre que meu time é o Corinthians\n"); p.stdin.flush(); time.sleep(1.5)
p.stdin.write("quantos neurônios você tem\n"); p.stdin.flush(); time.sleep(1.5)
p.stdin.write("o que você lembra sobre time\n"); p.stdin.flush(); time.sleep(3.0)
tok = open(base + "/token").read().strip() if os.path.exists(base + "/token") else ""
def get(path, tok=None):
    c = http.client.HTTPConnection("127.0.0.1", 18091, timeout=5); c.request("GET", path, headers={"X-Friday-Token": tok} if tok else {}); r = c.getresponse(); b = r.read(); return r.status, b
print("GET /saude:", get("/saude")[0], "| /state sem chave:", get("/state")[0])
st, b = get("/state", tok); s = json.loads(b) if st == 200 else {}
print("GET /state com chave:", st, "| chaves do estado:", sorted(s)[:40])
print("threads do processo:", len(os.listdir(f"/proc/{p.pid}/task")))
print("vitais (laços que já bateram):", (s.get("vida") or {}).get("vitais"))
print("ferramentas registradas:", s.get("ferramentas"), "| modo IA:", s.get("ia"), "| memória:", {k: s["memoria"].get(k) for k in ("neuronios", "sinapses")} if s.get("memoria") else None)
p.send_signal(signal.SIGTERM)
try: out, _ = p.communicate(timeout=8)
except Exception: p.kill(); out, _ = p.communicate()
print("--- saída do processo (início) ---"); print("\n".join(out.splitlines()[:16])[:1800])
print("código de saída:", p.returncode, "| Traceback na saída?", "Traceback" in out)
