from typing import Protocol

import httpx
import numpy as np

LOTE = 32


class ErroEmbeddings(Exception):
    pass


class Embedder(Protocol):
    async def embed(self, textos: list[str]) -> list[np.ndarray]: ...


class OllamaEmbedder:
    def __init__(self, url: str, modelo: str = "bge-m3", timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.timeout = timeout

    async def embed(self, textos: list[str]) -> list[np.ndarray]:
        saida: list[np.ndarray] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as cliente:
                for i in range(0, len(textos), LOTE):
                    r = await cliente.post(
                        f"{self.url}/api/embed",
                        json={
                            "model": self.modelo,
                            "input": textos[i : i + LOTE],
                            # CPU: a GPU fica livre para os modelos de chat
                            "options": {"num_gpu": 0},
                            "keep_alive": "30m",
                        },
                    )
                    r.raise_for_status()
                    for v in r.json()["embeddings"]:
                        a = np.asarray(v, dtype=np.float32)
                        n = np.linalg.norm(a)
                        saida.append(a / n if n else a)
        except httpx.HTTPStatusError as e:
            raise ErroEmbeddings(
                f"O Ollama respondeu com erro {e.response.status_code} ao gerar embeddings."
            ) from e
        except httpx.HTTPError as e:
            raise ErroEmbeddings(
                f"Não consegui falar com o Ollama em {self.url}. Ele está rodando?"
            ) from e
        except (KeyError, ValueError, TypeError) as e:
            raise ErroEmbeddings("Resposta inesperada do Ollama ao gerar embeddings.") from e
        if len(saida) != len(textos):
            raise ErroEmbeddings(
                f"O Ollama devolveu {len(saida)} vetores para {len(textos)} textos."
            )
        return saida
