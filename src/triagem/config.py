"""Configuração por ambiente (variáveis de ambiente e arquivo .env).

Carregada sob demanda com carregar_config(), e não no import: importar um
módulo do projeto não lê arquivo nenhum, e um teste pode criar um Config
com os valores que quiser.
"""

from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_modelo: str = "qwen3:8b"
    llm_timeout_s: float = 120
    llm_tentativas: int = 2

    database_url: str = "postgresql://triagem:triagem@127.0.0.1:5433/triagem"
    migracoes_dir: Path = Path("db")

    condominios_csv: Path = Path("data/condominios.csv")
    gestores_csv: Path = Path("data/gestores.csv")


@cache
def carregar_config() -> Config:
    """Lê o ambiente na primeira chamada e reaproveita nas seguintes."""
    return Config()
