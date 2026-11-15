# Report: partner ticket -> triage card

**Production choice: `gemini-2.5-flash-lite` + prompt `v3` + temperature 0.** It ties with `gpt-4o-mini` on
accuracy (92.5% vs 91.9–92.5% over 20 labelled tickets), and beats it on validity (100% on the first try),
latency (p50 0.93 s vs 2.4 s) and cost ($0.18 vs $0.24–0.27 per 1000 tickets). The local `llama3.2:3b` is not
usable for this task (54–63% accuracy, up to 20% failed answers).

## Setup

- **Task.** One partner support ticket in, one `TicketTriage` JSON out: 9 fields, 4 enums
  (`surface`, `category`, `priority`, `language`), a nested object (`entity_ids` with 3 ID lists),
  a list of nested objects (`api_errors`) and a bool `needs_engineering`. See `extractor/schema.py`.
- **Data.** 30 synthetic tickets in the style of real Guesty API partner traffic (no personal data).
  They are 32–786 characters long, with typos, forwarded threads, logs, signatures, and EN / UK / RU / ES, often mixed.
  - **Golden set:** `t01`–`t10`, hand-labelled before any model run, and used while writing prompts v2 and v3.
  - **Holdout:** `t11`–`t20`, hand-labelled after v2 and before v3, and never used to tune prompts.
    It was added because tuning on only 10 tickets can overfit.
  - The labelling rules are in `data/LABELING.md`.
- **Models.**
  - `gpt-4o-mini`: the main provider model, via OpenRouter.
  - `gemini-2.5-flash-lite`: the cheap provider model (the optional third model), via OpenRouter.
  - `llama3.2:3b`: local, via Ollama.
  - All three use the same `LLMProvider` interface and a strict JSON Schema (structured output).
- **Prompts.** `v1` is the baseline (4 sentences), `v2` adds field-by-field rules, and `v3` turns priority into a
  decision procedure and tightens the `surface` and `api_errors` rules. See `prompts/CHANGELOG.md`.
- **Sampling** (in `config.toml`): `deterministic` is T=0.0, top_p=1.0; `creative` is T=0.8, top_p=0.9.
- **Metrics.**
  - *Field accuracy* is the share of exact matches on the 8 scored fields, averaged. `summary` is free text and
    not scored. ID lists and API errors are compared as sets. Endpoints are compared without host and query string.
    A failed answer scores 0 on every field.
  - *Valid* is the share of answers that pass Pydantic validation: on the first try, and after the one repair turn.
  - *Invented IDs* counts returned IDs that do not appear verbatim in the ticket (all 30 tickets).
  - *Latency* is the wall time per ticket, including retries and the repair turn.
  - *Cost* uses OpenRouter list prices × the actual token usage. The local model counts as $0 (hardware and
    electricity are not included).

## Results: model × prompt × sampling

All runs cover 30 tickets. "All 20" is field accuracy over golden + holdout together. Full per-field tables
are in [`results/metrics.md`](results/metrics.md).

| Model | Prompt | Sampling | Golden (10) | Holdout (10) | All 20 | Valid 1st try | Valid final | Failed | Invented IDs | p50, s | p95, s | $ / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-2.5-flash-lite | v1 | deterministic | 91.2% | 85.0% | 88.1% | 97% | 100% | 0 | 0 | 0.95 | 1.42 | $0.096 |
| gemini-2.5-flash-lite | v1 | creative | 90.0% | 86.2% | 88.1% | 97% | 100% | 0 | 0 | 0.89 | 1.22 | $0.096 |
| gemini-2.5-flash-lite | v2 | deterministic | 91.2% | 86.2% | 88.8% | 100% | 100% | 0 | 0 | 0.84 | 1.07 | $0.163 |
| gemini-2.5-flash-lite | v2 | creative | 91.2% | 86.2% | 88.8% | 100% | 100% | 0 | 0 | 0.94 | 1.08 | $0.163 |
| **gemini-2.5-flash-lite** | **v3** | **deterministic** | **97.5%** | **87.5%** | **92.5%** | **100%** | **100%** | **0** | **0** | **0.93** | **1.18** | **$0.180** |
| gemini-2.5-flash-lite | v3 | creative | 98.8% | 87.5% | 93.1% | 100% | 100% | 0 | 0 | 0.94 | 1.48 | $0.179 |
| gpt-4o-mini | v1 | deterministic | 88.8% | 90.0% | 89.4% | 100% | 100% | 0 | 0 | 1.68 | 3.16 | $0.134 |
| gpt-4o-mini | v1 | creative | 92.5% | 86.2% | 89.4% | 97% | 100% | 0 | 0 | 1.76 | 2.47 | $0.140 |
| gpt-4o-mini | v2 | deterministic | 93.8% | 90.0% | 91.9% | 97% | 100% | 0 | 0 | 2.44 | 4.43 | $0.244 |
| gpt-4o-mini | v2 | creative | 92.5% | 92.5% | 92.5% | 100% | 100% | 0 | 0 | 2.20 | 2.79 | $0.233 |
| gpt-4o-mini | v3 | deterministic | 90.0% | 90.0% | 90.0% | 97% | 100% | 0 | 0 | 2.41 | 3.21 | $0.270 |
| gpt-4o-mini | v3 | creative | 91.2% | 91.2% | 91.2% | 97% | 100% | 0 | 0 | 2.08 | 3.09 | $0.270 |
| llama3.2:3b (local) | v1 | deterministic | 68.8% | 57.5% | 63.1% | 83% | 100% | 0 | 0 | 5.83 | 13.93 | $0 |
| llama3.2:3b (local) | v1 | creative | 60.0% | 56.2% | 58.1% | 90% | 100% | 0 | 2 | 7.55 | 15.43 | $0 |
| llama3.2:3b (local) | v2 | deterministic | 62.5% | 60.0% | 61.3% | 70% | 87% | 4 | 4 | 9.21 | 24.33 | $0 |
| llama3.2:3b (local) | v2 | creative | 55.0% | 61.3% | 58.1% | 73% | 87% | 4 | 5 | 10.08 | 22.27 | $0 |
| llama3.2:3b (local) | v3 | deterministic | 46.2% | 62.5% | 54.4% | 70% | 80% | 6 | 0 | 9.54 | 24.94 | $0 |
| llama3.2:3b (local) | v3 | creative | 53.8% | 61.3% | 57.5% | 77% | 90% | 3 | 1 | 9.86 | 25.65 | $0 |

The whole matrix (18 runs, 540 extractions, plus repair turns) cost **$0.065** on OpenRouter.

### What the numbers say

- **Prompt versions.** v2 fixed `category` (gpt-4o-mini: 85% to 95% over all 20 tickets) and `needs_engineering`
  (70% to 90–95%), but made `priority` worse for gemini (65% to 50%). v3 fixed priority for gemini (to 75%) but not for
  gpt-4o-mini, which got slightly worse (70% to 65%). That's why the best prompt differs by model: v3 for gemini, v2 for gpt-4o-mini.
- **Golden vs holdout.** Gemini v3 gains 6 points on the golden set but only 1 point on the holdout: most of
  its v3 gain is fitting to the 10 tickets the rules were written against. gpt-4o-mini moves the same way on both sets.
  **With 10 tickets × 8 fields, one wrong field is 1.25 points, so differences under ~3 points are noise.**
- **Sampling.** For the hosted models, T=0.8 vs T=0 changes accuracy by 0–1.2 points over 20 tickets, within noise.
  For the 3B model, T=0.8 is worse on v1 (−5 points). T=0 is chosen for reproducibility and so the cache stays meaningful:
  two uncached reruns of the production config on the golden set both gave 97.5%. T=0 still isn't fully deterministic
  through an API: an uncached rerun of gpt-4o-mini v3 flipped one holdout field (90.0% to 88.8%).
- **Validity.** Strict structured output gives the hosted models almost 100% valid JSON on the first try. The ~3%
that fail are answers that break the *local* checks: the string `"null"` as a name (gpt-4o-mini t08, v1), a `200 OK`
listed as an API error (gpt-4o-mini t08, v2/v3), or a summary over 200 characters (gemini t10, v1). All of those were
fixed in the one repair turn. Ollama's schema-constrained decoding always yields well-formed JSON, but the
  3B model fills it with meaningless values that the repair turn doesn't fix (error 4 below).
- **Prompt cost.** The longer v2/v3 prompts cost 1.7–2× more per ticket and roughly double local latency (prefill
  on a 3B model). For hosted models that's still under $0.30 per 1000 tickets.

## Error analysis

**1. Priority follows tone, not the rubric (gpt-4o-mini, t06).** The ticket says "the client is nervous because
they want to launch before the season": a marketplace integration waiting for approval, not live yet.
The gold label is `medium` (setup blocked, no production impact). gpt-4o-mini returns `high` with v1, v2 *and* v3,
even though v3 explicitly says "impatient clients and launch deadlines do not raise the priority". The same happens on
t02 (polling degraded, "nobody complained yet") and t09 (a new app missing a scope). Gemini follows the v3 procedure on
these. Why: the emotional signal in the ticket outweighs a written rule for gpt-4o-mini. This is the main reason
gpt-4o-mini's priority accuracy is stuck at 65–70%.

**2. A negative rule leaks onto the nearest positive case (gpt-4o-mini, v2 to v3, t08).** v3 added "a risk of
overbooking is high, not critical" to stop models from escalating t03 (an overbooking *risk*). On t08 the ticket
says in Ukrainian "Вже 2 овербукінги за вихідні!!!" ("2 overbookings already this weekend"), which is harm
that already happened, so it's `critical`. gpt-4o-mini answered `critical` with v2 and `high` with v3, and at the same time
flipped `needs_engineering` from `true` to `false`. The cached first answer confirms the repair turn (which only removed a
`200 OK` "error") didn't cause this; the v3 prompt did. Why: the model matched the word "overbooking" to the new rule
without checking tense. Lesson: every rule added to fix one ticket has to be re-checked on all the others, which is
exactly what `make regress` is for.

**3. Ukrainian read as Russian (gpt-4o-mini t18; llama t08).** t18 is plain Ukrainian ("Резервації які ми
створюємо через POST /v1/reservations приходять з валютою USD замість EUR…"). gpt-4o-mini returns `language: "ru"` with
every prompt version, and llama does the same on t08. Why: both languages are Cyrillic, the ticket is short and
technical, and both models seem to treat "Cyrillic" as Russian by default, even though the very first word
("Резервації") contains the Ukrainian-only letter "ї". If `language` routes tickets to a support queue, this sends
Ukrainian partners to Russian-speaking agents. A cheap deterministic check after the model (the letters і/ї/є/ґ mean
`uk`) would catch it, which is better than adding yet another rule to the prompt.

**4. Constrained decoding guarantees shape, not meaning (llama3.2:3b).** The local model always returns
well-formed JSON, but fills fields that should be empty:
- An `api_errors` item with `http_status: 200` on a how-to question with no error at all (t05), or status `0` on an SSL error (t26).
- ID lists containing `"null"`, `""`, `"none stated"`, or the prompt's own delimiters `"<<<"` / `">>>"` (t05).
- `partner_name: "Airbnb"` for a ticket that only mentions Airbnb as a channel (t08).

The local validators added along the way (status 400–599, no placeholder strings) turn these into repair turns,
but the 3B model usually repeats the same answer, so the run ends as `failed` (up to 6/30 with v3).
Longer prompts make it worse: v3 is the *least* accurate prompt for llama on the golden set (46–54%).
Why: a 3B model can't hold ~650 tokens of rules and still read the ticket; the schema forces it to produce *something* for every field.

**5. Part of the "error" is in the labels, not the model (holdout t18, t19, t14).** On t19 (429 on `/oauth2/token`,
which then causes a 401 on `/v1/reservations`) both hosted models say `authentication`, while the label says
`rate_limit`. On t18 (wrong currency stored on reservations created through a successful POST) both say `data_sync`,
while the label says `bug`, and under my own definition ("data different while the calls succeed") `data_sync` is defensible.
On t14 ("are we supposed to sign the raw body or the parsed JSON?" for webhook signatures) gemini says `authentication`
with every prompt, while the label and gpt-4o-mini say `how_to_question`. When two different models agree against the label
(t18, t19), the taxonomy has overlapping categories. Fix: a tie-break rule in `LABELING.md`
(root cause over symptom), or allow a secondary category. This also caps the measurable holdout `category` accuracy for gemini at 60–70%.

Smaller, fixed along the way: gemini dropped the `/api` prefix from Booking Engine endpoints with v1 (fixed by v2's
"keep prefixes"), and gpt-4o-mini returned the *string* `"null"` as `partner_name` (now rejected by a validator and fixed
in the repair turn).

## Decision for production

I'd ship **`gemini-2.5-flash-lite` with prompt `v3` at temperature 0**. Over 20 hand-labelled tickets it's as
accurate as the best gpt-4o-mini setup (92.5% vs 92.5% / 91.9%, a difference well inside the noise of a set this
small). It's the only setup with 100% schema-valid answers on the first try and zero invented IDs, it's 2.6× faster
(p50 0.93 s, p95 1.18 s) and 25–33% cheaper ($0.18 vs $0.24–0.27 per 1000 tickets), and it passes `make regress` (97.5% on the golden set, threshold 85%).

I'd change the decision if:
- **gpt-4o-mini + v2 instead**, if a larger holdout (≥50 tickets) confirms the `category` gap seen here (95% vs 80%
  over 20 tickets), because category picks the routing queue and is worth more than a 1-second latency gain.
- **A local model**, if tickets must not leave our infrastructure. But not a 3B one: I'd first measure a 7–8B model
  (for example `qwen2.5:7b` or `llama3.1:8b`) with the short v1 prompt, since longer prompts hurt small models.
- **A batch API at half the price**, if volume grows to many thousands of tickets a day and latency stops mattering.
  Cost is negligible at our scale.

## Limitations

- 20 labelled tickets is enough to compare setups roughly, not to claim the second decimal place.
  Gemini v3 is partly tuned to the golden set, as the golden vs holdout gap shows.
- The tickets are synthetic and were written by the same person who labelled them, so real traffic will be messier.
- Latency is measured from one laptop in Europe through OpenRouter, with 4 parallel requests for the hosted models
  and 1 at a time for Ollama.
- The creative-sampling runs are a single sample each; their variance was not measured.
