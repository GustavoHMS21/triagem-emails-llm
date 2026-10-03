from triagem.limpeza import limpar_assunto, limpar_corpo


def test_corta_historico_de_resposta_do_gmail():
    corpo = (
        "Pode confirmar o dia 12?\n\n"
        "Em seg., 28 de set. de 2026 às 17:02, Alvorada <atendimento@alvorada.com.br> escreveu:\n"
        "> Dias livres: 5, 12 e 19."
    )
    assert limpar_corpo(corpo) == "Pode confirmar o dia 12?"


def test_corta_historico_do_outlook():
    corpo = "Segue o comprovante.\n\nDe: Alvorada Atendimento\nEnviado: segunda-feira\nAssunto: boleto"
    assert limpar_corpo(corpo) == "Segue o comprovante."


def test_encaminhamento_mantem_o_conteudo():
    # E048: o conteúdo urgente está DENTRO do encaminhamento
    corpo = (
        "---------- Forwarded message ---------\n"
        "De: Roberto Nogueira <roberto@nogueiratransportes.com.br>\n"
        "Assunto: aviso\n\n"
        "A tampa do poço de esgoto quebrou, tem um buraco aberto."
    )
    assert limpar_corpo(corpo) == "A tampa do poço de esgoto quebrou, tem um buraco aberto."


def test_encaminhamento_com_texto_em_cima_mantem_os_dois():
    corpo = (
        "Sérgio, veja o aviso abaixo.\n\n"
        "---------- Mensagem encaminhada ---------\n"
        "De: Zelador <zelador@gmail.com>\n"
        "Data: 1 de out. de 2026\n\n"
        "Bomba do bloco A parou."
    )
    assert limpar_corpo(corpo) == "Sérgio, veja o aviso abaixo.\n\nBomba do bloco A parou."


def test_resposta_continua_cortando_o_historico():
    corpo = "Ok, obrigado!\n\n-----Mensagem original-----\nDe: Alvorada\nSegue boleto."
    assert limpar_corpo(corpo) == "Ok, obrigado!"


def test_remove_rodape_de_celular():
    assert limpar_corpo("Sem água no bloco B.\n\nEnviado do meu iPhone") == "Sem água no bloco B."


def test_remove_assinatura_a_partir_da_despedida():
    corpo = "O elevador parou.\n\nAtt,\nLúcia Martins\nApto 92"
    assert limpar_corpo(corpo) == "O elevador parou."


def test_remove_assinatura_com_separador():
    corpo = "Interfone quebrado.\n-- \nCarlos\nSíndico do Ed. Solar"
    assert limpar_corpo(corpo) == "Interfone quebrado."


def test_nao_corta_despedida_no_meio_de_texto_longo():
    corpo = "Obrigado\n" + "\n".join(f"linha {i}" for i in range(12))
    assert limpar_corpo(corpo).startswith("Obrigado\nlinha 0")


def test_assunto_perde_urgente_e_prefixos():
    assert limpar_assunto("RE: ENC: URGENTE!!! segunda via") == "segunda via"
    assert limpar_assunto("Urgente - vazamento") == "vazamento"
