# Free AI setup for the weekly refresh

The website remains static. Only the refresh job calls AI; no visitor data or API
keys are sent through the browser. Extraction and factual verification share one
validated provider interface. Existing listings are retained when AI is unavailable.

## Use the intended Google account

1. Sign into [Google AI Studio](https://aistudio.google.com/) with the other account.
2. Create a project and API key. Confirm the project's Billing Tier says **Free
   Tier** and no billing account is attached. A different login alone does not
   determine API pricing: the key inherits its project's billing settings.
3. Check [current model pricing](https://ai.google.dev/gemini-api/docs/pricing)
   and the account's actual quota. The starting configuration uses
   `gemini-3.5-flash-lite,gemini-flash-lite-latest`; availability must still be checked for
   this account. The application cap of 20 calls is a conservative setting,
   not a claim about Google's allowance. Verification also consumes calls.
4. In this repository's **Settings → Secrets and variables → Actions**, add the
   repository secret `GEMINI_API_KEY`. Never paste the key into chat or commit it.
5. Add repository variables:

| Variable | Starting value |
| --- | --- |
| `AI_PROVIDERS` | `gemini` |
| `AI_GEMINI_MODELS` | `gemini-3.5-flash-lite,gemini-flash-lite-latest` |
| `AI_GEMINI_FREE_TIER_CONFIRMED` | `true`, after the billing check |
| `AI_GEMINI_DAILY_CALLS` | `20`, or a lower value matching the account |
| `AI_MAX_RUN_CALLS` | `20`, or a lower value |
| `AI_GEMINI_MIN_INTERVAL_MS` | `5000`, increase if required |

The workflow always sets `AI_DAILY_USD=0`. Free-tier confirmation is an operator
attestation; the code cannot independently verify billing. If project billing or
model pricing changes, disable confirmation until checked again. Google documents
these project-level rules in [billing](https://ai.google.dev/gemini-api/docs/billing).
Only public charity page text is supplied; Google's free-tier data-use terms apply.

If you previously set `AI_GEMINI_MODELS` to the 2.5 models, update that repository
variable: it overrides the workflow default. Google now restricts 2.5 model access
to projects that previously used them, as explained in its
[model availability notice](https://ai.google.dev/gemini-api/docs/deprecations).
The 6 October 2026 refresh report recorded HTTP 404 for both 2.5 models.
The `latest` fallback is a moving alias: it may resolve to the primary model and
does not provide a separate provider or independent quota allowance.

`AI_MAX_INPUT_BYTES` defaults to 262,144 bytes, counting the complete serialised
request. This accommodates the fetcher's existing 60,000-character source limit,
including multi-byte text, instructions and schema. The source limit, output-token
limit, quota limits and zero-spend guard remain in place. Oversized requests are
still held; source text is not silently shortened merely to make a request fit.

## Local diagnostics and first activation

Set the same variables in the terminal environment. `.env.example` documents them
but is not automatically loaded. Keep any private `.env` outside version control.

```bash
export PYTHONPATH=pipeline
python pipeline/ai.py providers  # configuration only; no API calls
python pipeline/ai.py models     # list accessible models; no generation
python pipeline/ai.py probe      # one synthetic generation; reserves one call
python pipeline/run.py --dry-run --only manna-society # source-only, no AI or writes
```

Run the synthetic probe after offline tests pass and the free-tier account is
configured. A successful catalogue lookup is not proof of schema compatibility.
The probe checks the API's structured response, local validation and completion.
Then start a normal refresh for one organisation before enabling the full run.
The probe has not been run against a real account as part of implementation.

## Quota persistence

`pipeline/state/ai_usage.json` contains UTC-day reservations and provider names,
never keys or prompts. A file lock and atomic replacement prevent local concurrent
reservations from exceeding the cap. The GitHub workflow serialises refresh runs.
Before its first call to each provider, a job reserves its whole configured run
allowance and commits/pushes that reservation using normal checkout authentication.
If that checkpoint fails, no provider call is sent. A killed runner cannot erase
an already-persisted reservation. Unused reservations are not refunded: this is
deliberately conservative. New runs from the latest branch read the updated ledger.
Rerunning an older commit cannot overwrite a newer reservation: its checkpoint
push is rejected and no AI request is sent. Start a fresh dispatch from the branch
instead of rerunning an obsolete commit.

Do not delete/reset the ledger to make a same-day rerun fit. Local runs share the
ledger only within that checkout; independent clones and other projects using the
same key are outside this budget. Use the API only through the scheduled job for
shared quota accounting. A local probe reserves locally, so allow for that call in
the remote cap. The provider still enforces its own account/project quotas.

An incomplete source check or AI extraction makes the workflow fail after safe
updates and diagnostic artifacts are saved. Only genuine proposed changes create
a review PR. The summary distinguishes configuration, validated AI responses,
published updates and incomplete checks. No provider response bodies are logged.

Dry runs never call AI, so they neither change the ledger nor push checkpoints.
Provider failures, failed generations and the single bounded 429 retry consume
the reserved allowance. A quota-exhausted refresh holds changed facts for review;
it does not label them successfully verified. Source-fetch failures are reported
separately. Logs contain normalised failure categories without provider bodies.

## Optional fallback

Gemini works alone. To enable OpenRouter later, configure `OPENROUTER_API_KEY`,
`AI_OPENROUTER_MODELS`, `AI_OPENROUTER_FREE_TIER_CONFIRMED=true`, and change
`AI_PROVIDERS` to `gemini,openrouter`. Only explicit `:free` model IDs are allowed.
No paid model is substituted. Choose a current model supporting JSON Schema;
routing requires parameter support and denies provider data collection. If no
compatible endpoint exists, the pipeline holds the extraction rather than weakening
validation. Verify the account's limits and terms before activation.

Adding another provider requires one adapter implementing the structured request
and response contract in `pipeline/ai.py`; feature code does not call provider APIs.
No account has been connected and no repository secrets have been changed locally.
