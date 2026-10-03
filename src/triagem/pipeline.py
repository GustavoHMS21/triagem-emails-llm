"""Orquestra as etapas: entrada -> limpeza -> LLM -> regras -> banco.

Uso:
    uv run python -m triagem.pipeline data/emails/
    uv run python -m triagem.pipeline data/emails/exemplos.json --sem-banco
"""

import argparse
import logging
from contextlib import nullcontext
from pathlib import Path

from triagem.classificador import PROMPT_VERSAO, Classificador
from triagem.config import config
from triagem.entrada import FonteEmails, FonteJson
from triagem.filtro import chave_da_fila, motivo_propaganda, triagem_de_propaganda
from triagem.limpeza import limpar
from triagem.llm import ClienteOllama
from triagem.modelos import Triagem
from triagem.regras import CadastroCondominios, aplicar_regras
from triagem.repositorio import Repositorio

log = logging.getLogger("triagem")


def processar(
    fonte: FonteEmails,
    classificador: Classificador,
    cadastro: CadastroCondominios,
    repositorio: Repositorio | None,
) -> list[Triagem]:
    # Fase 1: ler todos, pular os já triados e limpar
    novos = []
    for email in fonte.ler():
        if repositorio and repositorio.ja_triado(email.id):
            log.info("%s já triado, pulando", email.id)
            continue
        novos.append(limpar(email))

    # Fase 2: propaganda vai direto para o banco, sem gastar LLM
    resultados = []
    para_classificar = []
    for limpo in novos:
        motivo = motivo_propaganda(limpo)
        if motivo:
            resultados.append(_registrar(triagem_de_propaganda(limpo, motivo), repositorio))
        else:
            para_classificar.append(limpo)

    # Fase 3: quem tem palavra-chave crítica passa primeiro pelo LLM
    for limpo in sorted(para_classificar, key=chave_da_fila):
        classificacao = classificador.classificar(limpo)
        triagem = aplicar_regras(
            limpo, classificacao, cadastro, classificador.llm.nome_modelo, PROMPT_VERSAO
        )
        resultados.append(_registrar(triagem, repositorio))
    return resultados


def _registrar(triagem: Triagem, repositorio: Repositorio | None) -> Triagem:
    if repositorio:
        repositorio.salvar(triagem)
    log.info(
        "%-12s %-10s revisão=%-5s %s",
        triagem.email.original.id, triagem.nivel_final.name, triagem.requer_revisao,
        triagem.email.assunto[:60],
    )
    return triagem


def main() -> None:
    parser = argparse.ArgumentParser(description="Triagem de e-mails da Alvorada")
    parser.add_argument("caminho", type=Path, help="Arquivo .json ou pasta com .json")
    parser.add_argument("--sem-banco", action="store_true", help="Só imprime, não grava no Postgres")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    llm = ClienteOllama(config.ollama_url, config.ollama_modelo, config.llm_timeout_s)
    banco = nullcontext() if args.sem_banco else Repositorio(config.database_url)
    with banco as repositorio:
        resultados = processar(
            fonte=FonteJson(args.caminho),
            classificador=Classificador(llm, config.llm_tentativas),
            cadastro=CadastroCondominios.de_csv(config.condominios_csv),
            repositorio=repositorio,
        )

    if args.sem_banco:
        for t in sorted(resultados, key=lambda t: (-t.nivel_final, not t.requer_revisao)):
            print(f"\n[{t.nivel_final.name}{' | REVISÃO' if t.requer_revisao else ''}] {t.email.assunto}")
            for motivo in t.motivos:
                print(f"  - {motivo}")


if __name__ == "__main__":
    main()
