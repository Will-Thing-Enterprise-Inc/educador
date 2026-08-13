#
# /educador/core/ai_provider/adapters/cerebras.py
#

import requests
import json
import time

from ..base import BaseProvider


class CerebrasAdapter(BaseProvider):
    """
    Adaptador para API Cerebras.
    Modelo: gpt-oss-120b
    """
    MODEL = "gpt-oss-120b"
    LABEL = "gpt-oss-120b · Cerebras"
    BASE_URL = "https://api.cerebras.ai/v1/chat/completions"

    DEFAULT_CONFIG = {
        "temperature": 0.65,
        "max_tokens": 512,
        "top_p": 0.85,
        "reasoning_effort": "low",  # gpt-oss-120b: reduz o raciocínio interno
        # "top_k": 3,              # ← REMOVIDO - Cerebras não suporta
        # "frequency_penalty": 1.50, # ← REMOVIDO
        # "presence_penalty": 1.00,  # ← REMOVIDO
    }

    def __init__(self, api_key):
        super().__init__(api_key)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    #--------------------------------------------
    def _build_payload(self, messages, config=None, stream=False):
        """Constrói o payload mesclando DEFAULT_CONFIG com config recebido."""
        merged = {**self.DEFAULT_CONFIG, **(config or {})}

        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": merged.get("temperature"),
            "max_tokens": merged.get("max_tokens"),
            "top_p": merged.get("top_p"),
            "reasoning_effort": merged.get("reasoning_effort"),
        }

        if stream:
            payload["stream"] = True

        return {k: v for k, v in payload.items() if v is not None}

    #--------------------------------------------
    def chat(self, messages, config=None):
        """Chamada síncrona para o modelo Cerebras."""
        if not self.api_key:
            raise ValueError("Chave da API Cerebras não configurada.")

        payload = self._build_payload(messages, config, stream=False)

        try:
            r = requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()

            choice_message = data["choices"][0]["message"]
            content = choice_message.get("content")

            if not content:
                raise Exception(
                    "Cerebras: resposta sem conteúdo — possível estouro de "
                    "max_tokens durante o raciocínio interno do modelo."
                )

            return content

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Cerebras excedeu o limite de taxa. Tente novamente.")
            raise Exception(f"Cerebras erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Cerebras: tempo limite excedido.")
        except Exception as e:
            raise Exception(f"Cerebras falhou: {e}")

    #--------------------------------------------
    def stream(self, messages, config=None):
        """
        Streaming via Cerebras.
        Nota: A API Cerebras atualmente não suporta streaming nativo.
        """
        resposta = self.chat(messages, config)
        yield resposta, self.LABEL