#
# /educador/core/ai_provider/adapters/ollama.py
#

import requests
import json
import time

from ..base import BaseProvider


class OllamaAdapter(BaseProvider):
    """
    Adaptador para Ollama (modelo local).
    Modelo: phi4-mini
    """
    MODEL = "phi4-mini"
    LABEL = "Phi4 Mini · Ollama Local"
    BASE_URL = "http://localhost:11434/v1/chat/completions"

    DEFAULT_CONFIG = {
        "temperature": 0.45,
        "max_tokens": 512,
        "top_p": 0.85,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "top_k": 5,
    }

    def __init__(self, api_key=None):
        # Ollama não usa API Key, mas mantemos o padrão
        super().__init__(api_key)
        self._headers = {
            "Content-Type": "application/json",
        }

    def _build_payload(self, messages, config=None, stream=False):
        """Constrói o payload para a API Ollama."""
        merged = {**self.DEFAULT_CONFIG, **(config or {})}

        payload = {
            "model": self.MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": merged.get("temperature"),
                "num_predict": merged.get("max_tokens"),
                "top_p": merged.get("top_p"),
                "frequency_penalty": merged.get("frequency_penalty"),
                "presence_penalty": merged.get("presence_penalty"),
            },
        }

        if stream:
            payload["stream"] = True

        return {k: v for k, v in payload.items() if v is not None}

    def chat(self, messages, config=None):
        """
        Chamada síncrona para o modelo Ollama.
        """
        # Ollama não precisa de API Key, mas mantemos a verificação por consistência
        payload = self._build_payload(messages, config, stream=False)

        try:
            r = requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                timeout=120,  # timeout maior por rodar local
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Ollama excedeu o limite de taxa. Tente novamente.")
            raise Exception(f"Ollama erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Ollama: tempo limite excedido.")
        except requests.exceptions.ConnectionError:
            raise Exception("Ollama: não foi possível conectar ao servidor local. Certifique-se de que o Ollama está rodando.")
        except Exception as e:
            raise Exception(f"Ollama falhou: {e}")

    def stream(self, messages, config=None):
        """
        Streaming via Ollama.
        Nota: A API OpenAI do Ollama suporta streaming, mas mantemos fallback.
        """
        try:
            payload = self._build_payload(messages, config, stream=True)
            with requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                stream=True,
                timeout=120,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta, self.LABEL
                        except json.JSONDecodeError:
                            continue
                        except Exception:
                            continue
        except Exception as e:
            # Fallback para chat se streaming falhar
            resposta = self.chat(messages, config)
            yield resposta, self.LABEL