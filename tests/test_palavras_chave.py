import pytest

from triagem.modelos import Nivel
from triagem.palavras_chave import nivel_da_fila, nivel_por_palavra_chave

# Um exemplo real de texto para cada padrão da rede de segurança
EXEMPLOS_DA_REDE = [
    "cheiro de gás no hall",
    "pessoa presa no elevador",
    "o elevador parou com a moradora dentro",
    "saiu faísca do quadro",
    "cheiro de queimado no corredor",
    "fio desencapado na garagem",
    "cano estourado no subsolo",
    "vazamento no banheiro",
    "estamos sem água",
    "falta de luz na escada",
    "o portão da garagem não fecha",
]


@pytest.mark.parametrize("texto", EXEMPLOS_DA_REDE)
def test_tudo_que_e_critico_tambem_fura_a_fila_no_mesmo_nivel(texto):
    # Regra de ouro das duas listas: a fila inclui a rede inteira
    nivel_rede, _ = nivel_por_palavra_chave(texto)
    assert nivel_da_fila(texto) >= nivel_rede


def test_palavra_so_da_fila_nao_aciona_a_rede():
    # "elevador" sozinho adianta a classificação, mas não vira alarme
    assert nivel_da_fila("preciso reservar o elevador para a mudança") == Nivel.IMPORTANTE
    assert nivel_por_palavra_chave("preciso reservar o elevador para a mudança") is None


def test_sem_palavra_nenhuma():
    assert nivel_da_fila("segunda via do boleto") == 0
    assert nivel_por_palavra_chave("segunda via do boleto") is None
