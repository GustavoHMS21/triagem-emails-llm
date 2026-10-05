"""Repositorio contra um PostgreSQL de verdade, com o schema criado pelas migrações."""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from triagem.limpeza import limpar
from triagem.modelos import Anexo, Email, Nivel, Status, Triagem
from triagem.repositorio import Repositorio

BASE = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)


def triagem(
    email_id: str,
    nivel: Nivel = Nivel.NORMAL,
    revisao: bool = False,
    hora: int = 0,
    corpo: str = "texto do morador",
    remetente: str = "morador@gmail.com",
    assunto: str = "assunto",
    anexos: tuple[str, ...] = (),
) -> Triagem:
    email = Email(
        id=email_id,
        remetente=remetente,
        assunto=assunto,
        corpo=corpo,
        recebido_em=BASE + timedelta(hours=hora),
        anexos=[Anexo(nome=a) for a in anexos],
    )
    return Triagem(
        email=limpar(email),
        classificacao=None,
        categoria="manutencao",
        condominio_id="C01",
        remetente_sindico=False,
        nivel_final=nivel,
        requer_revisao=revisao,
        motivos=["Classificação em dúvida entre dois níveis"] if revisao else [],
        modelo="teste",
        prompt_versao="teste",
    )


def test_salvar_e_reconhecer_como_ja_triado(banco_migrado):
    with Repositorio(banco_migrado) as repo:
        assert not repo.ja_triado("e1")
        assert repo.salvar(triagem("e1", anexos=("foto.jpg",)))
        assert repo.ja_triado("e1")

        [linha] = repo.fila()
        assert linha["nivel_final"] == Nivel.NORMAL
        assert linha["tem_anexo"] is True
        assert linha["recebido_em"] == BASE  # fuso preservado (timestamptz)


def test_salvar_duas_vezes_nao_duplica(banco_migrado):
    # Idempotência: o pipeline pode ser reexecutado depois de uma queda
    with Repositorio(banco_migrado) as repo:
        assert repo.salvar(triagem("e1"))
        assert not repo.salvar(triagem("e1"))
        assert len(repo.fila()) == 1


def test_fila_vem_na_ordem_de_prioridade(banco_migrado):
    with Repositorio(banco_migrado) as repo:
        repo.salvar(triagem("normal-antigo", Nivel.NORMAL, hora=0))
        repo.salvar(triagem("urgente-novo", Nivel.URGENTE, hora=5))
        repo.salvar(triagem("urgente-antigo", Nivel.URGENTE, hora=1))
        repo.salvar(triagem("normal-revisao", Nivel.NORMAL, revisao=True, hora=3))

        ordem = [t["email_id"] for t in repo.fila()]
    # nível desc → revisão primeiro → mais antigo primeiro
    assert ordem == ["urgente-antigo", "urgente-novo", "normal-revisao", "normal-antigo"]


def test_fila_padrao_nao_traz_concluidos(banco_migrado):
    with Repositorio(banco_migrado) as repo:
        repo.salvar(triagem("aberto"))
        repo.salvar(triagem("fechado"))
        [fechado] = [t for t in repo.fila() if t["email_id"] == "fechado"]
        repo.atualizar_status(fechado["id"], Status.CONCLUIDO)

        assert [t["email_id"] for t in repo.fila()] == ["aberto"]
        assert [t["email_id"] for t in repo.fila([Status.CONCLUIDO])] == ["fechado"]


def test_status_volta_do_banco_como_enum(banco_migrado):
    with Repositorio(banco_migrado) as repo:
        repo.salvar(triagem("e1"))
        [t] = repo.fila()
        repo.atualizar_status(t["id"], Status.EM_ATENDIMENTO)
        [t] = repo.fila()
    assert t["status"] is Status.EM_ATENDIMENTO
    assert t["atualizado_em"] > t["triado_em"]


def test_banco_recusa_status_invalido(banco_migrado):
    # Segunda linha de defesa: além do tipo no Python, o CHECK do schema
    with Repositorio(banco_migrado) as repo:
        repo.salvar(triagem("e1"))
        with pytest.raises(psycopg.errors.CheckViolation):
            repo.conn.execute("UPDATE triagens SET status = 'concluído'")


def test_nada_do_conteudo_do_email_chega_ao_banco(banco_migrado):
    # Minimização (LGPD): o conteúdo fica no Gmail. Procura cada dado pessoal
    # em TODAS as colunas gravadas, inclusive as que forem criadas no futuro.
    pessoais = {
        "corpo": "Vazamento no apto 52 da Sandra Moreira",
        "remetente": "sandra.moreira@gmail.com",
        "assunto": "Socorro Sandra apto 52",
        "anexo": "rg_sandra_moreira.pdf",
    }
    t = triagem(
        "e1",
        corpo=pessoais["corpo"],
        remetente=pessoais["remetente"],
        assunto=pessoais["assunto"],
        anexos=(pessoais["anexo"],),
    )
    with Repositorio(banco_migrado) as repo:
        repo.salvar(t)
        [linha] = repo.conn.execute("SELECT * FROM triagens").fetchall()

    gravado = " ".join(str(valor) for valor in linha.values())
    for campo, valor in pessoais.items():
        assert valor not in gravado, f"{campo} foi gravado no banco"
    assert "Sandra" not in gravado
