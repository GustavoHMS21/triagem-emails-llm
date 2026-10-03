# Triagem de e-mails: Alvorada Gestão Condominial

Classifica os e-mails da caixa de atendimento por setor e urgência e monta uma fila ordenada por prioridade, para que vazamento, gás e elevador parado não esperem atrás de pedidos de segunda via.

Os dados em `data/` são fictícios.

## Como funciona

```
e-mails → limpeza → filtro → LLM (JSON validado) → regras de negócio → PostgreSQL → painel
```

- **Limpeza:** remove histórico de resposta, rodapé de celular, assinatura e "URGENTE" do assunto; preserva o conteúdo de e-mails encaminhados.
- **Filtro:** propaganda (descadastro + marcas de marketing) vai direto para o banco como `lixo`, sem chamar o LLM. O restante é classificado por ordem de risco: e-mails com palavra-chave crítica passam primeiro.
- **LLM:** Qwen3 via Ollama, com saída restrita a um JSON Schema e validada com Pydantic. Classifica só o que depende de linguagem: categoria e urgência do conteúdo.
- **Regras de negócio:** síndico sobe um nível, elevador parado em prédio com um elevador vira urgente, dúvida do modelo vai para revisão humana, palavra-chave crítica funciona como rede de segurança. Cada decisão grava o motivo.
- **Falhas:** se o LLM falhar, o e-mail entra na fila com revisão humana; o pipeline não para. Reprocessar é idempotente.

## Rodando

Pré-requisitos: [uv](https://docs.astral.sh/uv/), Docker e [Ollama](https://ollama.com).

```bash
cp .env.example .env
uv sync
ollama pull qwen3:8b
docker compose up -d                                         # Postgres + tabela (porta 5433)

uv run pytest
uv run python -m triagem.pipeline data/emails/ --sem-banco   # só imprime
uv run python -m triagem.pipeline data/emails/               # grava no banco
uv run streamlit run src/triagem/painel.py                   # fila (http://127.0.0.1:8501)
```

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `src/triagem/entrada.py` | Fonte de e-mails e normalização de formatos |
| `src/triagem/limpeza.py` | Limpeza do texto antes do LLM |
| `src/triagem/filtro.py` | Propaganda e ordem de classificação |
| `src/triagem/llm.py` | Interface do LLM e cliente Ollama |
| `src/triagem/classificador.py` | Prompt, chamada, validação e novas tentativas |
| `src/triagem/prompts/` | Prompts versionados |
| `src/triagem/regras.py` | Regras de negócio e rede de segurança |
| `src/triagem/repositorio.py` | Persistência no PostgreSQL |
| `src/triagem/painel.py` | Painel da fila (Streamlit) |
| `data/condominios.csv` | Condomínios, nº de elevadores e e-mail do síndico |
| `data/amostras/` | Amostra de e-mails para avaliação |

## Roadmap

- Leitura direta do Gmail (nova `FonteEmails`), com pool de conexões (`psycopg_pool`) para o processo contínuo
- Login no painel
- Leitura do conteúdo dos anexos (PDF e fotos)
- Integração com o sistema de gestão do condomínio
