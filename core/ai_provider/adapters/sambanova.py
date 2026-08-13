#
# /educador/core/ai_provider/adapters/sambanova.py
#

import requests
import json
import time

from ..base import BaseProvider


class SambaNovaAdapter(BaseProvider):
    """
    Adaptador para API SambaNova.
    Modelo: Meta-Llama-3.3-70B-Instruct
    """
    MODEL = "Meta-Llama-3.3-70B-Instruct"
    LABEL = "Llama-3.3-70B · SambaNova"
    BASE_URL = "https://api.sambanova.ai/v1/chat/completions"

    DEFAULT_CONFIG = {
        "temperature": 0.80,
        "max_tokens": 256,
        "top_p": 0.90,
        "frequency_penalty": 1.20,
        "presence_penalty": 1.00,
        # "top_k": 3,  # REMOVIDO - SambaNova pode não suportar
    }

    def __init__(self, api_key):
        super().__init__(api_key)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, messages, config=None, stream=False):
        """Constrói o payload mesclando DEFAULT_CONFIG com config recebido."""
        merged = {**self.DEFAULT_CONFIG, **(config or {})}

        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": merged.get("temperature"),
            "max_tokens": merged.get("max_tokens"),
            "top_p": merged.get("top_p"),
            "frequency_penalty": merged.get("frequency_penalty"),
            "presence_penalty": merged.get("presence_penalty"),
        }

        if stream:
            payload["stream"] = True

        return {k: v for k, v in payload.items() if v is not None}

    def chat(self, messages, config=None):
        """Chamada síncrona para o modelo SambaNova."""
        if not self.api_key:
            raise ValueError("Chave da API SambaNova não configurada.")

        payload = self._build_payload(messages, config, stream=False)

        try:
            r = requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("SambaNova excedeu o limite de taxa. Tente novamente.")
            raise Exception(f"SambaNova erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("SambaNova: tempo limite excedido.")
        except Exception as e:
            raise Exception(f"SambaNova falhou: {e}")

    def stream(self, messages, config=None):
        """
        Streaming via SambaNova.
        Nota: A API SambaNova atualmente não suporta streaming nativo.
        """
        resposta = self.chat(messages, config)
        yield resposta, self.LABEL