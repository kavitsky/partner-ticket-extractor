# Labeling guide (golden set)

`data/tickets/` holds 30 synthetic partner tickets written in the style of real Guesty API partner
support traffic. Partner names, IDs and hosts are fictional; there is no personal data.
They are deliberately messy: 1-line to 25-line texts, typos, forwarded threads, pasted logs,
email signatures and disclaimers, and English / Ukrainian / Russian / Spanish, often mixed.

`data/golden.json` labels 10 of them (`t01`–`t10`) by hand. The same rules are written into
prompt `v2`, but the labels were written before any model runs.

| Field | Rule |
|---|---|
| `partner_name` | Company that wrote the ticket, as written. `null` if not stated. Not Guesty, not a channel (Airbnb). |
| `surface` | `open_api`: open-api.guesty.com, client credentials, `/v1/...` used by a customer's own integration. `partners_api`: marketplace partner integration. `booking_engine_api`: booking.guesty.com / BE API. `webhooks`: the problem is about webhook delivery/payloads. `unknown`: cannot tell. |
| `category` | `authentication` 401/403, tokens, secrets, scopes. `rate_limit` 429 / throttling. `integration_setup` onboarding, credentials, approval, sandbox. `data_sync` data missing, late, duplicated or different between Guesty and the partner while calls succeed. `bug` 5xx or clearly wrong API behaviour. `how_to_question` docs / "how do I". `feature_request` asks for something that does not exist. `other` anything else. |
| `priority` | `critical`: production down or bookings/money being lost now. `high`: a production workflow is blocked or at clear risk. `medium`: degraded, or setup blocked with no production impact. `low`: questions, feature requests, "not urgent". |
| `language` | Language of the prose. `mixed` if two languages each carry meaning; quoted English error messages and endpoint names do not make a text mixed. |
| `entity_ids` | Copy IDs exactly as written. Quote IDs, conversation IDs, guest IDs and hosts are not account/listing/reservation IDs. |
| `api_errors` | One item per failing call that has an HTTP error status (4xx/5xx) in the text. Successful calls (200) are not errors. `endpoint` is the path only, without host and query string. |
| `needs_engineering` | `true` if the cause is likely on Guesty's side and needs backend investigation (5xx, lost/late/wrong data). `false` if Solutions/Support can resolve it (config, auth, limits, docs, product requests). |

`summary` is free text and is not scored.
