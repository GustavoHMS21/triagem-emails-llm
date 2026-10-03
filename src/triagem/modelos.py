"""Contratos de dados entre as etapas do pipeline.

Email           -> o que chega da fonte (JSON hoje, Gmail amanhã)
EmailLimpo      -> depois da limpeza (etapa 1)
Classificacao   -> o que o LLM devolve (etapa 2), validado aqui
Triagem         -> resultado final depois das regras de negócio (etapa 3)
"""

from datetime import datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field


class Nivel(IntEnum):
    """Nível de urgência. IntEnum para permitir comparar e subir nível com max()."""

    NORMAL = 1
    IMPORTANTE = 2
    URGENTE = 3

    @classmethod
    def de_texto(cls, texto: str) -> "Nivel":
        return cls[texto.upper()]

    def subir(self) -> "Nivel":
        return Nivel(min(self + 1, Nivel.URGENTE))


Categoria = Literal[
    "financeiro",
    "manutencao",
    "cobranca",
    "assembleia_reserva",
    "cadastro",
    "fornecedor",
    "lixo",
    "outros",
]
UrgenciaTexto = Literal["urgente", "importante", "normal"]


# --- Entrada -----------------------------------------------------------------


class Anexo(BaseModel):
    nome: str
    tipo: str = ""  # mime type, ex.: image/jpeg, application/pdf


class Email(BaseModel):
    id: str  # Message-ID no Gmail; garante idempotência no banco
    remetente: str
    assunto: str = ""
    corpo: str = ""
    recebido_em: datetime
    anexos: list[Anexo] = []
    cabecalhos: dict[str, str] = {}  # ex.: List-Unsubscribe, presente em e-mail de marketing


class EmailLimpo(BaseModel):
    original: Email
    assunto: str  # sem "URGENTE", "RE:", "ENC:"
    corpo: str  # sem histórico de resposta, rodapé de celular e assinatura

    @property
    def corpo_vazio(self) -> bool:
        return len(self.corpo.strip()) < 15


# --- Saída do LLM ------------------------------------------------------------


class Classificacao(BaseModel):
    """Schema que o LLM precisa preencher. É enviado ao Ollama como JSON Schema."""

    categoria: Categoria
    outras_categorias: list[Categoria] = Field(
        default=[], description="Preencha só se o e-mail trata de mais de um assunto"
    )
    urgencia: UrgenciaTexto = Field(description="Urgência do conteúdo, ignorando o remetente")
    em_duvida: bool = Field(description="true se ficou entre dois níveis de urgência")
    urgencia_alternativa: UrgenciaTexto | None = Field(
        default=None, description="O outro nível considerado, quando em_duvida=true"
    )
    elevador_parado: bool = Field(description="true se relata elevador parado ou quebrado")
    condominio_mencionado: str | None = Field(
        default=None, description="Nome do condomínio citado no texto, se houver"
    )
    resumo: str = Field(description="Uma frase curta para a fila de atendimento")
    motivo: str = Field(description="Trecho ou fato do e-mail que justifica a urgência")


# --- Resultado final ---------------------------------------------------------


class Triagem(BaseModel):
    email: EmailLimpo
    classificacao: Classificacao | None  # None quando o LLM falhou
    condominio_id: str | None
    remetente_sindico: bool
    nivel_final: Nivel
    requer_revisao: bool
    motivos: list[str]  # trilha de auditoria: por que o nível final é esse
    modelo: str
    prompt_versao: str
