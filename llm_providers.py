"""
LLM provider abstraction for coffee extraction.

Supports three backends:
  - anthropic: Claude Sonnet via Anthropic API (paid)
  - gemini:    Google Gemini via free-tier API
  - ollama:    Local LLMs via Ollama HTTP API
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


class LLMError(Exception):
    """Raised when an LLM API call fails."""


class LLMProvider:
    """Base class for LLM providers."""

    name: str = "base"

    def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        """Send prompt to LLM and return raw text response."""
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        import anthropic

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        from google import genai

        api_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise LLMError(
                "GOOGLE_GEMINI_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=api_key)
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._last_call = 0.0

    def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        # Rate limit: max 15 RPM on free tier = 1 request per 4 seconds
        elapsed = time.time() - self._last_call
        if elapsed < 4.0:
            time.sleep(4.0 - elapsed)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"max_output_tokens": max_tokens},
            )
            self._last_call = time.time()
            return response.text.strip()
        except Exception as e:
            raise LLMError(f"Gemini API error: {e}")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self):
        self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        # Verify Ollama is reachable
        try:
            requests.get(f"{self.url}/api/tags", timeout=5)
        except requests.ConnectionError:
            raise LLMError(
                f"Cannot connect to Ollama at {self.url}.\n"
                "Is Ollama running? Start it with: ollama serve"
            )

    def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        try:
            resp = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=600,
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise LLMError(f"Ollama error: {data['error']}")
            return data.get("response", "").strip()
        except requests.ConnectionError:
            raise LLMError(f"Lost connection to Ollama at {self.url}")
        except requests.Timeout:
            raise LLMError(
                f"Ollama request timed out (model: {self.model}). "
                "Try a smaller model or increase timeout."
            )
        except requests.RequestException as e:
            raise LLMError(f"Ollama HTTP error: {e}")


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str) -> LLMProvider:
    """Create a provider by name. Reads config from env vars."""
    cls = PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(PROVIDERS.keys())
        raise LLMError(f"Unknown provider '{name}'. Available: {available}")
    return cls()
