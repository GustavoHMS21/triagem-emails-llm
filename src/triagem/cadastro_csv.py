"""Adaptador: carrega o cadastro de condomínios e gestores a partir de CSV."""

import csv
from pathlib import Path

from triagem.cadastro import CadastroCondominios, Condominio, Gestor


def carregar_cadastro(caminho_condominios: Path, caminho_gestores: Path) -> CadastroCondominios:
    with open(caminho_condominios, encoding="utf-8", newline="") as f:
        condominios = [
            Condominio(
                id=linha["id"],
                nome=linha["nome"],
                qtd_elevadores=int(linha["qtd_elevadores"]) if linha["qtd_elevadores"].strip() else None,
            )
            for linha in csv.DictReader(f)
        ]
    por_id = {c.id: c for c in condominios}
    with open(caminho_gestores, encoding="utf-8", newline="") as f:
        gestores = [
            Gestor(
                condominio=por_id[linha["condominio_id"]],
                papel=linha["papel"].strip(),
                nome=linha["nome"].strip(),
                email=linha["email"].strip(),
            )
            for linha in csv.DictReader(f)
        ]
    return CadastroCondominios(condominios, gestores)
