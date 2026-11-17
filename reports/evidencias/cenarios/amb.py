"""Ambiente isolado dos cenários da auditoria. Tudo numa pasta-base passada pelo script; nada toca o projeto, o cofre real nem a internet.
Dois processos que usam a mesma base compartilham o cofre, o estado e a trilha de auditoria (é o que permite testar «reiniciar»)."""
import os, sys, json
COPIA = "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/copia"
def preparar(base, vida="0", extra=None):
    os.makedirs(base, exist_ok=True)
    env = dict(FRIDAY_DB=f"{base}/t.db", FRIDAY_AUDITORIA=f"{base}/aud.jsonl", FRIDAY_PIN="4321", RELES="luz:17:1,portao:27:3,tomada:22:2",
               FRIDAY_PLATAFORMA="android", FRIDAY_DOCS=f"{base}/docs", FRIDAY_TOKEN_ARQ=f"{base}/token", FRIDAY_AUTONOMIA_ARQ=f"{base}/autonomia.json",
               FRIDAY_DIAG_ARQ=f"{base}/diag.txt", FRIDAY_HEARTBEAT=f"{base}/hb", CONTATOS="mae:+5511999990001,Sócio:(11) 98888-0002", SILENCIO="", DESCANSO="",
               OBSIDIAN_VAULT=f"{base}/cofre", FRIDAY_VIDA=vida, VISAO_FONTE="off", IA_MODO="local", OLLAMA_URL="http://127.0.0.1:9", OLLAMA_TIMEOUT="1")
    for k in ("ANTHROPIC_API_KEY", "NTFY_URL", "NTFY_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "BRAVE_API_KEY"):
        os.environ.pop(k, None)
    env.update(extra or {})
    os.environ.update(env)
    sys.path.insert(0, COPIA + "/friday")
    return env
def mostra(titulo, **kv):
    print(f"## {titulo}")
    for k, v in kv.items():
        print(f"   {k}: {json.dumps(v, ensure_ascii=False, default=str)[:400]}")
