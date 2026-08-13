#
# /educador/core/ai_provider/adapters/gemini.py
#

import requests
import json
import time

from ..base import BaseProvider


class GeminiAdapter(BaseProvider):  # ← CORRIGIDO: parênteses e nome corretos
    """
    Adaptador para API Gemini.
    Modelo: gemini-2.5-flash
    """
    MODEL = "gemini-2.5-flash"
    LABEL = "Gemini 2.5 Flash · Google"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    DEFAULT_CONFIG = {
        "temperature": 0.35,
        "max_tokens": 2048,
        "top_p": 0.40,
        "frequency_penalty": 0.10,
        "presence_penalty": 0.05,
        "top_k": 5,
    }

    def __init__(self, api_key):
        super().__init__(api_key)
        self._headers = {
            "Content-Type": "application/json",
        }

    def _convert_messages(self, messages):
        """
        Converte mensagens do formato OpenAI para o formato Gemini.
        Gemini não aceita role "system" — injeta como primeira mensagem user,
        seguida de uma resposta model para fixar o contexto.
        """
        contents = []
        for m in messages:
            if m.get("role") == "system":
                contents.insert(0, {"role": "user", "parts": [{"text": m.get("content", "")}]})
                contents.insert(1, {"role": "model", "parts": [{"text": "Entendido."}]})
            else:
                role = "model" if m.get("role") == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        return contents

    def _build_payload(self, messages, config=None, stream=False):
        """Constrói o payload para a API Gemini."""
        contents = self._convert_messages(messages)
        merged = {**self.DEFAULT_CONFIG, **(config or {})}

        generation_config = {
            "temperature": merged.get("temperature"),
            "maxOutputTokens": merged.get("max_tokens"),
            "topP": merged.get("top_p"),
            "topK": merged.get("top_k"),
        }
        # Remove None
        generation_config = {k: v for k, v in generation_config.items() if v is not None}

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        return payload

    def _get_url(self, stream=False):
        """Retorna a URL correta para a API Gemini."""
        if stream:
            return f"{self.BASE_URL}/{self.MODEL}:streamGenerateContent?alt=sse&key={self.api_key}"
        return f"{self.BASE_URL}/{self.MODEL}:generateContent?key={self.api_key}"

    def chat(self, messages, config=None):
        """
        Chamada síncrona para o modelo Gemini.
        
        Args:
            messages (list): Lista de mensagens no formato OpenAI.
            config (dict, optional): Configurações específicas para esta chamada.
        
        Returns:
            str: Resposta do modelo.
        """
        if not self.api_key:
            raise ValueError("Chave da API Gemini não configurada.")

        payload = self._build_payload(messages, config, stream=False)
        url = self._get_url(stream=False)

        try:
            r = requests.post(
                url,
                headers=self._headers,
                json=payload,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Gemini excedeu o limite de taxa. Tente novamente.")
            raise Exception(f"Gemini erro HTTP: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Gemini: tempo limite excedido.")
        except Exception as e:
            raise Exception(f"Gemini falhou: {e}")

    def stream(self, messages, config=None):
        """
        Streaming via Gemini — chunked response (SSE).
        
        Args:
            messages (list): Lista de mensagens no formato OpenAI.
            config (dict, optional): Configurações específicas para esta chamada.
        
        Yields:
            tuple: (texto_parcial, label) token a token.
        """
        if not self.api_key:
            raise ValueError("Chave da API Gemini não configurada.")

        payload = self._build_payload(messages, config, stream=True)
        url = self._get_url(stream=True)

        try:
            with requests.post(
                url,
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

                        try:
                            chunk = json.loads(data)
                            texto = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if texto:
                                yield texto, self.LABEL
                        except json.JSONDecodeError:
                            continue
                        except Exception:
                            continue

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2)
                raise Exception("Gemini excedeu o limite de taxa durante streaming.")
            raise Exception(f"Gemini erro HTTP durante streaming: {e}")
        except requests.exceptions.Timeout:
            raise Exception("Gemini: tempo limite excedido durante streaming.")
        except Exception as e:
            raise Exception(f"Gemini falhou no streaming: {e}")