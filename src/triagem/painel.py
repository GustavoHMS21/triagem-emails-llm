"""Etapa 5: painel da fila de atendimento.

Mostra a fila ordenada e por que cada e-mail está em cada nível. O conteúdo
do e-mail não é guardado (fica no Gmail): cada chamado tem o link para abrir
a mensagem original.

Uso:
    uv run streamlit run src/triagem/painel.py
"""

from zoneinfo import ZoneInfo

import streamlit as st

from triagem.config import config
from triagem.formatacao import escapar_markdown, link_gmail
from triagem.regras import CadastroCondominios
from triagem.repositorio import Repositorio

NIVEIS = {3: "🔴 Urgente", 2: "🟠 Importante", 1: "⚪ Normal"}
FUSO = ZoneInfo("America/Sao_Paulo")  # o banco guarda em UTC; a atendente lê no horário local


def mostrar_fila(repo: Repositorio, cadastro: CadastroCondominios) -> None:
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

    # Texto dinâmico passa por escapar_markdown antes de qualquer componente que
    # interpreta markdown (título do expander, caption, markdown)
    for t in fila:
        condominio = cadastro.por_id(t["condominio_id"])
        titulo = (
            f"{NIVEIS[t['nivel_final']]}"
            f"{' · 👀 revisão' if t['requer_revisao'] else ''}"
            f"{' · 🏢 síndico/subsíndico' if t['remetente_sindico'] else ''}"
            f" · {t['categoria'] or 'sem categoria'}"
            f" · {escapar_markdown(condominio.nome) if condominio else 'condomínio não identificado'}"
            f" · {t['recebido_em'].astimezone(FUSO):%d/%m %H:%M}"
        )
        with st.expander(titulo):
            st.caption(f"status: {t['status']}{' · 📎 tem anexo' if t['tem_anexo'] else ''}")
            st.markdown("**Por que está nesse nível:**")
            for motivo in t["motivos"]:
                st.markdown(f"- {escapar_markdown(motivo)}")
            st.link_button("Abrir no Gmail", link_gmail(t["email_id"]))

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
    mostrar_fila(repo, CadastroCondominios.de_csv(config.condominios_csv, config.gestores_csv))
