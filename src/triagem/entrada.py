"""Etapa 0: de onde vêm os e-mails.

O resto do pipeline só conhece o protocolo FonteEmails. Para ler do Gmail,
basta criar uma FonteGmail com o mesmo método `ler()`, sem mexer nas outras etapas.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from triagem.modelos import Email


class FonteEmails(Protocol):
    def ler(self) -> Iterator[Email]: ...


class FonteJson:
    """Lê um arquivo .json (lista de e-mails) ou uma pasta com vários .json."""

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)

    def ler(self) -> Iterator[Email]:
        arquivos = sorted(self.caminho.glob("*.json")) if self.caminho.is_dir() else [self.caminho]
        for arquivo in arquivos:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            for item in dados if isinstance(dados, list) else [dados]:
                yield Email.model_validate(item)
