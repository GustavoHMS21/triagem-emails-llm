"""Avaliação do pipeline contra o gabarito.

Uso:
    uv run python -m triagem.avaliacao rodar        # chama o LLM; retoma de onde parou
    uv run python -m triagem.avaliacao relatorio    # só calcula as métricas

`rodar` executa o mesmo `processar()` do pipeline (filtro, ordem, LLM, regras),
trocando só o destino: em vez do PostgreSQL (a fila real das atendentes), um
arquivo JSONL, uma linha por e-mail, gravada na hora. Se a execução cair, a
próxima pula o que já está no arquivo.
"""

import argparse
import csv
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from triagem.classificador import Classificador
from triagem.config import config
from triagem.entrada import FonteJson
from triagem.filtro import FILTRO_VERSAO
from triagem.llm import ClienteOllama
from triagem.modelos import Triagem
from triagem.pipeline import processar
from triagem.regras import CadastroCondominios

log = logging.getLogger("triagem.avaliacao")

AMOSTRA = Path("data/amostras/emails_setembro.json")
GABARITO = Path("data/amostras/gabarito_setembro.csv")
RESULTADOS = Path("resultados/avaliacao_setembro.jsonl")

NIVEIS = ["normal", "importante", "urgente"]

# Casos difíceis acompanhados um a um no relatório
CASOS_ESPECIAIS = {
    "E072": "tenta manipular o LLM (pede para classificar como URGENTE)",
    "E021": "golpe: conta será bloqueada",
    "E037": "golpe: pede CPF",
    "E032": 'negação: "não tem cheiro de gás"',
    "E113": 'passado: "quando fiquei presa no elevador"',
    "E064": 'erro de digitação: "vasamento"',
    "E048": "conteúdo dentro de e-mail encaminhado",
    "E002": "URGENTE falso no assunto",
}


# --- Execução ----------------------------------------------------------------


class ArquivoResultados:
    """Destino do pipeline (mesma interface do Repositorio) que grava em JSONL.

        with ArquivoResultados(caminho) as destino:
            processar(fonte, classificador, cadastro, destino)
    """

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._feitos: set[str] = set()
        self._arquivo = None
        self._ultimo = 0.0

    def __enter__(self) -> "ArquivoResultados":
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        if self.caminho.exists():
            linhas = self.caminho.read_text(encoding="utf-8").splitlines()
            self._feitos = {json.loads(l)["id"] for l in linhas if l.strip()}
        self._arquivo = open(self.caminho, "a", encoding="utf-8")
        self._ultimo = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self._arquivo.close()

    def ja_triado(self, email_id: str) -> bool:
        return email_id in self._feitos

    def salvar(self, t: Triagem) -> bool:
        # O pipeline processa um e-mail por vez: o intervalo desde o último
        # salvamento é, na prática, o tempo de classificação deste e-mail
        agora = time.perf_counter()
        segundos, self._ultimo = agora - self._ultimo, agora

        propaganda = t.prompt_versao == FILTRO_VERSAO
        c = t.classificacao
        registro = {
            "id": t.email.original.id,
            "filtrado_como_propaganda": propaganda,
            "llm_falhou": c is None and not propaganda,
            "urgencia_llm": c.urgencia if c else None,
            "categoria": t.categoria,
            "nivel_final": t.nivel_final.name.lower(),
            "requer_revisao": t.requer_revisao,
            "motivos": t.motivos,
            "segundos": round(segundos, 1),
        }
        self._arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        self._arquivo.flush()  # gravado na hora: uma queda não perde o que já rodou
        self._feitos.add(registro["id"])
        return True


def rodar(amostra: Path = AMOSTRA, saida: Path = RESULTADOS, classificador: Classificador | None = None) -> None:
    """Roda o pipeline de produção sobre a amostra, gravando no arquivo de resultados."""
    if classificador is None:
        llm = ClienteOllama(config.ollama_url, config.ollama_modelo, config.llm_timeout_s)
        classificador = Classificador(llm, config.llm_tentativas)
    cadastro = CadastroCondominios.de_csv(config.condominios_csv, config.gestores_csv)

    with ArquivoResultados(saida) as destino:
        processar(FonteJson(amostra), classificador, cadastro, destino)


# --- Métricas ----------------------------------------------------------------


@dataclass
class Metricas:
    total: int
    urgentes_esperados: int
    recall_urgente_sistema: float
    recall_urgente_llm: float
    alarmes_falsos_sistema: int
    alarmes_falsos_llm: int
    acerto_categoria: float
    em_revisao: int
    falhas_llm: int
    filtrados_propaganda: int
    urgentes_perdidos: list[str] = field(default_factory=list)
    alarmes_falsos: list[str] = field(default_factory=list)
    confusao: Counter = field(default_factory=Counter)  # (esperado, obtido) -> quantidade


def calcular_metricas(resultados: list[dict], gabarito: dict[str, dict]) -> Metricas:
    """Função pura: compara resultados com o gabarito, sem LLM, banco ou arquivo.

    "LLM sozinho" usa a urgência que o modelo deu ao conteúdo, sem nenhuma regra
    de negócio; comparar com o sistema completo mostra quanto as regras corrigem.
    """
    por_id = {r["id"]: r for r in resultados}
    ids = [i for i in gabarito if i in por_id]

    def urgente_llm(r):
        return r["urgencia_llm"] == "urgente"

    esperados_urgentes = [i for i in ids if gabarito[i]["nivel_esperado"] == "urgente"]
    nao_urgentes = [i for i in ids if gabarito[i]["nivel_esperado"] != "urgente"]

    pegos_sistema = [i for i in esperados_urgentes if por_id[i]["nivel_final"] == "urgente"]
    pegos_llm = [i for i in esperados_urgentes if urgente_llm(por_id[i])]
    alarmes = [i for i in nao_urgentes if por_id[i]["nivel_final"] == "urgente"]
    alarmes_llm = [i for i in nao_urgentes if urgente_llm(por_id[i])]

    categoria_certa = [
        i for i in ids
        if por_id[i]["categoria"] in gabarito[i]["categorias_aceitas"].split("|")
    ]

    def razao(parte, todo):
        return len(parte) / len(todo) if todo else 0.0

    return Metricas(
        total=len(ids),
        urgentes_esperados=len(esperados_urgentes),
        recall_urgente_sistema=razao(pegos_sistema, esperados_urgentes),
        recall_urgente_llm=razao(pegos_llm, esperados_urgentes),
        alarmes_falsos_sistema=len(alarmes),
        alarmes_falsos_llm=len(alarmes_llm),
        acerto_categoria=razao(categoria_certa, ids),
        em_revisao=sum(por_id[i]["requer_revisao"] for i in ids),
        falhas_llm=sum(por_id[i]["llm_falhou"] for i in ids),
        filtrados_propaganda=sum(por_id[i]["filtrado_como_propaganda"] for i in ids),
        urgentes_perdidos=sorted(set(esperados_urgentes) - set(pegos_sistema)),
        alarmes_falsos=sorted(alarmes),
        confusao=Counter((gabarito[i]["nivel_esperado"], por_id[i]["nivel_final"]) for i in ids),
    )


# --- Relatório ---------------------------------------------------------------


def carregar(resultados: Path = RESULTADOS, gabarito: Path = GABARITO) -> tuple[list[dict], dict[str, dict]]:
    linhas = [json.loads(l) for l in resultados.read_text(encoding="utf-8").splitlines() if l.strip()]
    with open(gabarito, encoding="utf-8", newline="") as f:
        return linhas, {g["id"]: g for g in csv.DictReader(f)}


def relatorio() -> None:
    resultados, gabarito = carregar()
    m = calcular_metricas(resultados, gabarito)
    por_id = {r["id"]: r for r in resultados}
    tempos = [r["segundos"] for r in resultados if not r["filtrado_como_propaganda"]]

    print(f"\nAvaliação: {m.total} de {len(gabarito)} e-mails ({m.urgentes_esperados} urgentes esperados)\n")
    print(f"{'':28s}{'LLM sozinho':>14s}{'Sistema':>10s}")
    print(f"{'Recall de urgentes':28s}{m.recall_urgente_llm:>14.0%}{m.recall_urgente_sistema:>10.0%}")
    print(f"{'Alarmes falsos (urgente)':28s}{m.alarmes_falsos_llm:>14d}{m.alarmes_falsos_sistema:>10d}")
    print(f"\nAcerto de categoria: {m.acerto_categoria:.0%}")
    print(f"Em revisão humana: {m.em_revisao}   Falhas do LLM: {m.falhas_llm}   Propaganda filtrada: {m.filtrados_propaganda}")
    if tempos:
        print(f"Tempo médio por e-mail classificado: {sum(tempos) / len(tempos):.0f}s")

    print("\nMatriz de confusão (linhas = esperado, colunas = sistema)")
    print(f"{'':12s}" + "".join(f"{n:>12s}" for n in NIVEIS))
    for esperado in NIVEIS:
        print(f"{esperado:12s}" + "".join(f"{m.confusao[(esperado, obtido)]:>12d}" for obtido in NIVEIS))

    def detalhe(i):
        r = por_id[i]
        return f"  {i} esperado={gabarito[i]['nivel_esperado']:10s} sistema={r['nivel_final']:10s} llm={r['urgencia_llm']}\n      " + " | ".join(r["motivos"])

    if m.urgentes_perdidos:
        print("\nURGENTES PERDIDOS:")
        for i in m.urgentes_perdidos:
            print(detalhe(i))
    if m.alarmes_falsos:
        print("\nALARMES FALSOS:")
        for i in m.alarmes_falsos:
            print(detalhe(i))

    print("\nCASOS ESPECIAIS:")
    for i, descricao in CASOS_ESPECIAIS.items():
        if i in por_id:
            r = por_id[i]
            print(f"  {i} ({descricao}): esperado={gabarito[i]['nivel_esperado']}, sistema={r['nivel_final']}"
                  f"{' +revisão' if r['requer_revisao'] else ''}, categoria={r['categoria']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação do pipeline contra o gabarito")
    parser.add_argument("acao", choices=["rodar", "relatorio"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    rodar() if args.acao == "rodar" else relatorio()


if __name__ == "__main__":
    main()
