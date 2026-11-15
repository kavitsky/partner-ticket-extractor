# Prompt changelog

Each version is a folder with `system.txt` and `user.txt`. Every result record logs
`prompt_version` and `prompt_sha` (hash of both files), so a changed file can never hide behind an old version name.
Never edit a released version: copy it to a new folder and record the change here.

## v3 (2026-11-14)

Why: v2 fixed `category`, `needs_engineering`, `language` and endpoints, but `priority` got worse on the
golden set (gemini 80% -> 50%, gpt-4o-mini 70% -> 60%). The v2 rubric was a list of loose descriptions:
"production workflow blocked or clear risk" matched almost any ticket with an impatient customer, so models
picked `high` for onboarding tickets (t06, t09) and `critical` for an overbooking *risk* (t03).
`surface` still defaulted to `open_api` (t05, and t07 for gemini), and gpt-4o-mini listed a `200 OK` call as an API error (t08).

Changed:
- `priority` is now an ordered 4-step decision procedure ("stop at the first yes"), with explicit
  "risk is high, not critical" and "urgency words / deadlines do not raise priority".
- `surface`: `webhooks` wins over `open_api` for webhook events; `unknown` when no API/host/endpoint/webhook is named.
- `api_errors`: http_status must be 400-599, 200 calls are never listed.
- Paired with a schema change: `ApiError.http_status` is validated locally as 400-599, so a 200 now triggers the repair step.

Result: gemini golden 91% -> 98%, holdout 86% -> 88%; gpt-4o-mini golden 94% -> 90%, holdout 90% -> 90%
(see REPORT.md: gpt-4o-mini still ignores the priority procedure; part of the gemini gain is fitting to the 10 golden tickets).
Known regression: the "risk of overbooking is high" rule made gpt-4o-mini downgrade t08, where overbookings already happened, from critical to high.
v3 is the production prompt for gemini-2.5-flash-lite; for gpt-4o-mini, v2 remains better.

## v2 (2026-11-14)

Why: v1 (baseline) on the golden set, both hosted models, showed systematic errors:
- `needs_engineering` over-flagged: an auth error right after the partner rotated its secret (t01) and a feature request (t07) were sent to engineering.
- `category`: 5xx errors during a nightly sync labelled `data_sync` instead of `bug` (t10).
- `priority` inflated to `high` for onboarding / scope questions (t06, t09).
- `language`: a Ukrainian/English ticket labelled `uk` (t08).
- `api_errors`: gemini dropped the `/api` prefix from a Booking Engine path (t04).
- `surface`: marketplace integration not recognised as `partners_api` (t06), guessed `open_api` when no API was named (t05).
- `partner_name`: gpt-4o-mini returned the string `"null"` (t08) - fixed by a schema validator, not by the prompt.

Changed:
- Field-by-field rules with definitions for every enum value (same rules as data/LABELING.md).
- "Any 5xx makes it a bug", "200 is not an error", "keep /api or /v1 prefixes", "never the string null".
- Explicit `needs_engineering` true/false lists.
- Priority judged by stated business impact, not tone.
- Summary limited to 25 words.

Cost: system prompt grew from ~70 to ~650 tokens, so cost per document went up ~1.7x.

## v1 (2026-11-14)

Baseline: four sentences. Role, "fill the schema", "null / [] when missing, do not invent", "English one-sentence summary".
All field semantics come only from the JSON Schema enum names.
