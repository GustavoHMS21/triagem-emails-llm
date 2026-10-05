"""Etapa 5: painel da fila de atendimento.

Quadro por status (pendente, em atendimento, concluído), cada coluna em ordem
de prioridade, e um resumo por condomínio. O conteúdo do e-mail não é guardado
(fica no Gmail): cada chamado tem o link para abrir a mensagem original.

Este arquivo só desenha: filtros, indicadores, colunas e resumo são calculados
em fila.py, que é testável sem Streamlit.

Uso:
    uv run streamlit run src/triagem/painel.py
"""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import streamlit as st

from triagem.cadastro import CadastroCondominios
from triagem.cadastro_csv import carregar_cadastro
from triagem.config import carregar_config
from triagem.fila import (
    COLUNAS,
    MAX_CONCLUIDOS,
    PROXIMA_ACAO,
    Chamado,
    Filtros,
    calcular_indicadores,
    filtrar,
    itens_da_coluna,
    nome_condominio,
    opcoes_de_condominio,
    resumo_por_condominio,
)
from triagem.formatacao import ROTULOS_STATUS, escapar_markdown, link_gmail, rotulo_categoria, tempo_de_espera
from triagem.modelos import Status
from triagem.repositorio import Repositorio

FUSO = ZoneInfo("America/Sao_Paulo")  # o banco guarda em UTC; a atendente lê no horário local

# nível -> (rótulo, cor do selo)
NIVEIS = {3: ("Urgente", "red"), 2: ("Importante", "orange"), 1: ("Normal", "gray")}

# CSS fixo: nenhum dado do banco entra aqui. Borda colorida por nível nos cartões
# (o Streamlit expõe a key do container como classe "st-key-<key>").
_CSS = """
<style>
[class*="st-key-cartao-3-"] { border-left: 5px solid #DC2626 !important; }
[class*="st-key-cartao-2-"] { border-left: 5px solid #EA580C !important; }
[class*="st-key-cartao-1-"] { border-left: 5px solid #9CA3AF !important; }
</style>
"""


def barra_de_filtros(fila: list[Chamado], cadastro: CadastroCondominios) -> Filtros:
    with st.sidebar:
        st.header("Filtros")
        return Filtros(
            condominios=st.multiselect(
                "Condomínio", opcoes_de_condominio(fila, cadastro), placeholder="Todos os condomínios"
            ),
            niveis=st.pills(
                "Nível", [3, 2, 1], selection_mode="multi", default=[3, 2, 1], format_func=lambda n: NIVEIS[n][0]
            ),
            so_revisao=st.toggle("Só os que pedem revisão"),
            esconder_propaganda=st.toggle("Esconder propaganda", value=True),
        )


def cabecalho(agora: datetime) -> None:
    titulo, acao = st.columns([4, 1], vertical_alignment="bottom")
    with titulo:
        st.title("Fila de atendimento")
        st.caption(f"Chamados por prioridade · atualizado às {agora:%H:%M}")
    with acao:
        if st.button("Atualizar", icon=":material/refresh:", width="stretch"):
            st.rerun()


def indicadores(fila: list[Chamado], agora: datetime) -> None:
    i = calcular_indicadores(fila)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Urgentes abertos", i.urgentes_abertos, border=True)
    c2.metric("🟠 Importantes abertos", i.importantes_abertos, border=True)
    c3.metric("👀 Pedem revisão", i.em_revisao, border=True)
    espera = tempo_de_espera(i.urgente_mais_antigo, agora) if i.urgente_mais_antigo else "nenhum"
    c4.metric("⏱ Urgente mais antigo esperando", espera, border=True)


def cartao(t: Chamado, cadastro: CadastroCondominios, repo: Repositorio, agora: datetime) -> None:
    nivel, cor = NIVEIS[t["nivel_final"]]
    with st.container(border=True, key=f"cartao-{t['nivel_final']}-{t['id']}"):
        selos = [f":{cor}-badge[{nivel}]"]
        if t["requer_revisao"]:
            selos.append(":violet-badge[:material/visibility: Revisão]")
        if t["remetente_sindico"]:
            selos.append(":blue-badge[:material/apartment: Síndico]")
        st.markdown(" ".join(selos))

        st.markdown(f"**{escapar_markdown(nome_condominio(t, cadastro))}**")
        if t["status"] == Status.CONCLUIDO:
            quando = f"concluído {tempo_de_espera(t['atualizado_em'], agora)}"
        else:
            quando = f"aguardando {tempo_de_espera(t['recebido_em'], agora)}"
        anexo = " · 📎 anexo" if t["tem_anexo"] else ""
        st.caption(f"{rotulo_categoria(t['categoria'])} · {quando}{anexo}")

        if t["motivos"]:  # só quando alguma regra de negócio mexeu no nível
            with st.expander("Por que este nível?"):
                for motivo in t["motivos"]:
                    st.markdown(f"- {escapar_markdown(motivo)}")

        gmail, acao = st.columns(2)
        gmail.link_button("Gmail", link_gmail(t["email_id"]), icon=":material/mail:", width="stretch")
        rotulo, proximo = PROXIMA_ACAO[t["status"]]
        tipo: Literal["primary", "secondary"] = "secondary" if t["status"] == Status.CONCLUIDO else "primary"
        if acao.button(rotulo, key=f"{proximo}-{t['id']}", type=tipo, width="stretch"):
            repo.atualizar_status(t["id"], proximo)
            st.rerun()


def quadro(fila: list[Chamado], cadastro: CadastroCondominios, repo: Repositorio, agora: datetime) -> None:
    colunas = st.columns(len(COLUNAS), gap="medium")
    for status, coluna in zip(COLUNAS, colunas, strict=True):
        itens = itens_da_coluna(fila, status)
        with coluna:
            st.subheader(f"{ROTULOS_STATUS[status]} · {len(itens)}")
            if status == Status.CONCLUIDO and itens:
                st.caption(f"Últimos {MAX_CONCLUIDOS}")
            if not itens:
                st.caption("Nenhum chamado aqui.")
            for t in itens:
                cartao(t, cadastro, repo, agora)


def aba_por_condominio(fila: list[Chamado], cadastro: CadastroCondominios) -> None:
    resumo = resumo_por_condominio(fila, cadastro)
    if not resumo:
        st.info("Nenhum chamado aberto com os filtros atuais.")
        return
    st.caption("Chamados abertos (pendentes e em atendimento) por condomínio, mais urgentes primeiro.")
    st.dataframe(resumo, hide_index=True, width="stretch")


# --- Página -------------------------------------------------------------------

st.set_page_config(page_title="Fila de atendimento", page_icon="📬", layout="wide")
st.markdown(_CSS, unsafe_allow_html=True)

# O Streamlit roda este script de novo a cada clique: uma conexão por atualização da tela,
# fechada pelo `with` mesmo quando st.rerun() interrompe a execução
config = carregar_config()
with Repositorio(config.database_url) as repo:
    cadastro = carregar_cadastro(config.condominios_csv, config.gestores_csv)
    agora = datetime.now(FUSO)
    todos = repo.fila(COLUNAS)
    fila = filtrar(todos, barra_de_filtros(todos, cadastro), cadastro)

    cabecalho(agora)
    indicadores(fila, agora)
    aba_quadro, aba_condominios = st.tabs(["Quadro", "Por condomínio"])
    with aba_quadro:
        quadro(fila, cadastro, repo, agora)
    with aba_condominios:
        aba_por_condominio(fila, cadastro)
