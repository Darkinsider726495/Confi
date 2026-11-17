"""Promoção automática opcional de candidatos locais, com a política de evolucao.py.

Opt-in explícito: FRIDAY_AUTO_PROMOTE=yes. Usa apenas testes fixos do repositório,
nunca um comando fornecido pelo candidato ou por requisição HTTP. Candidatos continuam
limitados pela allowlist de evolucao.py; esse mecanismo não copia código para a rede.
"""
from __future__ import annotations
import os
import sys
from . import evolucao, gerador_local

def processar_fila(timeout: int = 120) -> list[dict]:
    if os.getenv("FRIDAY_AUTO_PROMOTE", "").strip().lower() not in {"yes", "true", "1"}:
        return [{"status": "desativado", "motivo": "Defina FRIDAY_AUTO_PROMOTE=yes para ativar."}]
    # Comando de teste fixo, sem shell. Candidatos não podem escolher o comando.
    testes = [[sys.executable, "-m", "pytest", "-q", "tests/test_evolucao.py", "tests/test_gerador_local.py", "tests/test_api_evolutiva.py"]]
    resultados = []
    for item in gerador_local.listar():
        if item.get("estado") not in {"pendente", "candidato", "aguardando", "aguardando_testes"}:
            continue
        try:
            # Verifica allowlist/sintaxe antes de iniciar testes e promoção.
            manifesto, conteudo = gerador_local.obter(item["id"])
            evolucao.validar_candidato(manifesto["alvo"], conteudo)
            resultado = gerador_local.promover(item["id"], testes, timeout=timeout)
            resultados.append({"id": item["id"], "alvo": manifesto["alvo"], **resultado})
        except Exception as exc:
            resultados.append({"id": item.get("id"), "status": "bloqueado", "motivo": f"{type(exc).__name__}: {exc}"[:500]})
    return resultados

if __name__ == "__main__":
    import json
    print(json.dumps(processar_fila(), ensure_ascii=False, indent=2, default=str))
