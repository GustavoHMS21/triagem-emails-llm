"""Cliente de LLM isolado atrás de uma interface.

O classificador só conhece ClienteLLM. Trocar Qwen local por outro modelo ou
provedor é escrever outra classe com o mesmo método, sem mexer no resto.
"""

from typing import Protocol

import httpx


class ErroLLM(Exception):
    """Falha ao obter resposta do LLM (rede, timeout, resposta fora do formato).

    Cada adaptador traduz os erros do seu provedor para este, para quem usa a
    interface não precisar conhecer HTTP, SDKs ou formatos de cada provedor.
    """


class ClienteLLM(Protocol):
    nome_modelo: str

    def gerar_json(self, sistema: str, usuario: str, schema: dict) -> str:
        """Devolve o texto JSON bruto gerado pelo modelo, seguindo `schema`.

        Levanta ErroLLM se não conseguir uma resposta.
        """
        ...


class ClienteOllama:
    def __init__(self, url: str, modelo: str, timeout_s: float = 120, http: httpx.Client | None = None):
        self.url = url.rstrip("/")
        self.nome_modelo = modelo
        self._http = http or httpx.Client(timeout=timeout_s)

    def gerar_json(self, sistema: str, usuario: str, schema: dict) -> str:
        try:
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
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as erro:
            # ValueError: corpo não é JSON; KeyError/TypeError: JSON sem message.content
            raise ErroLLM(f"{type(erro).__name__}: {erro}") from erro
