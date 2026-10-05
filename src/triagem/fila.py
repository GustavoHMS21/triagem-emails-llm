"""Lógica da fila de atendimento, separada da tela.

Funções puras sobre a lista de chamados (linhas da tabela `triagens`): filtros,
indicadores, colunas do quadro e resumo por condomínio. Sem Streamlit aqui,
para tudo ser testável; o painel só desenha o que estas funções devolvem.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from triagem.cadastro import CadastroCondominios

Chamado = dict[str, Any]  # uma linha da tabela triagens

SEM_CONDOMINIO = "Não identificado"
MAX_CONCLUIDOS = 10
COLUNAS = ["pendente", "em_atendimento", "concluido"]

# status -> (ação, próximo status): uma ação principal por chamado.
# "Reabrir" desfaz um clique errado em "Concluir".
PROXIMA_ACAO = {
    "pendente": ("Assumir", "em_atendimento"),
    "em_atendimento": ("Concluir", "concluido"),
    "concluido": ("Reabrir", "pendente"),
}


def nome_condominio(chamado: Chamado, cadastro: CadastroCondominios) -> str:
    condominio = cadastro.por_id(chamado["condominio_id"])
    return condominio.nome if condominio else SEM_CONDOMINIO


def opcoes_de_condominio(fila: list[Chamado], cadastro: CadastroCondominios) -> list[str]:
    """Condomínios presentes na fila, em ordem alfabética; "Não identificado" por último."""
    nomes = {nome_condominio(t, cadastro) for t in fila}
    return sorted(nomes - {SEM_CONDOMINIO}) + [SEM_CONDOMINIO]


# --- Filtros -----------------------------------------------------------------


@dataclass
class Filtros:
    condominios: list[str] = field(default_factory=list)  # vazio = todos
    niveis: list[int] = field(default_factory=lambda: [3, 2, 1])  # vazio = todos
    so_revisao: bool = False
    esconder_propaganda: bool = True


def filtrar(fila: list[Chamado], filtros: Filtros, cadastro: CadastroCondominios) -> list[Chamado]:
    niveis = filtros.niveis or [3, 2, 1]  # nada selecionado = todos, em vez de uma tela vazia
    return [
        t
        for t in fila
        if (not filtros.condominios or nome_condominio(t, cadastro) in filtros.condominios)
        and t["nivel_final"] in niveis
        and (t["requer_revisao"] or not filtros.so_revisao)
        and not (filtros.esconder_propaganda and t["categoria"] == "lixo")
    ]


# --- Indicadores ---------------------------------------------------------------


@dataclass
class Indicadores:
    urgentes_abertos: int
    importantes_abertos: int
    em_revisao: int
    urgente_mais_antigo: datetime | None  # recebimento do urgente pendente mais antigo


def calcular_indicadores(fila: list[Chamado]) -> Indicadores:
    """Indicadores dos chamados abertos (pendentes e em atendimento).

    O "urgente mais antigo" considera só os pendentes: um urgente já assumido
    tem alguém cuidando e não está mais esperando.
    """
    abertos = [t for t in fila if t["status"] != "concluido"]
    urgentes_pendentes = [t for t in abertos if t["nivel_final"] == 3 and t["status"] == "pendente"]
    return Indicadores(
        urgentes_abertos=sum(t["nivel_final"] == 3 for t in abertos),
        importantes_abertos=sum(t["nivel_final"] == 2 for t in abertos),
        em_revisao=sum(t["requer_revisao"] for t in abertos),
        urgente_mais_antigo=min((t["recebido_em"] for t in urgentes_pendentes), default=None),
    )


# --- Quadro ----------------------------------------------------------------------


def itens_da_coluna(fila: list[Chamado], status: str) -> list[Chamado]:
    """Chamados de uma coluna do quadro.

    Pendente e em atendimento mantêm a ordem de prioridade da fila. Concluído
    mostra só os mais recentes, para a coluna não crescer para sempre.
    """
    itens = [t for t in fila if t["status"] == status]
    if status == "concluido":
        itens = sorted(itens, key=lambda t: t["atualizado_em"], reverse=True)[:MAX_CONCLUIDOS]
    return itens


# --- Resumo por condomínio -------------------------------------------------------

_COLUNA_DO_NIVEL = {3: "Urgentes", 2: "Importantes", 1: "Normais"}


def resumo_por_condominio(fila: list[Chamado], cadastro: CadastroCondominios) -> list[dict[str, Any]]:
    """Chamados abertos por condomínio e nível, mais urgentes primeiro."""
    linhas: dict[str, dict[str, Any]] = {}
    for t in fila:
        if t["status"] == "concluido":
            continue
        nome = nome_condominio(t, cadastro)
        linha = linhas.setdefault(
            nome,
            {"Condomínio": nome, "Urgentes": 0, "Importantes": 0, "Normais": 0, "Em revisão": 0, "Total": 0},
        )
        linha[_COLUNA_DO_NIVEL[t["nivel_final"]]] += 1
        linha["Em revisão"] += int(t["requer_revisao"])
        linha["Total"] += 1
    return sorted(linhas.values(), key=lambda r: (r["Urgentes"], r["Importantes"], r["Total"]), reverse=True)
