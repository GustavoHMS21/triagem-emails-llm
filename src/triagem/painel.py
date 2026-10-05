"""Etapa 5: painel da fila de atendimento.

Quadro por status (pendente, em atendimento, concluído), cada coluna em ordem
de prioridade, e um resumo por condomínio. O conteúdo do e-mail não é guardado
(fica no Gmail): cada chamado tem o link para abrir a mensagem original.

Uso:
    uv run streamlit run src/triagem/painel.py
"""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from triagem.cadastro import CadastroCondominios
from triagem.cadastro_csv import carregar_cadastro
from triagem.config import config
from triagem.formatacao import ROTULOS_STATUS, escapar_markdown, link_gmail, rotulo_categoria, tempo_de_espera
from triagem.repositorio import Repositorio

FUSO = ZoneInfo("America/Sao_Paulo")  # o banco guarda em UTC; a atendente lê no horário local

# nível -> (rótulo, cor do selo)
NIVEIS = {3: ("Urgente", "red"), 2: ("Importante", "orange"), 1: ("Normal", "gray")}
COLUNAS = ["pendente", "em_atendimento", "concluido"]
# status -> (botão, próximo status): uma ação principal por cartão
PROXIMA_ACAO = {
    "pendente": ("Assumir", "em_atendimento"),
    "em_atendimento": ("Concluir", "concluido"),
    "concluido": ("Reabrir", "pendente"),
}
SEM_CONDOMINIO = "Não identificado"
MAX_CONCLUIDOS = 10

# CSS fixo: nenhum dado do banco entra aqui. Borda colorida por nível nos cartões
# (o Streamlit expõe a key do container como classe "st-key-<key>").
_CSS = """
<style>
[class*="st-key-cartao-3-"] { border-left: 5px solid #DC2626 !important; }
[class*="st-key-cartao-2-"] { border-left: 5px solid #EA580C !important; }
[class*="st-key-cartao-1-"] { border-left: 5px solid #9CA3AF !important; }
</style>
"""


def nome_condominio(t: dict, cadastro: CadastroCondominios) -> str:
    condominio = cadastro.por_id(t["condominio_id"])
    return condominio.nome if condominio else SEM_CONDOMINIO


# --- Filtros -----------------------------------------------------------------


def filtros(fila: list[dict], cadastro: CadastroCondominios) -> list[dict]:
    with st.sidebar:
        st.header("Filtros")
        nomes = sorted({nome_condominio(t, cadastro) for t in fila} - {SEM_CONDOMINIO})
        condominios = st.multiselect("Condomínio", nomes + [SEM_CONDOMINIO], placeholder="Todos os condomínios")
        # Nada selecionado = todos (em vez de uma tela vazia sem explicação)
        niveis = st.pills(
            "Nível",
            [3, 2, 1],
            selection_mode="multi",
            default=[3, 2, 1],
            format_func=lambda n: NIVEIS[n][0],
        ) or [3, 2, 1]
        so_revisao = st.toggle("Só os que pedem revisão")
        esconder_propaganda = st.toggle("Esconder propaganda", value=True)

    return [
        t
        for t in fila
        if (not condominios or nome_condominio(t, cadastro) in condominios)
        and t["nivel_final"] in niveis
        and (t["requer_revisao"] or not so_revisao)
        and not (esconder_propaganda and t["categoria"] == "lixo")
    ]


# --- Cabeçalho e indicadores --------------------------------------------------


def cabecalho(agora: datetime) -> None:
    titulo, acao = st.columns([4, 1], vertical_alignment="bottom")
    with titulo:
        st.title("Fila de atendimento")
        st.caption(f"Chamados por prioridade · atualizado às {agora:%H:%M}")
    with acao:
        if st.button("Atualizar", icon=":material/refresh:", width="stretch"):
            st.rerun()


def indicadores(fila: list[dict], agora: datetime) -> None:
    abertos = [t for t in fila if t["status"] != "concluido"]
    urgentes_pendentes = [t for t in abertos if t["nivel_final"] == 3 and t["status"] == "pendente"]
    mais_antigo = min((t["recebido_em"] for t in urgentes_pendentes), default=None)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Urgentes abertos", sum(t["nivel_final"] == 3 for t in abertos), border=True)
    c2.metric("🟠 Importantes abertos", sum(t["nivel_final"] == 2 for t in abertos), border=True)
    c3.metric("👀 Pedem revisão", sum(t["requer_revisao"] for t in abertos), border=True)
    c4.metric(
        "⏱ Urgente mais antigo esperando",
        tempo_de_espera(mais_antigo, agora) if mais_antigo else "nenhum",
        border=True,
    )


# --- Quadro por status --------------------------------------------------------


def cartao(t: dict, cadastro: CadastroCondominios, repo: Repositorio, agora: datetime) -> None:
    nivel, cor = NIVEIS[t["nivel_final"]]
    with st.container(border=True, key=f"cartao-{t['nivel_final']}-{t['id']}"):
        selos = [f":{cor}-badge[{nivel}]"]
        if t["requer_revisao"]:
            selos.append(":violet-badge[:material/visibility: Revisão]")
        if t["remetente_sindico"]:
            selos.append(":blue-badge[:material/apartment: Síndico]")
        st.markdown(" ".join(selos))

        st.markdown(f"**{escapar_markdown(nome_condominio(t, cadastro))}**")
        if t["status"] == "concluido":
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
        tipo: Literal["primary", "secondary"] = "secondary" if t["status"] == "concluido" else "primary"
        if acao.button(rotulo, key=f"{proximo}-{t['id']}", type=tipo, width="stretch"):
            repo.atualizar_status(t["id"], proximo)
            st.rerun()


def quadro(fila: list[dict], cadastro: CadastroCondominios, repo: Repositorio, agora: datetime) -> None:
    colunas = st.columns(len(COLUNAS), gap="medium")
    for status, coluna in zip(COLUNAS, colunas, strict=True):
        itens = [t for t in fila if t["status"] == status]
        if status == "concluido":
            itens = sorted(itens, key=lambda t: t["atualizado_em"], reverse=True)[:MAX_CONCLUIDOS]
        with coluna:
            st.subheader(f"{ROTULOS_STATUS[status]} · {len(itens)}")
            if status == "concluido" and itens:
                st.caption(f"Últimos {MAX_CONCLUIDOS}")
            if not itens:
                st.caption("Nenhum chamado aqui.")
            for t in itens:
                cartao(t, cadastro, repo, agora)


# --- Resumo por condomínio ----------------------------------------------------


def resumo_por_condominio(fila: list[dict], cadastro: CadastroCondominios) -> None:
    abertos = [t for t in fila if t["status"] != "concluido"]
    if not abertos:
        st.info("Nenhum chamado aberto com os filtros atuais.")
        return

    linhas: dict[str, dict[str, int]] = {}
    for t in abertos:
        linha = linhas.setdefault(
            nome_condominio(t, cadastro),
            {"Urgentes": 0, "Importantes": 0, "Normais": 0, "Em revisão": 0, "Total": 0},
        )
        linha[{3: "Urgentes", 2: "Importantes", 1: "Normais"}[t["nivel_final"]]] += 1
        linha["Em revisão"] += t["requer_revisao"]
        linha["Total"] += 1

    tabela = (
        pd.DataFrame.from_dict(linhas, orient="index")
        .rename_axis("Condomínio")
        .reset_index()
        .sort_values(["Urgentes", "Importantes", "Total"], ascending=False)
    )
    st.caption("Chamados abertos (pendentes e em atendimento) por condomínio, mais urgentes primeiro.")
    st.dataframe(tabela, hide_index=True, width="stretch")


# --- Página -------------------------------------------------------------------

st.set_page_config(page_title="Fila de atendimento", page_icon="📬", layout="wide")
st.markdown(_CSS, unsafe_allow_html=True)

# O Streamlit roda este script de novo a cada clique: uma conexão por atualização da tela,
# fechada pelo `with` mesmo quando st.rerun() interrompe a execução
with Repositorio(config.database_url) as repo:
    cadastro = carregar_cadastro(config.condominios_csv, config.gestores_csv)
    agora = datetime.now(FUSO)
    fila = filtros(repo.fila(COLUNAS), cadastro)

    cabecalho(agora)
    indicadores(fila, agora)
    aba_quadro, aba_condominios = st.tabs(["Quadro", "Por condomínio"])
    with aba_quadro:
        quadro(fila, cadastro, repo, agora)
    with aba_condominios:
        resumo_por_condominio(fila, cadastro)
