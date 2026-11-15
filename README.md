# Partner ticket extractor

Turns messy Guesty API partner support tickets (typos, forwarded threads, logs, EN/UK/RU/ES) into a
validated JSON triage card, and measures which model + prompt + sampling config should go to production.
First slice of the course project: the same tickets and model layer will feed the RAG and agent stages.

Results and the production decision: [REPORT.md](REPORT.md).

## Run

Requirements: Python 3.11+, an [OpenRouter](https://openrouter.ai/keys) key, and [Ollama](https://ollama.com) for the local model.

```bash
cp .env.example .env          # paste OPENROUTER_API_KEY
ollama pull llama3.2:3b       # ~2 GB, runs on a normal laptop
make run                      # or: python main.py  (after pip install -r requirements.txt)
```

`make run` creates `.venv`, installs dependencies, runs the matrix from `config.toml`
(3 models x 3 prompt versions x 2 sampling configs x 30 tickets), writes `results/runs/*.jsonl`
and regenerates `results/metrics.md`. If the key or Ollama is missing, that model is skipped with a message.

| Command | What it does |
|---|---|
| `make run` | full matrix, then metrics |
| `make report` | rebuild `results/metrics.md` from the saved runs, no API calls |
| `make regress` | production config on the golden set; fails if field accuracy < 85%, any answer failed, or any invented ID |
| `python main.py --models gpt-4o-mini --prompts v3 --sampling deterministic` | a single cell of the matrix |
| `python main.py --no-cache` | ignore the response cache |

A full run from scratch costs about $0.07 on OpenRouter; the local model takes ~25 min on an M-series laptop.
Responses are cached in `.cache/` (keyed by model, messages, schema and sampling), so a second run is free and instant.

## Layout

```
main.py                  CLI: run / report / regress
config.toml              models, prices, sampling configs, prompt versions, production config
extractor/schema.py      Pydantic schema (TicketTriage) + strict JSON Schema for providers
extractor/providers.py   LLMProvider interface: OpenRouterProvider, OllamaProvider (timeout + retry/backoff)
extractor/pipeline.py    prompt loading, validation, one repair attempt, run metadata, cache
extractor/metrics.py     field accuracy, validity, latency p50/p95, cost, invented IDs
prompts/v1..v3/          versioned prompts + CHANGELOG.md
data/tickets/            30 synthetic tickets (no personal data)
data/golden.json         10 hand-labelled tickets used while writing prompts
data/holdout.json        10 more hand-labelled tickets never used for prompt tuning
data/LABELING.md         labelling rules
results/runs/            one JSONL per model x prompt x sampling, one record per ticket
results/metrics.md       generated comparison tables
REPORT.md                comparison, error analysis, production choice
```

## How a ticket is processed

1. The prompt version's `system.txt` + `user.txt` and the ticket go to the model with a strict JSON Schema
   (`response_format` on OpenRouter, `format` on Ollama). Transient errors (timeouts, 429, 5xx) are retried with backoff.
2. The answer is validated with Pydantic. Local checks are stricter than the provider schema:
   summary length, HTTP error status 400-599, no placeholder strings like `"null"` in names or ID lists.
3. If validation fails, the model gets one repair turn with the validation error. Still invalid: `status = "failed"`.
4. Each record logs model, provider, prompt version + hash, sampling params, status, attempts, latency, tokens and cost.
