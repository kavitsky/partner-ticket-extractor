"""Common interface over a hosted provider (OpenRouter) and a local model (Ollama)."""

from __future__ import annotations

import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import openai


@dataclass(frozen=True)
class Sampling:
    name: str
    temperature: float
    top_p: float


@dataclass
class Completion:
    content: str
    input_tokens: int
    output_tokens: int
    latency_s: float


class TransientError(Exception):
    """Timeouts, connection drops, 429 and 5xx: worth retrying."""


class ProviderUnavailable(Exception):
    pass


class LLMProvider(ABC):
    name: str

    def __init__(self, model_id: str, timeout_s: float, max_retries: int):
        self.model_id = model_id
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    def complete(self, messages: list[dict], schema: dict, sampling: Sampling) -> Completion:
        """Structured-output call with exponential backoff on transient errors."""
        start = time.perf_counter()
        for attempt in range(self.max_retries + 1):
            try:
                content, tin, tout = self._call(messages, schema, sampling)
                return Completion(content, tin, tout, time.perf_counter() - start)
            except TransientError:
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2**attempt, 20) + random.random())
        raise AssertionError("unreachable")

    @abstractmethod
    def _call(self, messages: list[dict], schema: dict, sampling: Sampling) -> tuple[str, int, int]:
        """Return (content, input_tokens, output_tokens)."""

    @abstractmethod
    def check_available(self) -> None:
        """Raise ProviderUnavailable with a human-readable reason."""


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, model_id: str, base_url: str, api_key_env: str, timeout_s: float, max_retries: int):
        super().__init__(model_id, timeout_s, max_retries)
        self.api_key_env = api_key_env
        self._client = openai.OpenAI(
            base_url=base_url,
            api_key=os.getenv(api_key_env) or "missing",
            timeout=timeout_s,
            max_retries=0,
        )

    def check_available(self) -> None:
        if not os.getenv(self.api_key_env):
            raise ProviderUnavailable(f"{self.api_key_env} is not set in .env")

    def _call(self, messages, schema, sampling):
        try:
            r = self._client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=sampling.temperature,
                top_p=sampling.top_p,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "ticket_triage", "strict": True, "schema": schema},
                },
                # Only route to upstream providers that honour response_format.
                extra_body={"provider": {"require_parameters": True}},
            )
        except (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError) as e:
            raise TransientError(str(e)) from e
        if not r.choices:
            raise TransientError("empty choices in response")
        usage = r.usage
        return (
            r.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, model_id: str, base_url: str, timeout_s: float, max_retries: int):
        super().__init__(model_id, timeout_s, max_retries)
        self.base_url = base_url.rstrip("/")

    def check_available(self) -> None:
        try:
            tags = httpx.get(f"{self.base_url}/api/tags", timeout=5).json()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"Ollama is not reachable at {self.base_url} ({e})") from e
        names = {m["name"] for m in tags.get("models", [])}
        if self.model_id not in names:
            raise ProviderUnavailable(f"run `ollama pull {self.model_id}` first")

    def _call(self, messages, schema, sampling):
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_id,
                    "messages": messages,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": sampling.temperature, "top_p": sampling.top_p},
                },
                timeout=self.timeout_s,
            )
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise TransientError(str(e)) from e
        if r.status_code >= 500 or r.status_code == 429:
            raise TransientError(f"HTTP {r.status_code}: {r.text[:200]}")
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0)


def build_provider(model_cfg: dict, providers_cfg: dict) -> LLMProvider:
    kind = model_cfg["provider"]
    p = providers_cfg[kind]
    if kind == "openrouter":
        return OpenRouterProvider(model_cfg["model_id"], p["base_url"], p["api_key_env"], p["timeout_s"], p["max_retries"])
    if kind == "ollama":
        return OllamaProvider(model_cfg["model_id"], p["base_url"], p["timeout_s"], p["max_retries"])
    raise ValueError(f"unknown provider {kind!r}")
