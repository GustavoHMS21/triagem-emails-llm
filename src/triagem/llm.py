"""Cliente de LLM isolado atrás de uma interface.

O classificador só conhece ClienteLLM. Trocar Qwen local por outro modelo ou
provedor é escrever outra classe com o mesmo método, sem mexer no resto.
"""

from typing import Protocol

import httpx


class ClienteLLM(Protocol):
    nome_modelo: str

    def gerar_json(self, sistema: str, usuario: str, schema: dict) -> str:
        """Devolve o texto JSON bruto gerado pelo modelo, seguindo `schema`."""
        ...


class ClienteOllama:
    def __init__(self, url: str, modelo: str, timeout_s: float = 120):
        self.url = url.rstrip("/")
        self.nome_modelo = modelo
        self._http = httpx.Client(timeout=timeout_s)

    def gerar_json(self, sistema: str, usuario: str, schema: dict) -> str:
        resposta = self._http.post(
            f"{self.url}/api/chat",
            json={
                "model": self.nome_modelo,
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
                "format": schema,  # saída estruturada: o Ollama restringe a geração ao schema
                "think": False,  # Qwen3: sem raciocínio longo, só a resposta
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        resposta.raise_for_status()
        return resposta.json()["message"]["content"]
