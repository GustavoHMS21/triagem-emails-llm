"""Dados de referência: condomínios e seus gestores (síndico e subsíndico).

Só estrutura e busca, sem I/O. De onde os dados vêm é problema dos
adaptadores (hoje cadastro_csv.py; amanhã, por exemplo, a API do sistema de
gestão do condomínio).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Condominio:
    id: str
    nome: str
    qtd_elevadores: int | None  # None: não informado


@dataclass(frozen=True)
class Gestor:
    """Síndico ou subsíndico. Uma pessoa pode ter mais de um e-mail (um Gestor por e-mail)."""

    condominio: Condominio
    papel: str  # "sindico" ou "subsindico"
    nome: str
    email: str


class CadastroCondominios:
    def __init__(self, condominios: Sequence[Condominio], gestores: Sequence[Gestor] = ()):
        self._por_id = {c.id: c for c in condominios}
        self._gestor_por_email = {g.email.lower(): g for g in gestores}

    def por_id(self, condominio_id: str | None) -> Condominio | None:
        return self._por_id.get(condominio_id) if condominio_id else None

    def por_gestor(self, email: str) -> Gestor | None:
        """Síndico ou subsíndico pelo e-mail do remetente. Assinatura no texto não conta."""
        return self._gestor_por_email.get(email.strip().lower())

    def por_nome(self, nome: str | None) -> Condominio | None:
        if not nome:
            return None
        alvo = _normalizar(nome)
        if not alvo:  # ex.: o LLM devolveu só "Condomínio"
            return None
        for c in self._por_id.values():
            nome_c = _normalizar(c.nome)
            if alvo in nome_c or nome_c in alvo:
                return c
        return None


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    sem_prefixo = re.sub(r"\b(condominio|cond|edificio|ed|residencial|res)\b\.?", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", sem_prefixo).strip()
