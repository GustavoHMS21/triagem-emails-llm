from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_modelo: str = "qwen3:8b"
    llm_timeout_s: float = 120
    llm_tentativas: int = 2

    database_url: str = "postgresql://triagem:triagem@127.0.0.1:5433/triagem"

    condominios_csv: Path = Path("data/condominios.csv")
    gestores_csv: Path = Path("data/gestores.csv")


config = Config()
