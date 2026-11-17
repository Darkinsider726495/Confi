#!/usr/bin/env python3
"""CLI local de evolução controlada FRIDAY — nenhum endpoint/API é usado."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday import evolucao as E
from friday import gerador_local as G


def _suite(nome: str, alvo_teste: str | None) -> list[list[str]]:
    if alvo_teste:
        p = Path(alvo_teste)
        if p.is_absolute() or ".." in p.parts or not str(p).startswith("tests/") or not p.is_file() or p.is_symlink():
            raise ValueError("O teste específico deve ser um arquivo regular existente dentro de tests/.")
        caminho = str(p.as_posix())
    else:
        caminho = "tests"
    if nome == "pytest":
        return [[sys.executable, "-m", "pytest", "-q", "--disable-warnings", caminho]]
    return [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="FRIDAY: fila local, testes, backup e rollback sem API")
    sub = parser.add_subparsers(dest="acao", required=True)

    sub.add_parser("alvos", help="Lista módulos que podem ser considerados para promoção")
    p = sub.add_parser("preparar", help="Coloca um arquivo .py local em quarentena")
    p.add_argument("alvo", help="Ex.: friday/memoria.py")
    p.add_argument("arquivo_candidato", help="Arquivo .py com a nova versão")
    p.add_argument("--descricao", default="")

    p = sub.add_parser("substituir", help="Gera candidato por substituição literal única")
    p.add_argument("alvo")
    p.add_argument("busca", help="Trecho original, entre aspas")
    p.add_argument("substituicao", help="Trecho novo, entre aspas")
    p.add_argument("--descricao", default="")

    sub.add_parser("fila", help="Lista candidatos pendentes; nenhum será executado")
    sub.add_parser("historico", help="Mostra eventos registrados no diário da evolução")

    p = sub.add_parser("promover", help="Valida candidato em staging e promove se tudo passar")
    p.add_argument("id")
    p.add_argument("--suite", choices=("pytest", "unittest"), default="pytest")
    p.add_argument("--teste", help="Opcional: arquivo único em tests/ (pytest)")
    p.add_argument("--timeout", type=int, default=E.TEST_TIMEOUT, help="Timeout por comando de teste em segundos (máximo 600)")

    args = parser.parse_args(argv)
    try:
        if args.acao == "alvos":
            print(json.dumps(sorted(E.ALVOS_PERMITIDOS), ensure_ascii=False, indent=2))
            return 0
        if args.acao == "preparar":
            resultado = G.preparar_arquivo(args.alvo, args.arquivo_candidato, args.descricao)
        elif args.acao == "substituir":
            resultado = G.gerar_substituicao(args.alvo, args.busca, args.substituicao, args.descricao)
        elif args.acao == "fila":
            resultado = G.listar()
        elif args.acao == "historico":
            resultado = E.historico()
        elif args.acao == "promover":
            if args.teste and args.suite != "pytest":
                raise ValueError("--teste específico só é aceito com --suite pytest.")
            resultado = G.promover(args.id, _suite(args.suite, args.teste), timeout=args.timeout)
        else:
            parser.error("ação desconhecida")
            return 2
        print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
        if isinstance(resultado, dict) and resultado.get("status") in {"bloqueado", "rejeitado", "revertido"}:
            return 1
        return 0
    except (OSError, ValueError, PermissionError, SyntaxError, TypeError) as exc:
        print(f"ERRO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
