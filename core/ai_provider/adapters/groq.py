#
# /educador/core/ai_provider/adapters/groq.py
#

import requests
import json
import time

from ..base import BaseProvider


class GroqAdapter(BaseProvider):
    """
    Adaptador para API Groq.
    Modelo: openai/gpt-oss-120b
    """
    MODEL = "openai/gpt-oss-120b"
    LABEL = "GPT-OSS 120B · Groq"
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    DEFAULT_CONFIG = {
        "temperature": 0.75,
        "max_tokens": 512,
        "top_p": 0.85,
        "frequency_penalty": 0.80,
        "presence_penalty": 1.50,
        "reasoning_effort": "low",  # gpt-oss-120b: reduz o raciocínio interno
        # "top_k": 4,  # ← REMOVIDO - Groq não suporta
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
            "frequency_penalty": merged.get("frequency_penalty"),
            "presence_penalty": merged.get("presence_penalty"),
            "reasoning_effort": merged.get("reasoning_effort"),
        }

        if stream:
            payload["stream"] = True

        return {k: v for k, v in payload.items() if v is not None}

    #--------------------------------------------
    def chat(self, messages, config=None):
        """Chamada síncrona para o modelo Groq."""
        if not self.api_key:
            raise ValueError("Chave da API Groq não configurada.")

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
                    "Groq: resposta sem conteúdo — possível estouro de "
                    "max_tokens durante o raciocínio interno do modelo."
                )

            return content

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Groq excedeu o limite de taxa. Tente novamente.")
            raise Exception(f"Groq erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Groq: tempo limite excedido.")
        except Exception as e:
            raise Exception(f"Groq falhou: {e}")

    #--------------------------------------------
    def stream(self, messages, config=None):
        """Streaming via Groq — Server-Sent Events."""
        if not self.api_key:
            raise ValueError("Chave da API Groq não configurada.")

        payload = self._build_payload(messages, config, stream=True)

        try:
            with requests.post(
                self.BASE_URL,
                headers=self._headers,
                json=payload,
                stream=True,
                timeout=30,
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

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Groq excedeu o limite de taxa durante streaming.")
            raise Exception(f"Groq erro HTTP durante streaming: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Groq: tempo limite excedido durante streaming.")
        except Exception as e:
            raise Exception(f"Groq falhou no streaming: {e}")