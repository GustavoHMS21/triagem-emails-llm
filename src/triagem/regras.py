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

import csv
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from triagem.modelos import Classificacao, EmailLimpo, Nivel, Triagem

# --- Dados de referência -----------------------------------------------------


@dataclass(frozen=True)
class Condominio:
    id: str
    nome: str
    qtd_elevadores: int | None  # None: não informado


@dataclass(frozen=True)
class Gestor:
    """Síndico ou subsíndico. Uma pessoa pode ter mais de um e-mail (uma linha por e-mail)."""

    condominio: Condominio
    papel: str  # "sindico" ou "subsindico"
    nome: str
    email: str


class CadastroCondominios:
    def __init__(self, condominios: Sequence[Condominio], gestores: Sequence[Gestor] = ()):
        self._por_id = {c.id: c for c in condominios}
        self._gestor_por_email = {g.email.lower(): g for g in gestores}

    @classmethod
    def de_csv(cls, caminho_condominios: Path, caminho_gestores: Path) -> "CadastroCondominios":
        with open(caminho_condominios, encoding="utf-8", newline="") as f:
            condominios = [
                Condominio(
                    id=linha["id"],
                    nome=linha["nome"],
                    qtd_elevadores=int(linha["qtd_elevadores"]) if linha["qtd_elevadores"].strip() else None,
                )
                for linha in csv.DictReader(f)
            ]
        por_id = {c.id: c for c in condominios}
        with open(caminho_gestores, encoding="utf-8", newline="") as f:
            gestores = [
                Gestor(
                    condominio=por_id[linha["condominio_id"]],
                    papel=linha["papel"].strip(),
                    nome=linha["nome"].strip(),
                    email=linha["email"].strip(),
                )
                for linha in csv.DictReader(f)
            ]
        return cls(condominios, gestores)

    def por_id(self, condominio_id: str | None) -> Condominio | None:
        return self._por_id.get(condominio_id) if condominio_id else None

    def por_gestor(self, email: str) -> Gestor | None:
        """Síndico ou subsíndico pelo e-mail do remetente. Assinatura no texto não conta."""
        return self._gestor_por_email.get(email.strip().lower())

    def por_nome(self, nome: str | None) -> Condominio | None:
        if not nome:
            return None
        alvo = _normalizar(nome)
        if not alvo:  # ex.: o LLM devolveu só "Condomínio"
            return None
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

# padrão -> (nível, rótulo). O motivo gravado usa o rótulo, nunca o trecho
# encontrado: padrões como "elevador.{0,60}dentro" capturam texto livre do
# e-mail, que pode ter nome de pessoa.
PALAVRAS_CRITICAS: dict[str, tuple[Nivel, str]] = {
    r"cheiro de g[aá]s|vazamento de g[aá]s": (Nivel.URGENTE, "cheiro de gás"),
    r"pres[oa]s? no elevador|gente presa|pessoa presa": (Nivel.URGENTE, "pessoa presa no elevador"),
    r"elevador.{0,60}dentro|dentro do elevador": (Nivel.URGENTE, "pessoa presa no elevador"),  # E039
    r"inc[eê]ndio|fuma[cç]a|fa[ií]sca|curto[- ]circuito": (Nivel.URGENTE, "fogo ou faísca"),
    r"cheiro de queimado": (Nivel.URGENTE, "cheiro de queimado"),  # E132
    r"fio desencapado": (Nivel.URGENTE, "fio desencapado"),
    r"cano estourad|estourou o cano|alagad|alagamento": (Nivel.URGENTE, "cano estourado ou alagamento"),
    r"vazamento|vazando|vasament|infiltra": (Nivel.IMPORTANTE, "vazamento ou infiltração"),  # "vasamento" (E064)
    r"sem [aá]gua|falta de [aá]gua": (Nivel.IMPORTANTE, "falta de água"),
    r"sem luz|falta de luz|apag[aã]o": (Nivel.IMPORTANTE, "falta de luz"),
    r"port[aã]o.{0,30}(n[aã]o fecha|aberto|quebrad)": (Nivel.URGENTE, "portão que não fecha"),
}
_PALAVRAS_COMPILADAS = [(re.compile(p, re.IGNORECASE), n, r) for p, (n, r) in PALAVRAS_CRITICAS.items()]


def nivel_por_palavra_chave(texto: str) -> tuple[Nivel, str] | None:
    """Devolve o maior nível acionado por palavra-chave e o rótulo do padrão."""
    achados = [(n, rotulo) for p, n, rotulo in _PALAVRAS_COMPILADAS if p.search(texto)]
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
        remetente_sindico=gestor is not None,  # síndico ou subsíndico
        nivel_final=nivel,
        requer_revisao=revisao,
        motivos=motivos,
        modelo=modelo,
        prompt_versao=prompt_versao,
    )
