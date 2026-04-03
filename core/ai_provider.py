import os
import requests
import random
import time

from core.engine import ESTILOS_IA

# ============================================
# Configurações por IA
# ============================================
CONFIGS = {
    #"Anthropic": {"temperature": 0.45, "max_tokens": 512,  "top_p": 0.9,  "frequency_penalty": 0.45, "presence_penalty": 0.25},
    "Gemini":    {"temperature": 0.35, "max_tokens": 2048, "top_p": 0.40, "frequency_penalty": 0.10, "presence_penalty": 0.05},
    "Groq":      {"temperature": 0.55, "max_tokens": 512,  "top_p": 0.85, "frequency_penalty": 0.80, "presence_penalty": 1.50},
    "Cerebras":  {"temperature": 0.35, "max_tokens": 256,  "top_p": 0.85, "frequency_penalty": 1.50, "presence_penalty": 1.00},
    "SambaNova": {"temperature": 0.75, "max_tokens": 384,  "top_p": 0.90, "frequency_penalty": 1.20, "presence_penalty": 1.00},
}


class FreeAIProvider:
    def __init__(self):
        self.keys = {
            #"anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "gemini":    os.getenv("GEMINI_API_KEY"),
            "groq":      os.getenv("GROQ_API_KEY"),
            "cerebras":  os.getenv("CEREBRAS_API_KEY"),
            "sambanova": os.getenv("SAMBANOVA_API_KEY"),
        }

    def _ajustar_system(self, messages: list, ia_nome: str) -> list:
        """Injeta o estilo da IA no system prompt, preservando o restante."""
        estilo = ESTILOS_IA.get(ia_nome, "")
        resultado = []
        for m in messages:
            if m["role"] == "system" and estilo:
                resultado.append({
                    "role": "system",
                    "content": m["content"] + f"\n{estilo}"
                })
            else:
                resultado.append(m)
        return resultado

    def chat(self, messages, temperature=0.45, max_tokens=512, top_p=0.9,
             frequency_penalty=0.45, presence_penalty=0.25):

        providers = [
            #("anthropic", "Anthropic", "Claude Haiku · Anthropic", self._anthropic_chat),
            ("gemini",    "Gemini",    "Gemini 2.5 Flash · Google", self._gemini_chat),
            ("groq",      "Groq",      "Llama 3.3 70B · Groq",      self._groq_chat),
            ("cerebras",  "Cerebras",  "Llama 3.1 8B · Cerebras",   self._cerebras_chat),
            ("sambanova", "SambaNova", "Llama 3.1 8B · SambaNova",  self._sambanova_chat),
        ]

        random.shuffle(providers)

        for key, nome, label, method in providers:
            if not self.keys.get(key):
                continue
            try:
                messages_ajustadas = self._ajustar_system(messages, nome)
                cfg = CONFIGS.get(nome, {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                    "frequency_penalty": frequency_penalty,
                    "presence_penalty": presence_penalty,
                })
                resposta = method(
                    messages_ajustadas,
                    cfg["temperature"],
                    cfg["max_tokens"],
                    cfg["top_p"],
                    cfg["frequency_penalty"],
                    cfg["presence_penalty"],
                )
                return resposta, label

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print(f"[AI] {nome} está exausto (429). Meditando por 2 segundos...")
                    time.sleep(2)
                else:
                    print(f"[AI] {nome} falhou com erro HTTP: {e}")
                continue
            except Exception as e:
                print(f"[AI] {nome} falhou: {e}. Tentando próximo...")
                continue

        return "Companheiro, a palavra encontrou um obstáculo. Tente novamente.", "Fallback"

    def _gemini_chat(self, messages, temperature, max_tokens, top_p, freq_pen, pres_pen):
        model_name = "gemini-2.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={self.keys['gemini']}"
        )
        contents = []
        for m in messages:
            if m["role"] == "system":
                # Gemini não aceita role "system" — injeta como primeira mensagem user
                contents.insert(0, {"role": "user", "parts": [{"text": m["content"]}]})
                contents.insert(1, {"role": "model", "parts": [{"text": "Entendido."}]})
            else:
                role = "model" if m["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p,
            },
        }
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    def _groq_chat(self, messages, temperature, max_tokens, top_p, freq_pen, pres_pen):
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.keys['groq']}"},
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _cerebras_chat(self, messages, temperature, max_tokens, top_p, freq_pen, pres_pen):
        payload = {
            "model": "llama3.1-8b",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.keys['cerebras']}"},
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _sambanova_chat(self, messages, temperature, max_tokens, top_p, freq_pen, pres_pen):
        payload = {
            "model": "Meta-Llama-3.1-8B-Instruct",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = requests.post(
            "https://api.sambanova.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.keys['sambanova']}"},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _anthropic_chat(self, messages, temperature, max_tokens, top_p, freq_pen, pres_pen):
        # Comentado em produção — usado apenas para calibração local
        system = ""
        msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)

        payload = {
            "model": "claude-haiku-4-5-20251001",
            "messages": msgs,
            "system": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.keys["anthropic"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]
