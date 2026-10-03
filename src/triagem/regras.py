"""Etapa 3: regras de negócio, aplicadas por código sobre a saída do LLM.

O LLM julga só a urgência do conteúdo. Tudo que é regra determinística do
cliente fica aqui, para ser testável e auditável:

  1. Falha do LLM                -> revisão humana
  2. Dúvida entre dois níveis    -> fica no mais alto + revisão humana
  3. Elevador parado             -> urgente se o prédio tem um só elevador
  4. Palavra-chave crítica       -> rede de segurança caso o LLM subestime
  5. Corpo vazio com anexo       -> revisão humana (anexo não é lido na v1)
  6. Remetente é síndico         -> sobe um nível (prioridade de negócio)

Cada regra que mexe no resultado deixa um motivo, que aparece no painel.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from triagem.modelos import Classificacao, EmailLimpo, Nivel, Triagem

# --- Dados de referência -----------------------------------------------------


@dataclass(frozen=True)
class Condominio:
    id: str
    nome: str
    qtd_elevadores: int
    email_sindico: str


class CadastroCondominios:
    def __init__(self, condominios: list[Condominio]):
        self._por_id = {c.id: c for c in condominios}
        self._por_email_sindico = {c.email_sindico.lower(): c for c in condominios if c.email_sindico}

    @classmethod
    def de_csv(cls, caminho: Path) -> "CadastroCondominios":
        with open(caminho, encoding="utf-8", newline="") as f:
            return cls([
                Condominio(
                    id=linha["id"],
                    nome=linha["nome"],
                    qtd_elevadores=int(linha["qtd_elevadores"]),
                    email_sindico=linha["email_sindico"].strip(),
                )
                for linha in csv.DictReader(f)
            ])

    def por_sindico(self, email: str) -> Condominio | None:
        return self._por_email_sindico.get(email.strip().lower())

    def por_nome(self, nome: str | None) -> Condominio | None:
        if not nome:
            return None
        alvo = _normalizar(nome)
        for c in self._por_id.values():
            nome_c = _normalizar(c.nome)
            if alvo in nome_c or nome_c in alvo:
                return c
        return None


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    sem_prefixo = re.sub(r"\b(condominio|cond|edificio|ed|residencial|res)\b\.?", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", sem_prefixo).strip()


# --- Palavras-chave críticas (rede de segurança) -----------------------------
# Não substituem o LLM: só pegam o caso em que ele subestimou algo grave.
# O nível indicado é o piso; quem confirma é a atendente na revisão.

PALAVRAS_CRITICAS: dict[str, Nivel] = {
    r"cheiro de g[aá]s|vazamento de g[aá]s": Nivel.URGENTE,
    r"pres[oa]s? no elevador|gente presa|pessoa presa": Nivel.URGENTE,
    r"elevador.{0,60}dentro|dentro do elevador": Nivel.URGENTE,  # "parou com a dona Cida dentro" (E039)
    r"inc[eê]ndio|fuma[cç]a|fa[ií]sca|curto[- ]circuito": Nivel.URGENTE,
    r"cheiro de queimado": Nivel.URGENTE,  # E132
    r"fio desencapado": Nivel.URGENTE,
    r"cano estourad|estourou o cano|alagad|alagamento": Nivel.URGENTE,
    r"vazamento|vazando|vasament|infiltra": Nivel.IMPORTANTE,  # "vasamento", erro comum (E064)
    r"sem [aá]gua|falta de [aá]gua": Nivel.IMPORTANTE,
    r"sem luz|falta de luz|apag[aã]o": Nivel.IMPORTANTE,
    r"port[aã]o.{0,30}(n[aã]o fecha|aberto|quebrad)": Nivel.IMPORTANTE,
}
_PALAVRAS_COMPILADAS = [(re.compile(p, re.IGNORECASE), n) for p, n in PALAVRAS_CRITICAS.items()]


def nivel_por_palavra_chave(texto: str) -> tuple[Nivel, str] | None:
    """Devolve o maior nível acionado por palavra-chave e o trecho encontrado."""
    achados = [(n, m.group(0)) for p, n in _PALAVRAS_COMPILADAS if (m := p.search(texto))]
    return max(achados, key=lambda a: a[0]) if achados else None


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

    sindico_de = cadastro.por_sindico(email.original.remetente)
    condominio = sindico_de or cadastro.por_nome(classificacao and classificacao.condominio_mencionado)

    # 1. Falha do LLM
    if classificacao is None:
        nivel = Nivel.NORMAL
        revisao = True
        motivos.append("LLM não devolveu classificação válida")
    else:
        nivel = Nivel.de_texto(classificacao.urgencia)
        motivos.append(f"LLM: {classificacao.urgencia} ({classificacao.motivo})")

        # 2. Dúvida entre dois níveis: fica no mais alto, mas uma pessoa confere
        if classificacao.em_duvida:
            revisao = True
            if classificacao.urgencia_alternativa:
                alternativa = Nivel.de_texto(classificacao.urgencia_alternativa)
                if alternativa > nivel:
                    nivel = alternativa
                    motivos.append(f"Dúvida do LLM: subiu para {alternativa.name.lower()}")
            motivos.append("LLM em dúvida entre dois níveis")

        # 3. Elevador: o LLM não sabe quantos elevadores o prédio tem; o cadastro sabe
        if classificacao.elevador_parado and nivel < Nivel.URGENTE:
            if condominio is None:
                nivel = Nivel.URGENTE
                revisao = True
                motivos.append("Elevador parado em condomínio não identificado: tratado como urgente")
            elif condominio.qtd_elevadores <= 1:
                nivel = Nivel.URGENTE
                motivos.append(f"Elevador parado e {condominio.nome} tem um só elevador")

    # 4. Rede de segurança por palavra-chave (roda mesmo se o LLM falhou)
    achado = nivel_por_palavra_chave(f"{email.assunto}\n{email.corpo}")
    if achado and achado[0] > nivel:
        nivel_chave, trecho = achado
        nivel = nivel_chave
        revisao = True
        motivos.append(f'Palavra-chave crítica "{trecho}": subiu para {nivel_chave.name.lower()}')

    # 5. Conteúdo só no anexo
    if email.corpo_vazio and email.original.anexos:
        revisao = True
        motivos.append("Corpo vazio com anexo: conteúdo não lido na v1")

    # 6. Síndico sobe um nível (prioridade de negócio, aplicada por último)
    if sindico_de:
        novo = nivel.subir()
        if novo > nivel:
            motivos.append(f"Remetente é síndico de {sindico_de.nome}: subiu para {novo.name.lower()}")
        nivel = novo

    return Triagem(
        email=email,
        classificacao=classificacao,
        categoria=classificacao.categoria if classificacao else None,
        condominio_id=condominio.id if condominio else None,
        remetente_sindico=sindico_de is not None,
        nivel_final=nivel,
        requer_revisao=revisao,
        motivos=motivos,
        modelo=modelo,
        prompt_versao=prompt_versao,
    )
