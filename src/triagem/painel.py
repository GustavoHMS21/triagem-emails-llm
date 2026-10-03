"""Etapa 5: painel da fila de atendimento.

Uso:
    uv run streamlit run src/triagem/painel.py
"""

import streamlit as st

from triagem.config import config
from triagem.repositorio import Repositorio

NIVEIS = {3: "🔴 Urgente", 2: "🟠 Importante", 1: "⚪ Normal"}


def mostrar_fila(repo: Repositorio) -> None:
    with st.sidebar:
        status = st.multiselect(
            "Status", ["pendente", "em_atendimento", "concluido"], default=["pendente", "em_atendimento"]
        )
        so_revisao = st.checkbox("Só os que pedem revisão")
        esconder_lixo = st.checkbox("Esconder propaganda", value=True)

    fila = repo.fila(status)
    if so_revisao:
        fila = [t for t in fila if t["requer_revisao"]]
    if esconder_lixo:
        fila = [t for t in fila if t["categoria"] != "lixo"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Urgentes", sum(t["nivel_final"] == 3 for t in fila))
    col2.metric("Importantes", sum(t["nivel_final"] == 2 for t in fila))
    col3.metric("Pedem revisão", sum(t["requer_revisao"] for t in fila))

    for t in fila:
        titulo = (
            f"{NIVEIS[t['nivel_final']]}"
            f"{' · 👀 revisão' if t['requer_revisao'] else ''}"
            f"{' · 🏢 síndico' if t['remetente_sindico'] else ''}"
            f" · {t['categoria'] or 'sem categoria'} · {t['assunto'] or '(sem assunto)'}"
        )
        with st.expander(titulo):
            st.caption(f"{t['remetente']} · recebido em {t['recebido_em']:%d/%m %H:%M} · status: {t['status']}")
            if t["resumo"]:
                st.markdown(f"**Resumo:** {t['resumo']}")
            st.markdown("**Por que está nesse nível:**")
            for motivo in t["motivos"]:
                st.markdown(f"- {motivo}")
            st.text(t["corpo"])
            if t["anexos"]:
                st.caption("Anexos: " + ", ".join(a["nome"] for a in t["anexos"]))

            b1, b2 = st.columns(2)
            if b1.button("Assumir", key=f"assumir-{t['id']}", disabled=t["status"] != "pendente"):
                repo.atualizar_status(t["id"], "em_atendimento")
                st.rerun()
            if b2.button("Concluir", key=f"concluir-{t['id']}", disabled=t["status"] == "concluido"):
                repo.atualizar_status(t["id"], "concluido")
                st.rerun()


st.set_page_config(page_title="Fila de triagem: Alvorada", layout="wide")
st.title("Fila de atendimento")

# O Streamlit roda este script de novo a cada clique: uma conexão por atualização da tela,
# fechada pelo `with` mesmo quando st.rerun() interrompe a execução
with Repositorio(config.database_url) as repo:
    mostrar_fila(repo)
