import re
from datetime import datetime, timedelta
from pathlib import Path

from triagem.cadastro import CadastroCondominios, Condominio
from triagem.fila import (
    MAX_CONCLUIDOS,
    PROXIMA_ACAO,
    SEM_CONDOMINIO,
    Filtros,
    calcular_indicadores,
    filtrar,
    itens_da_coluna,
    opcoes_de_condominio,
    resumo_por_condominio,
)
from triagem.modelos import Status

CADASTRO = CadastroCondominios([Condominio("C01", "Bela Vista", 2), Condominio("C02", "Monte Azul", 1)])
BASE = datetime(2026, 10, 5, 8, 0)


def chamado(id, nivel=1, status=Status.PENDENTE, condominio="C01", revisao=False, categoria="manutencao", hora=0):
    return {
        "id": id,
        "nivel_final": nivel,
        "status": status,
        "condominio_id": condominio,
        "requer_revisao": revisao,
        "categoria": categoria,
        "recebido_em": BASE + timedelta(hours=hora),
        "atualizado_em": BASE + timedelta(hours=hora),
    }


# --- Filtros -----------------------------------------------------------------


def test_sem_filtro_mostra_tudo_menos_propaganda():
    fila = [chamado(1), chamado(2, categoria="lixo")]
    assert [t["id"] for t in filtrar(fila, Filtros(), CADASTRO)] == [1]


def test_filtra_por_condominio_incluindo_nao_identificado():
    fila = [chamado(1, condominio="C01"), chamado(2, condominio="C02"), chamado(3, condominio=None)]
    filtros = Filtros(condominios=["Monte Azul", SEM_CONDOMINIO])
    assert [t["id"] for t in filtrar(fila, filtros, CADASTRO)] == [2, 3]


def test_nenhum_nivel_selecionado_significa_todos():
    fila = [chamado(1, nivel=3), chamado(2, nivel=1)]
    assert len(filtrar(fila, Filtros(niveis=[]), CADASTRO)) == 2


def test_so_revisao():
    fila = [chamado(1, revisao=True), chamado(2)]
    assert [t["id"] for t in filtrar(fila, Filtros(so_revisao=True), CADASTRO)] == [1]


def test_opcoes_de_condominio_em_ordem_com_nao_identificado_por_ultimo():
    fila = [chamado(1, condominio="C02"), chamado(2, condominio=None), chamado(3, condominio="C01")]
    assert opcoes_de_condominio(fila, CADASTRO) == ["Bela Vista", "Monte Azul", SEM_CONDOMINIO]


# --- Indicadores ---------------------------------------------------------------


def test_indicadores_ignoram_concluidos():
    fila = [chamado(1, nivel=3), chamado(2, nivel=3, status=Status.CONCLUIDO), chamado(3, nivel=2, revisao=True)]
    i = calcular_indicadores(fila)
    assert (i.urgentes_abertos, i.importantes_abertos, i.em_revisao) == (1, 1, 1)


def test_urgente_mais_antigo_considera_so_os_pendentes():
    fila = [
        chamado(1, nivel=3, status=Status.EM_ATENDIMENTO, hora=0),  # mais antigo, mas já assumido
        chamado(2, nivel=3, status=Status.PENDENTE, hora=2),
        chamado(3, nivel=3, status=Status.PENDENTE, hora=5),
    ]
    assert calcular_indicadores(fila).urgente_mais_antigo == BASE + timedelta(hours=2)


def test_sem_urgente_pendente_nao_ha_mais_antigo():
    assert calcular_indicadores([chamado(1, nivel=2)]).urgente_mais_antigo is None


# --- Quadro ----------------------------------------------------------------------


def test_coluna_mantem_a_ordem_de_prioridade_da_fila():
    fila = [chamado(1, nivel=3, hora=5), chamado(2, nivel=1, hora=0)]
    assert [t["id"] for t in itens_da_coluna(fila, Status.PENDENTE)] == [1, 2]


def test_concluidos_mostram_so_os_mais_recentes():
    fila = [chamado(i, status=Status.CONCLUIDO, hora=i) for i in range(MAX_CONCLUIDOS + 3)]
    itens = itens_da_coluna(fila, Status.CONCLUIDO)
    assert len(itens) == MAX_CONCLUIDOS
    assert itens[0]["id"] == MAX_CONCLUIDOS + 2  # o mais recente primeiro


# --- Resumo por condomínio -------------------------------------------------------


def test_resumo_conta_abertos_por_nivel_e_ordena_por_urgencia():
    fila = [
        chamado(1, nivel=1, condominio="C01"),
        chamado(2, nivel=1, condominio="C01"),
        chamado(3, nivel=3, condominio="C02", revisao=True),
        chamado(4, nivel=3, condominio="C01", status=Status.CONCLUIDO),  # não conta
    ]
    resumo = resumo_por_condominio(fila, CADASTRO)
    assert [r["Condomínio"] for r in resumo] == ["Monte Azul", "Bela Vista"]  # quem tem urgente vem primeiro
    assert resumo[0] == {
        "Condomínio": "Monte Azul",
        "Urgentes": 1,
        "Importantes": 0,
        "Normais": 0,
        "Em revisão": 1,
        "Total": 1,
    }
    assert resumo[1]["Normais"] == 2


# --- Status ------------------------------------------------------------------


def test_status_do_codigo_bate_com_o_check_do_banco():
    # Se alguém mudar um lado e esquecer o outro, este teste falha no CI
    sql = Path("db/001_init.sql").read_text(encoding="utf-8")
    check = re.search(r"CHECK \(status IN \(([^)]*)\)\)", sql)
    assert check, "CHECK de status não encontrado no schema"
    no_banco = set(re.findall(r"'([a-z_]+)'", check.group(1)))
    assert no_banco == {s.value for s in Status}


def test_todo_status_tem_uma_proxima_acao_valida():
    assert set(PROXIMA_ACAO) == set(Status)
    assert all(proximo in Status for _, proximo in PROXIMA_ACAO.values())
