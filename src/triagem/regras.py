"""Etapa 3: regras de negócio, aplicadas por código sobre a saída do LLM.

O LLM julga só a urgência do conteúdo. Tudo que é regra determinística do
cliente fica aqui, para ser testável e auditável:

  1. Falha do LLM                -> revisão humana
  2. Dúvida entre dois níveis    -> fica no mais alto + revisão humana
  3. Elevador parado             -> urgente se o prédio tem um só elevador
                                    (ou se o nº de elevadores é desconhecido, + revisão)
  4. Palavra-chave crítica       -> rede de segurança caso o LLM subestime
  5. Corpo vazio com anexo       -> revisão humana (anexo não é lido na v1)
  6. Remetente é síndico/subsíndico -> sobe um nível (prioridade de negócio)

Cada regra que mexe no resultado deixa um motivo, que aparece no painel.
"""

from triagem.cadastro import CadastroCondominios, Condominio
from triagem.modelos import Classificacao, EmailLimpo, Nivel, Triagem
from triagem.palavras_chave import nivel_por_palavra_chave

# --- Aplicação das regras ----------------------------------------------------


def aplicar_regras(
    email: EmailLimpo,
    classificacao: Classificacao | None,
    cadastro: CadastroCondominios,
    modelo: str,
    prompt_versao: str,
) -> Triagem:
    motivos: list[str] = []
    revisao = False

    gestor = cadastro.por_gestor(email.original.remetente)
    condominio: Condominio | None
    if gestor:
        condominio = gestor.condominio
    else:
        condominio = cadastro.por_nome(classificacao.condominio_mencionado if classificacao else None)

    # 1. Falha do LLM
    if classificacao is None:
        nivel = Nivel.NORMAL
        revisao = True
        motivos.append("Classificação automática falhou: conferir no Gmail")
    else:
        # Motivos explicam regras de negócio para a atendente. O nível dado pelo
        # modelo não vira motivo (já fica em urgencia_llm), e o "motivo" textual do
        # LLM não é gravado: repete fatos do e-mail (dado pessoal)
        nivel = Nivel.de_texto(classificacao.urgencia)

        # 2. Dúvida entre dois níveis: fica no mais alto, mas uma pessoa confere
        if classificacao.em_duvida:
            revisao = True
            if classificacao.urgencia_alternativa:
                alternativa = Nivel.de_texto(classificacao.urgencia_alternativa)
                if alternativa > nivel:
                    nivel = alternativa
                    motivos.append(f"Classificação em dúvida: subiu para {alternativa.name.lower()}")
            motivos.append("Classificação em dúvida entre dois níveis")

        # 3. Elevador: o LLM não sabe quantos elevadores o prédio tem; o cadastro sabe
        if classificacao.elevador_parado and nivel < Nivel.URGENTE:
            # Na dúvida, urgente + revisão: perder urgência custa mais que alarme falso
            if condominio is None:
                nivel = Nivel.URGENTE
                revisao = True
                motivos.append("Elevador parado em condomínio não identificado: tratado como urgente")
            elif condominio.qtd_elevadores is None:
                nivel = Nivel.URGENTE
                revisao = True
                motivos.append(
                    f"Elevador parado e {condominio.nome} não tem nº de elevadores cadastrado: tratado como urgente"
                )
            elif condominio.qtd_elevadores <= 1:
                nivel = Nivel.URGENTE
                motivos.append(f"Elevador parado e {condominio.nome} tem um só elevador")

    # 4. Rede de segurança por palavra-chave (roda mesmo se o LLM falhou)
    achado = nivel_por_palavra_chave(f"{email.assunto}\n{email.corpo}")
    if achado and achado[0] > nivel:
        nivel_chave, rotulo = achado
        nivel = nivel_chave
        revisao = True
        motivos.append(f"Palavra-chave crítica ({rotulo}): subiu para {nivel_chave.name.lower()}")

    # 5. Conteúdo só no anexo
    if email.corpo_vazio and email.original.anexos:
        revisao = True
        motivos.append("Conteúdo só no anexo: abrir no Gmail")

    # 6. Síndico ou subsíndico sobe um nível (prioridade de negócio, aplicada por último)
    if gestor:
        novo = nivel.subir()
        if novo > nivel:
            papel = {"sindico": "síndico", "subsindico": "subsíndico"}.get(gestor.papel, gestor.papel)
            motivos.append(f"Remetente é {papel} de {gestor.condominio.nome}: subiu para {novo.name.lower()}")
        nivel = novo

    return Triagem(
        email=email,
        classificacao=classificacao,
        categoria=classificacao.categoria if classificacao else None,
        condominio_id=condominio.id if condominio else None,
        remetente_gestor=gestor is not None,
        nivel_final=nivel,
        requer_revisao=revisao,
        motivos=motivos,
        modelo=modelo,
        prompt_versao=prompt_versao,
    )
