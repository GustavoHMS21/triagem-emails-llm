from datetime import datetime

import pytest

from triagem.limpeza import limpar
from triagem.modelos import Anexo, Classificacao, Email, Nivel
from triagem.regras import CadastroCondominios, Condominio, aplicar_regras

CADASTRO = CadastroCondominios([
    Condominio("C01", "Condomínio Jardim das Acácias", 2, "sindico@acacias.com.br"),
    Condominio("C02", "Edifício Solar do Parque", 1, "sindico@solar.com.br"),
])


def email(corpo="texto qualquer do morador", remetente="morador@gmail.com", assunto="assunto", anexos=()):
    return limpar(Email(
        id="t1", remetente=remetente, assunto=assunto, corpo=corpo,
        recebido_em=datetime(2026, 10, 1, 9, 0), anexos=list(anexos),
    ))


def classif(**kwargs):
    base = dict(
        categoria="manutencao", urgencia="normal", em_duvida=False,
        elevador_parado=False, resumo="r", motivo="m",
    )
    return Classificacao(**{**base, **kwargs})


def triar(e, c):
    return aplicar_regras(e, c, CADASTRO, "modelo-teste", "v-teste")


def test_sem_regra_acionada_mantem_nivel_do_llm():
    t = triar(email(), classif(urgencia="importante"))
    assert t.nivel_final == Nivel.IMPORTANTE
    assert not t.requer_revisao


def test_falha_do_llm_vai_para_revisao():
    t = triar(email(), None)
    assert t.requer_revisao
    assert t.nivel_final == Nivel.NORMAL


def test_falha_do_llm_ainda_passa_pela_rede_de_palavras_chave():
    t = triar(email("cheiro de gás no hall"), None)
    assert t.nivel_final == Nivel.URGENTE
    assert t.requer_revisao


def test_duvida_fica_no_nivel_mais_alto_e_pede_revisao():
    t = triar(email(), classif(urgencia="importante", em_duvida=True, urgencia_alternativa="urgente"))
    assert t.nivel_final == Nivel.URGENTE
    assert t.requer_revisao


def test_duvida_com_alternativa_mais_baixa_nao_desce():
    t = triar(email(), classif(urgencia="importante", em_duvida=True, urgencia_alternativa="normal"))
    assert t.nivel_final == Nivel.IMPORTANTE


@pytest.mark.parametrize(
    ("condominio", "esperado", "revisao"),
    [
        ("Solar do Parque", Nivel.URGENTE, False),  # um elevador só
        ("Jardim das Acácias", Nivel.IMPORTANTE, False),  # tem outro funcionando
        (None, Nivel.URGENTE, True),  # não sabemos: na dúvida, urgente e revisão
    ],
)
def test_regra_do_elevador(condominio, esperado, revisao):
    c = classif(urgencia="importante", elevador_parado=True, condominio_mencionado=condominio)
    t = triar(email("o elevador parou"), c)
    assert t.nivel_final == esperado
    assert t.requer_revisao == revisao


def test_sindico_sobe_um_nivel():
    t = triar(email(remetente="SINDICO@solar.com.br"), classif(urgencia="normal"))
    assert t.remetente_sindico
    assert t.condominio_id == "C02"
    assert t.nivel_final == Nivel.IMPORTANTE


def test_sindico_nao_passa_de_urgente():
    t = triar(email(remetente="sindico@solar.com.br"), classif(urgencia="urgente"))
    assert t.nivel_final == Nivel.URGENTE


def test_assinatura_de_sindico_no_texto_nao_conta():
    t = triar(email("pedido simples\nSíndico do Solar do Parque"), classif(urgencia="normal"))
    assert not t.remetente_sindico
    assert t.nivel_final == Nivel.NORMAL


def test_palavra_chave_sobe_quando_llm_subestima():
    t = triar(email("tem um vazamento na garagem"), classif(urgencia="normal"))
    assert t.nivel_final == Nivel.IMPORTANTE
    assert t.requer_revisao


def test_palavra_chave_nao_rebaixa_o_llm():
    t = triar(email("tem um vazamento na garagem"), classif(urgencia="urgente"))
    assert t.nivel_final == Nivel.URGENTE
    assert not t.requer_revisao


def test_urgente_no_assunto_nao_aciona_nada():
    t = triar(email("preciso da segunda via", assunto="URGENTE!!!"), classif(urgencia="normal"))
    assert t.nivel_final == Nivel.NORMAL
    assert not t.requer_revisao


def test_corpo_vazio_com_anexo_vai_para_revisao():
    t = triar(email("segue anexo", anexos=[Anexo(nome="foto.jpg")]), classif())
    assert t.requer_revisao
