"""Scoring against the golden set plus validity, latency and cost metrics."""

from __future__ import annotations

import math
import re
from urllib.parse import urlparse

SCORED_FIELDS = [
    "partner_name",
    "surface",
    "category",
    "priority",
    "language",
    "needs_engineering",
    "entity_ids",
    "api_errors",
]


def _norm_name(v: str | None) -> str | None:
    return re.sub(r"[^a-z0-9]", "", v.lower()) or None if v else None


def norm_endpoint(v: str | None) -> str | None:
    if not v:
        return None
    path = urlparse(v).path if "://" in v else v.split("?")[0]
    path = re.sub(r"^[a-z0-9.-]+\.(com|io)(?=/)", "", path.strip().lower())
    return path.rstrip("/") or "/"


def _ids(e: dict) -> tuple:
    return tuple(frozenset(e[k]) for k in ("account_ids", "listing_ids", "reservation_ids"))


def _errors(errs: list[dict]) -> frozenset:
    return frozenset((norm_endpoint(e["endpoint"]), e["http_status"]) for e in errs)


def field_correct(field: str, pred: dict, gold: dict) -> bool:
    if field == "partner_name":
        return _norm_name(pred["partner_name"]) == _norm_name(gold["partner_name"])
    if field == "entity_ids":
        return _ids(pred["entity_ids"]) == _ids(gold["entity_ids"])
    if field == "api_errors":
        return _errors(pred["api_errors"]) == _errors(gold["api_errors"])
    return pred[field] == gold[field]


def invented_ids(pred: dict, text: str) -> list[str]:
    """IDs the model returned that do not appear verbatim in the ticket."""
    all_ids = [i for k in ("account_ids", "listing_ids", "reservation_ids") for i in pred["entity_ids"][k]]
    return [i for i in all_ids if i not in text]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def accuracy_by_field(records: list[dict], labels: dict) -> tuple[dict[str, float], int]:
    per_field = {f: 0 for f in SCORED_FIELDS}
    labeled = [r for r in records if r["doc_id"] in labels]
    for r in labeled:
        if r["output"] is None:
            continue  # a failed answer scores 0 on every field
        for f in SCORED_FIELDS:
            per_field[f] += field_correct(f, r["output"], labels[r["doc_id"]])
    n = len(labeled)
    return {f: per_field[f] / (n or 1) for f in SCORED_FIELDS}, n


def summarize(records: list[dict], golden: dict, texts: dict[str, str], holdout: dict | None = None) -> dict:
    n = len(records)
    valid = [r for r in records if r["output"] is not None]
    field_acc, n_golden = accuracy_by_field(records, golden)
    holdout_acc, n_holdout = accuracy_by_field(records, holdout or {})
    invented = sum(len(invented_ids(r["output"], texts[r["doc_id"]])) for r in valid)
    latencies = [r["latency_s"] for r in records]
    first = records[0]
    return {
        "model": first["model"],
        "prompt_version": first["prompt_version"],
        "sampling": first["sampling"]["name"],
        "temperature": first["sampling"]["temperature"],
        "top_p": first["sampling"]["top_p"],
        "n_docs": n,
        "n_golden": n_golden,
        "n_holdout": n_holdout,
        "valid_first_try_pct": 100 * sum(r["status"] == "ok" for r in records) / n,
        "valid_final_pct": 100 * len(valid) / n,
        "repaired": sum(r["status"] == "repaired" for r in records),
        "failed": n - len(valid),
        "field_accuracy": sum(field_acc.values()) / len(field_acc),
        "field_accuracy_by_field": field_acc,
        "holdout_accuracy": sum(holdout_acc.values()) / len(holdout_acc) if n_holdout else None,
        "holdout_accuracy_by_field": holdout_acc if n_holdout else None,
        "invented_ids": invented,
        "latency_p50_s": percentile(latencies, 0.5),
        "latency_p95_s": percentile(latencies, 0.95),
        "cost_per_1000_docs_usd": 1000 * sum(r["cost_usd"] for r in records) / n,
        "avg_input_tokens": sum(r["input_tokens"] for r in records) / n,
        "avg_output_tokens": sum(r["output_tokens"] for r in records) / n,
    }


def to_markdown(rows: list[dict]) -> str:
    head = (
        "| Model | Prompt | Sampling (T / top_p) | Field acc. golden | Field acc. holdout | Valid 1st try | Valid final | "
        "Repaired / failed | Invented IDs | p50, s | p95, s | $ / 1000 docs |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = "".join(
        f"| {r['model']} | {r['prompt_version']} | {r['sampling']} ({r['temperature']} / {r['top_p']}) | "
        f"{r['field_accuracy']:.1%} | "
        + (f"{r['holdout_accuracy']:.1%}" if r.get("holdout_accuracy") is not None else "-")
        + f" | {r['valid_first_try_pct']:.0f}% | {r['valid_final_pct']:.0f}% | "
        f"{r['repaired']} / {r['failed']} | {r['invented_ids']} | {r['latency_p50_s']:.2f} | "
        f"{r['latency_p95_s']:.2f} | ${r['cost_per_1000_docs_usd']:.3f} |\n"
        for r in rows
    )
    fields_head = "| Model | Prompt | Sampling | " + " | ".join(SCORED_FIELDS) + " |\n"
    fields_head += "|---|---|---|" + "---|" * len(SCORED_FIELDS) + "\n"
    def fields_body(key: str) -> str:
        return "".join(
            f"| {r['model']} | {r['prompt_version']} | {r['sampling']} | "
            + " | ".join(f"{r[key][f]:.0%}" for f in SCORED_FIELDS)
            + " |\n"
            for r in rows
            if r.get(key)
        )

    return (
        "## Summary\n\n" + head + body
        + "\n## Accuracy by field: golden set (t01-t10, used while writing prompts)\n\n"
        + fields_head + fields_body("field_accuracy_by_field")
        + "\n## Accuracy by field: holdout set (t11-t20, never used for prompt tuning)\n\n"
        + fields_head + fields_body("holdout_accuracy_by_field")
    )
