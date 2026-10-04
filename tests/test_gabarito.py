"""Integridade do dataset de avaliação: um erro de digitação no gabarito
estragaria a avaliação em silêncio."""

import csv
import typing
from pathlib import Path

from triagem.entrada import FonteJson
from triagem.modelos import Categoria

AMOSTRA = Path("data/amostras/emails_setembro.json")
GABARITO = Path("data/amostras/gabarito_setembro.csv")


def _gabarito() -> list[dict]:
    with open(GABARITO, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_todo_email_da_amostra_tem_exatamente_um_rotulo():
    ids_amostra = [e.id for e in FonteJson(AMOSTRA).ler()]
    ids_gabarito = [linha["id"] for linha in _gabarito()]
    assert sorted(ids_gabarito) == sorted(ids_amostra)
    assert len(ids_gabarito) == len(set(ids_gabarito))


def test_niveis_e_categorias_sao_valores_validos():
    categorias = set(typing.get_args(Categoria))
    for linha in _gabarito():
        assert linha["nivel_esperado"] in {"urgente", "importante", "normal"}, linha["id"]
        assert set(linha["categorias_aceitas"].split("|")) <= categorias, linha["id"]
