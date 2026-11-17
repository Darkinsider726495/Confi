"""Modelo de teste para um módulo local futuro; não importa nada se ele ainda não existe."""
import pytest


def test_harness_disponivel():
    assert True


def test_funcao_gerada():
    pytest.importorskip("friday.generated.exemplo_local")
    from friday.generated.exemplo_local import calcular
    assert calcular(2) == 4
