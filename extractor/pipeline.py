"""Extraction with schema validation, one repair attempt, run metadata and a response cache."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .providers import Completion, LLMProvider, Sampling
from .schema import TicketTriage, provider_json_schema

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
CACHE_DIR = ROOT / ".cache"

REPAIR_MESSAGE = (
    "Your previous answer failed schema validation:\n{error}\n"
    "Return the corrected JSON object only, matching the schema exactly."
)


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user_template: str

    @property
    def sha(self) -> str:
        return hashlib.sha256((self.system + self.user_template).encode()).hexdigest()[:12]

    def messages(self, ticket: str) -> list[dict]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user_template.replace("{ticket}", ticket.strip())},
        ]


def load_prompt(version: str) -> Prompt:
    d = PROMPTS_DIR / version
    return Prompt(version, (d / "system.txt").read_text(encoding="utf-8"), (d / "user.txt").read_text(encoding="utf-8"))


class ResponseCache:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        CACHE_DIR.mkdir(exist_ok=True)

    @staticmethod
    def _key(provider: LLMProvider, messages, schema, sampling: Sampling) -> str:
        blob = json.dumps(
            [provider.name, provider.model_id, messages, schema, sampling.temperature, sampling.top_p],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def complete(self, provider: LLMProvider, messages, schema, sampling) -> tuple[Completion, bool]:
        path = CACHE_DIR / f"{self._key(provider, messages, schema, sampling)}.json"
        if self.enabled and path.exists():
            return Completion(**json.loads(path.read_text())), True
        comp = provider.complete(messages, schema, sampling)
        path.write_text(json.dumps(asdict(comp), ensure_ascii=False))
        return comp, False


def _validate(content: str) -> tuple[TicketTriage | None, str | None]:
    try:
        return TicketTriage.model_validate_json(content), None
    except ValidationError as e:
        return None, str(e)


def extract(
    doc_id: str,
    text: str,
    provider: LLMProvider,
    model_key: str,
    prices: tuple[float, float],
    prompt: Prompt,
    sampling: Sampling,
    cache: ResponseCache,
) -> dict:
    schema = provider_json_schema()
    messages = prompt.messages(text)
    completions: list[Completion] = []
    cached_flags: list[bool] = []
    status, parsed, error, raw, first_error = "failed", None, None, "", None

    try:
        comp, cached = cache.complete(provider, messages, schema, sampling)
        completions.append(comp)
        cached_flags.append(cached)
        raw = comp.content
        parsed, error = _validate(raw)
        if parsed:
            status = "ok"
        else:
            first_error = error
            repair = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": REPAIR_MESSAGE.format(error=error)},
            ]
            comp, cached = cache.complete(provider, repair, schema, sampling)
            completions.append(comp)
            cached_flags.append(cached)
            raw = comp.content
            parsed, error = _validate(raw)
            status = "repaired" if parsed else "failed"
    except Exception as e:  # provider gave up after its retries
        error = f"{type(e).__name__}: {e}"

    tin = sum(c.input_tokens for c in completions)
    tout = sum(c.output_tokens for c in completions)
    return {
        "doc_id": doc_id,
        "model": model_key,
        "model_id": provider.model_id,
        "provider": provider.name,
        "prompt_version": prompt.version,
        "prompt_sha": prompt.sha,
        "sampling": {"name": sampling.name, "temperature": sampling.temperature, "top_p": sampling.top_p},
        "status": status,
        "attempts": len(completions),
        "output": parsed.model_dump(mode="json") if parsed else None,
        "raw": raw if not parsed else None,
        "error": error if not parsed else None,
        "repair_reason": first_error,
        "latency_s": round(sum(c.latency_s for c in completions), 3),
        "input_tokens": tin,
        "output_tokens": tout,
        "cost_usd": (tin * prices[0] + tout * prices[1]) / 1_000_000,
        "cached": all(cached_flags) if cached_flags else False,
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
