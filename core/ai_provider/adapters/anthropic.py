#
# /educador/core/ai_provider/adapters/anthropic.py
#

import requests
import json
import time

from ..base import BaseProvider


class AnthropicAdapter(BaseProvider):
    """
    Adaptador para API Anthropic.
    Modelo: claude-haiku-4-5-20251001
    """
    MODEL = "claude-haiku-4-5-20251001"
    LABEL = "Claude Haiku · Anthropic"
    BASE_URL = "https://api.anthropic.com/v1/messages"

    DEFAULT_CONFIG = {
        "temperature": 0.20,
        "max_tokens": 512,
        # "top_p": 0.90,  # ← REMOVIDO - Anthropic não suporta
        # "frequency_penalty": 0.45,  # ← REMOVIDO
        # "presence_penalty": 0.25,   # ← REMOVIDO
        # "top_k": 4,                 # ← REMOVIDO
    }

    def __init__(self, api_key):
        super().__init__(api_key)
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_payload(self, messages, config=None):
        """
        Constrói o payload para a API Anthropic.
        Separa system das demais mensagens.
        """
        system = ""
        msgs = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                msgs.append(m)

        merged = {**self.DEFAULT_CONFIG, **(config or {})}

        payload = {
            "model": self.MODEL,
            "messages": msgs,
            "system": system,  # string, não lista
            "temperature": merged.get("temperature"),
            "max_tokens": merged.get("max_tokens"),
        }

        return {k: v for k, v in payload.items() if v is not None}

    def chat(self, messages, config=None):
        """Chamada síncrona para o modelo Anthropic."""
        if not self.api_key:
            raise ValueError("Chave da API Anthropic não configurada.")

        payload = self._build_payload(messages, config)

        try:
            r = requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return data["content"][0]["text"]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Anthropic excedeu o limite de taxa. Tente novamente.")
            # Log do erro detalhado para diagnóstico
            try:
                erro_detalhe = e.response.json()
                print(f"[Anthropic] Detalhe do erro: {erro_detalhe}")
            except:
                pass
            raise Exception(f"Anthropic erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Anthropic: tempo limite excedido.")
        except Exception as e:
            raise Exception(f"Anthropic falhou: {e}")

    def stream(self, messages, config=None):
        """
        Streaming via Anthropic.
        Nota: A API Anthropic atualmente não suporta streaming no modelo Haiku.
        """
        resposta = self.chat(messages, config)
        yield resposta, self.LABEL