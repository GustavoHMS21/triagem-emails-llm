"""Executor de migrações contra um PostgreSQL de verdade (fixture banco_vazio)."""

from pathlib import Path

import psycopg
import pytest

from triagem.migrar import Migracao, MigracaoAlterada, listar, migrar

PASTA_REAL = Path("db")


def conectar(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True)


def tabelas(conn: psycopg.Connection) -> set[str]:
    linhas = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {t for (t,) in linhas}


def registradas(conn: psycopg.Connection) -> list[str]:
    return [v for (v,) in conn.execute("SELECT versao FROM schema_migrations ORDER BY versao").fetchall()]


# --- Com as migrações reais do projeto ---------------------------------------


def test_banco_novo_recebe_todas_as_migracoes_em_ordem(banco_vazio):
    with conectar(banco_vazio) as conn:
        aplicadas = migrar(conn, listar(PASTA_REAL))
        colunas = {
            c
            for (c,) in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'triagens'"
            ).fetchall()
        }
        assert aplicadas == [m.versao for m in listar(PASTA_REAL)]
        assert registradas(conn) == aplicadas
    # Estado final do schema: colunas de dado pessoal removidas pela 002, tem_anexo criada
    assert "corpo" not in colunas and "remetente" not in colunas
    assert "tem_anexo" in colunas


def test_rodar_de_novo_nao_aplica_nada(banco_vazio):
    with conectar(banco_vazio) as conn:
        migrar(conn, listar(PASTA_REAL))
        assert migrar(conn, listar(PASTA_REAL)) == []


# --- Com migrações de teste ----------------------------------------------------


def test_aplica_so_as_que_faltam(banco_vazio):
    m1 = Migracao("001_a.sql", "CREATE TABLE a (id int);")
    m2 = Migracao("002_b.sql", "CREATE TABLE b (id int);")
    with conectar(banco_vazio) as conn:
        migrar(conn, [m1])
        assert migrar(conn, [m1, m2]) == ["002_b.sql"]
        assert {"a", "b"} <= tabelas(conn)


def test_migracao_aplicada_e_editada_depois_e_recusada(banco_vazio):
    with conectar(banco_vazio) as conn:
        migrar(conn, [Migracao("001_a.sql", "CREATE TABLE a (id int);")])
        with pytest.raises(MigracaoAlterada):
            migrar(conn, [Migracao("001_a.sql", "CREATE TABLE a (id bigint);")])


def test_migracao_com_erro_e_desfeita_inteira_e_nao_registrada(banco_vazio):
    ok = Migracao("001_ok.sql", "CREATE TABLE ok (id int);")
    quebrada = Migracao("002_quebrada.sql", "CREATE TABLE parcial (id int); SELECT 1/0;")
    with conectar(banco_vazio) as conn:
        with pytest.raises(psycopg.errors.DivisionByZero):
            migrar(conn, [ok, quebrada])
        assert registradas(conn) == ["001_ok.sql"]
        assert "parcial" not in tabelas(conn)  # o CREATE da migração quebrada foi desfeito


def test_baseline_registra_sem_executar(banco_vazio):
    # Banco anterior ao executor: a migração já está "no banco", só falta o registro
    perigosa = Migracao("002_apaga.sql", "CREATE TABLE nao_deveria_existir (id int);")
    with conectar(banco_vazio) as conn:
        assert migrar(conn, [perigosa], baseline=True) == ["002_apaga.sql"]
        assert "nao_deveria_existir" not in tabelas(conn)
        assert registradas(conn) == ["002_apaga.sql"]
