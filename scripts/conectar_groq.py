#!/usr/bin/env python3
"""Conecta a FRIDAY à Groq (LLM grande na nuvem) com um comando, no celular:

    python scripts/conectar_groq.py

- Pede a chave ESCONDIDA (não aparece na tela nem fica no histórico do terminal).
- Grava só IA_PROVEDOR=groq e GROQ_API_KEY no .env, mantendo o resto do arquivo como está; cria o .env a partir do .env.example se faltar.
- Deixa o .env legível só por você (chmod 600). O .env não vai para o git (.gitignore).
- Testa a conexão com uma pergunta curta e diz se funcionou. A chave nunca é impressa (só os 4 últimos caracteres).
"""
import getpass
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAVE_RE = re.compile(r"^gsk_[A-Za-z0-9]{20,}$")


def mascarar(chave):
    return "…" + chave[-4:] if len(chave) >= 4 else "…"


def gravar(env, valores):
    """Troca (ou acrescenta) as linhas `NOME=` do .env, sem mexer no resto. Linhas comentadas «# NOME=» também são substituídas."""
    if not env.exists():
        exemplo = env.with_name(".env.example")
        env.write_text(exemplo.read_text(encoding="utf-8") if exemplo.exists() else "", encoding="utf-8")
    linhas = env.read_text(encoding="utf-8").splitlines()
    feitos = set()
    for i, l in enumerate(linhas):
        m = re.match(r"^\s*#?\s*([A-Z_][A-Z0-9_]*)\s*=", l)
        if m and m.group(1) in valores and m.group(1) not in feitos:
            linhas[i] = f"{m.group(1)}={valores[m.group(1)]}"
            feitos.add(m.group(1))
        elif m and m.group(1) in feitos and not l.lstrip().startswith("#"):
            linhas[i] = "# " + l                       # duplicata ativa: comenta para não brigar com a linha nova
    for k, v in valores.items():
        if k not in feitos:
            linhas.append(f"{k}={v}")
    env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    try:
        os.chmod(env, 0o600)
    except OSError:
        pass


def testar():
    sys.path.insert(0, str(ROOT / "friday"))
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass
    from provedor_groq import responder, GroqError
    try:
        r = responder([{"role": "user", "content": "Responda só: conectada."}], sistema="Você é a FRIDAY. Responda em português do Brasil.", max_tokens=10)
    except GroqError as e:
        return False, str(e)
    except Exception as e:                              # rede fora, DNS etc.: mensagem sem a chave
        return False, f"{type(e).__name__}"
    return bool(r), (r or "resposta vazia")


def main(argv=None, entrada=getpass.getpass, env=None):
    env = env or (ROOT / ".env")
    chave = entrada("Cole a chave da Groq (gsk_…) e aperte Enter — ela não aparece na tela: ").strip()
    if not CHAVE_RE.match(chave):
        print("Isso não parece uma chave da Groq (começa com gsk_ e tem letras e números). Nada foi gravado.")
        return 2
    gravar(env, {"IA_PROVEDOR": "groq", "GROQ_API_KEY": chave})
    print(f"Chave {mascarar(chave)} gravada no .env (só você lê o arquivo). Testando a conexão…")
    ok, msg = testar()
    if ok:
        print(f"✅ Conectada! A Groq respondeu: {msg}\nReinicie a FRIDAY para ela passar a usar o modelo grande.")
        return 0
    print(f"❌ Não consegui falar com a Groq: {msg}\nConfira a internet e se a chave foi criada certinho (ou crie outra). A chave ficou gravada; rode de novo para trocar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
