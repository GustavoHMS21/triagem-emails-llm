# Triagem de e-mails: Alvorada Gestão Condominial

Classifica os e-mails da caixa de atendimento por setor e urgência e monta uma fila ordenada por prioridade, para que vazamento, gás e elevador parado não esperem atrás de pedidos de segunda via.

Caso fictício para portfólio. Contexto completo do cliente em [02-alvorada-gestao-condominial.md](02-alvorada-gestao-condominial.md).

## Como funciona

```
e-mails → limpeza → Qwen (JSON validado) → regras de negócio → PostgreSQL → painel
```

O LLM julga só o que depende de linguagem: categoria e urgência do conteúdo. Regras determinísticas do cliente (síndico sobe um nível, regra do elevador, dúvida vai para revisão, palavra-chave crítica) ficam em código testado, em [src/triagem/regras.py](src/triagem/regras.py).

## Rodando

Pré-requisitos: [uv](https://docs.astral.sh/uv/), Docker e [Ollama](https://ollama.com).

```bash
cp .env.example .env
uv sync
ollama pull qwen3:8b
docker compose up -d                                   # Postgres + tabela (porta 5433)

uv run pytest                                          # testes das regras e da limpeza
uv run python -m triagem.pipeline data/emails/ --sem-banco   # só imprime
uv run python -m triagem.pipeline data/emails/               # grava no banco
uv run streamlit run src/triagem/painel.py             # fila
```

## Estrutura

| Arquivo | Etapa |
|---|---|
| `src/triagem/entrada.py` | Fonte de e-mails (JSON; Gmail entra aqui depois) |
| `src/triagem/limpeza.py` | Remove histórico, rodapé de celular, assinatura e "URGENTE" |
| `src/triagem/llm.py` | Cliente do LLM atrás de interface |
| `src/triagem/classificador.py` | Chama o LLM, valida com Pydantic, tenta de novo |
| `src/triagem/prompts/` | Prompts versionados |
| `src/triagem/regras.py` | Regras de negócio e rede de segurança |
| `src/triagem/repositorio.py` | PostgreSQL |
| `src/triagem/painel.py` | Painel Streamlit |
| `data/condominios.csv` | Condomínios, nº de elevadores e e-mail do síndico |

## Documentação técnica

- [docs/decisoes-tecnicas.md](docs/decisoes-tecnicas.md): integrações (Ollama, PostgreSQL, Gmail), validação, retry, testes
- [docs/seguranca.md](docs/seguranca.md): riscos, controles e como foram verificados

## Roadmap (fora da v1)

- Leitura direta do Gmail (nova `FonteEmails`), com pool de conexões (`psycopg_pool`) para o processo contínuo
- Leitura do conteúdo dos anexos (PDF e fotos)
- Integração com o CondoGestor (pendente: confirmar se há API)
- WhatsApp
