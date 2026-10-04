from datetime import datetime

import pytest

from triagem.limpeza import limpar
from triagem.modelos import Anexo, Classificacao, Email, Nivel
from triagem.config import config
from triagem.regras import CadastroCondominios, Condominio, Gestor, aplicar_regras

ACACIAS = Condominio("C01", "Condomínio Jardim das Acácias", 2)
SOLAR = Condominio("C02", "Edifício Solar do Parque", 1)
PORTAL = Condominio("C08", "Residencial Portal do Sol", None)  # nº de elevadores não informado
CADASTRO = CadastroCondominios(
    [ACACIAS, SOLAR, PORTAL],
    [
        Gestor(SOLAR, "sindico", "Síndico Solar", "sindico@solar.com.br"),
        Gestor(ACACIAS, "sindico", "Roberto", "roberto@empresa.com.br"),
        Gestor(ACACIAS, "sindico", "Roberto", "roberto.sindico@gmail.com"),
        Gestor(ACACIAS, "subsindico", "Renata", "renata@gmail.com"),
    ],
)


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


# --- Cadastro: vários e-mails, subsíndico, elevadores desconhecidos ----------


def test_sindico_com_segundo_email_tambem_sobe():
    t = triar(email(remetente="roberto.sindico@gmail.com"), classif(urgencia="normal"))
    assert t.nivel_final == Nivel.IMPORTANTE
    assert t.condominio_id == "C01"


def test_subsindico_sobe_um_nivel_e_o_motivo_diz_o_papel():
    t = triar(email(remetente="renata@gmail.com"), classif(urgencia="importante"))
    assert t.nivel_final == Nivel.URGENTE
    assert t.remetente_sindico
    assert any("subsindico de Condomínio Jardim das Acácias" in m for m in t.motivos)


def test_elevador_parado_com_qtd_desconhecida_vira_urgente_com_revisao():
    c = classif(urgencia="importante", elevador_parado=True, condominio_mencionado="Portal do Sol")
    t = triar(email("o elevador parou"), c)
    assert t.nivel_final == Nivel.URGENTE
    assert t.requer_revisao


def test_nome_de_condominio_generico_nao_casa_com_o_primeiro_da_lista():
    # "Condomínio" normalizado vira vazio, e "" in "qualquer texto" é True em Python
    assert CADASTRO.por_nome("Condomínio") is None


def test_cadastro_real_carrega_e_todo_gestor_aponta_para_condominio_existente():
    cadastro = CadastroCondominios.de_csv(config.condominios_csv, config.gestores_csv)
    roberto = [cadastro.por_gestor(e) for e in ("roberto@nogueiratransportes.com.br", "roberto.nogueira.sindico@gmail.com")]
    assert all(g and g.condominio.id == "C01" for g in roberto)
    assert cadastro.por_gestor("renatasilveira@gmail.com").papel == "subsindico"
    assert cadastro.por_nome("Santa Clara").qtd_elevadores is None


# --- LGPD: motivos não carregam texto do e-mail ------------------------------


def test_motivos_nao_carregam_dado_pessoal_do_email():
    e = email("o elevador parou com a dona Cida do apto 52 dentro", remetente="sindico@solar.com.br")
    c = classif(urgencia="urgente", motivo="Dona Cida do apto 52 presa no elevador")
    t = triar(e, c)
    texto = " ".join(t.motivos)
    assert "Cida" not in texto and "52" not in texto
    assert t.nivel_final == Nivel.URGENTE


def test_palavra_chave_aparece_pelo_rotulo():
    t = triar(email("cheiro de gás no hall"), classif(urgencia="normal"))
    assert any("Palavra-chave crítica (cheiro de gás)" in m for m in t.motivos)


def test_portao_que_nao_fecha_e_urgente_mesmo_se_o_llm_subestimar():
    # Regra do cliente: portão da garagem ou da entrada que não fecha é urgente
    t = triar(email("O portão da entrada de pedestres não fecha sozinho"), classif(urgencia="normal"))
    assert t.nivel_final == Nivel.URGENTE
    assert t.requer_revisao
