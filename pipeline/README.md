# The 8 Houses Daily — freshness pipeline

Implements spec §11. Feeds `site/build.py`, which sets the paper. Checks every charity's volunteering page once a week, extracts
role data, and decides what may go live without a human and what may not.

## The shape of it

```
fetch ──▶ isolate main content ──▶ follow role sub-pages ──▶ unchanged? ── done
      ──▶ confirm the published listing ── still supported? ── done, nothing changes
      ──▶ extract ──▶ verify ──▶ copyright guard ──▶ gate ──┬─▶ site check ─▶ commit to main
                                                            └─▶ pull request
```

Operating it day to day, and what each status-issue message means:
[docs/operations.md](../docs/operations.md).

| File | Does |
|---|---|
| `config.py` | Every threshold that affects what a visitor sees |
| `schema.py` | What the model may return vs what gets stored — deliberately different |
| `fetchpage.py` | robots.txt, 1 req/s, conditional GET, content hashing |
| `prompts/extract.md` | The extraction prompt |
| `extract.py` | Model call, verification pass, derived confidence, copyright guard |
| `gate.py` | **Safety-critical.** What may auto-publish |
| `test_gate.py` | 28 tests. The Action refuses to run if these fail |
| `test_fetch.py` | 10 tests on content isolation and hash stability |
| `decay.py` | Freshness state → `data/freshness.json` |
| `run.py` | Orchestrator |
| `sitecheck.py` | The site build's invariants, run before anything is written |
| `health.py` | The self-managing status issue: opens, updates, closes itself |
| `review.py` | Approve or reject held proposals (also the "Review a proposal" workflow) |
| `seed.py` | Creates org stubs from the PoC research, with editorial triage |
| `census.py` | **Scrapability survey. No API key needed — run this first.** |
| `reach.py` | One-off OTP precompute of the travel-time index (Phase 2) |

## Order of operations for a cold start

```bash
python pipeline/seed.py --report    # see the triage, write nothing
python pipeline/seed.py             # create stubs
python pipeline/census.py           # CAN WE READ THESE PAGES? no API key needed
#   -> read docs/census.md before going further
python pipeline/run.py --dry-run    # what WOULD be extracted, writes nothing
python pipeline/run.py              # for real; everything lands in a review PR
```

Do not skip the census. It separates "can we read this page" from "what does it
say", and only the second costs money or produces claims needing review. If the
census says most pages are client-rendered, that is a different project and you want
to know before publishing a hundred unreliable records.

The census also distinguishes two failures that look identical by character count
and lead to opposite decisions: `client_rendered` (framework mount point, needs a
different URL or a headless browser) versus `thin` (real prose, just no role detail
— treat as link-only permanently). Confusing those costs a wasted week.

## Running it

```bash
pip install -r pipeline/requirements.txt
export GEMINI_API_KEY=your-private-key
export AI_GEMINI_MODELS=gemini-3.5-flash-lite,gemini-flash-lite-latest
export AI_GEMINI_FREE_TIER_CONFIRMED=true # only after verifying the project's tier
export PYTHONPATH=pipeline

python pipeline/run.py --dry-run                    # writes nothing
python pipeline/run.py --dry-run --only manna-society
python pipeline/run.py                              # the real thing
python -m pytest pipeline/test_gate.py -q
```

Exit codes: `0` complete with no attention needed · `1` held proposals or incomplete
checks · `2` the run itself broke. The workflow uploads the report, publishes safe
updates, keeps one rolling review PR for real proposals, and updates the status
issue. It fails the job only when the AI integration itself is broken (`ai_broken`:
not configured, or every request failed). One page the AI could not read is
retried next week and noted in the issue rather than turning the job red.
Configuration alone is not labelled a working AI integration.

**Confirmation** (`extract.confirm`, added 17 October 2026). A changed or
never-approved page is first checked against the listing already published: each
role must still be described, and each screening, status, intake, times, season,
commitment, eligibility and team-only claim needs a quotation found verbatim in the
page that contains the fact (`extract._quote_backs`). If everything holds,
`last_success` and the baseline hash advance and **no record changes**; the gate is
not consulted because nothing is proposed. If the page also lists roles we do not
carry, a fresh extraction is a second opinion: only the extra roles are proposed,
beside the current records unchanged, and if it contradicts a listed role on a
critical fact or `who_can_apply` (`run.disagreements`), nothing is confirmed and
the gate sees the full extraction. Anything short of full
support falls through to the extract → gate path exactly as before. The first live
run (8 Oct) published nothing on its own because hand-researched listings never
matched a fresh extraction word for word; without this the paper would have
suspended itself around 1 November. Off switch: `CONFIRM_EXISTING_LISTINGS`.

**Never publish a build break.** Before an auto-publish is written, `sitecheck.py`
runs the site build's own invariants on it. A record the build would refuse goes to
review instead, because one such record stops the deploy and, through the tests,
the next refresh.

The weekly workflow treats review-needed as a completed check, and unexpected
exit codes as failures. Both standard output and errors are saved in the
`freshness-run` artifact. If repository permissions prevent a review pull request,
the report remains available in that artifact and the job summary explains why.

Configure `GEMINI_API_KEY`, model names and free-tier confirmation to enable
extraction and verification. Without an enabled provider, the pipeline still checks source pages. An identical
approved content hash can advance `last_success`; changed pages or pages without
an approved baseline go to review. Their existing facts, approved hash and
`last_success` remain unchanged. The report includes `extraction_available` so this
mode is visible rather than silently claiming a full refresh.

Weekly checks re-read linked role pages even when the landing page is unchanged.
HTTP cache entries are fetch history, not approval: only an approved, single-page
baseline can use a conditional GET. Dry runs write neither records, reports nor
HTTP cache. Matched roles retain their published IDs when titles are reworded,
preserving shared links and saved shortlists.

Dry runs are source-only: they do not generate AI content or reserve quota. Use
`python pipeline/ai.py probe` for an explicit synthetic API compatibility check.
The shared AI interface supports Gemini and optional OpenRouter `:free` fallback;
Anthropic is no longer called. See [account setup](../docs/ai-setup.md).

`human_review_count` counts valid proposals; `failed_count` counts source,
configuration, extraction and record-validation failures. `ai_successful_calls`
counts schema-valid responses (including verification), not successfully updated
charities. `extraction_available` is retained for compatibility and means configured,
not that any request succeeded. Read `results` for every check's outcome and
`ai_diagnostics` for safe provider/model failure categories and HTTP codes.

Run the complete regression checks before changing the refresh workflow:

```bash
PYTHONPATH=pipeline python -m pytest pipeline/ site/ -q
python site/build.py
node site/js/discovery-test.js
node site/js/directory-test.js
node site/js/sharing-test.js
```

## The map data

`data/london-map.json` is generated separately by `site/tools/build_map.py` from
ONS/OS boundary data, not by this pipeline. It changes when administrative
boundaries change, which is to say almost never.

## Reach index (Phase 2)

`reach.py` precomputes public-transport journey times from every London postcode
district to every role location, once, and inverts them into a static lookup. No
API key, no rate limit, no per-request cost, works offline — the same reasoning
that keeps everything else static.

```bash
python pipeline/reach.py --fetch-inputs    # ~1GB, once, not committed
python pipeline/reach.py --build-graph     # Java 17+, ~10 min, ~8GB RAM
python pipeline/reach.py --serve           # leave running
python pipeline/reach.py --compute         # in another shell
```

**It is currently blocked on data, not on code.** No role has `coords` populated
yet, and `--compute` says so and exits rather than producing an empty index. Roles
need at minimum a geocoded `postcode_district`. Until then the site filters by
borough, which is what the data actually supports.

You also need `data/postcode-districts.json` mapping each district to a centroid —
derive it from OS Open Names or the ONS postcode directory, both open data. The
site needs that file anyway, to resolve a typed postcode client-side without
sending it anywhere (spec §13).

## Content isolation (added after Phase 0)

Real charity pages are 76–95% boilerplate. Hashing a whole page meant the rotating
"Latest" news sidebar changed the hash every week, so all 34 pages looked changed
every run and the review queue was permanently full. `fetchpage.py` now isolates
main content before hashing or extracting, and follows role links one level down
because most landing pages carry no role detail. See `docs/scrapability.md`.

`test_fetch.py::test_hash_stable_when_only_sidebar_changes` is the load-bearing
test. Do not weaken it.

## The gate

The one thing to understand before changing anything. It decides what reaches a
visitor unreviewed, and it has three properties worth preserving:

**Pure.** No I/O, no network, no clock. Same records in, same routing out — which
is why it can be tested exhaustively rather than hopefully.

**Fails closed.** Missing confidence, empty extraction, unhandled exception, a page
that returns no roles at all — every unclassifiable case routes to review. There is
no path where "we didn't recognise this" means "publish it".

**Critical fields are absolute.** A change to `screening.*`, `status` or
`next_intake` goes to review regardless of confidence, change size, or config. Get
these wrong and someone travels across London to be turned away, or we misstate
somebody else's safeguarding rule. `test_every_declared_critical_field_is_actually_gated`
fails if a field is added to `CRITICAL_FIELDS` but never actually compared.

## Confidence is derived, not self-reported

The model is never asked how confident it is — self-reported confidence is weakly
calibrated and tends to be cheerful. Instead:

1. Extract normally.
2. For each critical claim that asserts something (`unknown` and `null` assert
   nothing, so they're skipped), a second pass sees the claim next to the page and
   judges whether the page actually supports it and supplies a supporting quotation.
   The quotation must occur in the supplied source text. Silence is not support.
3. Unsupported claims are forced to `unknown` **before the gate sees them**.
4. `confidence = supported / checked` — an observable, not an opinion.

If the verification call itself fails, confidence is `0.0`. A broken verifier is not
permission to publish.

## Copyright is enforced, not requested

`prompts/extract.md` asks for paraphrase. `extract.py` checks. Any verbatim run of
8+ words shared with the source page fails the whole extraction and routes to
review. Eight is deliberately stricter than a quote ceiling, because we aren't
quoting — we're restating in our own words.

## Weekly review

The Action keeps one rolling PR (`freshness/review`) listing what it held back,
field by field. Never merge it. Decide from the browser with **Actions → Review a
proposal → Run workflow**, or on `main` after `git fetch` with
`pipeline/review.py`. It reads the review branch or a local
`pipeline/state/review.json`, whichever run is newer:

```bash
python pipeline/review.py list                # what is waiting
python pipeline/review.py show crisis         # field-by-field changes, new and missing roles
python pipeline/review.py approve crisis      # publish it as human-reviewed
python pipeline/review.py approve crisis --drop "Kitchen helper" --keep-missing
python pipeline/review.py reject crisis       # current listing stays
```

Read the charity's page before approving: approving marks every record
`provenance.reviewed_by_human`. `approve` also records the page version as the
approved baseline (`check.content_hash`, `check.last_success`), so an unchanged
page is not proposed again. It refuses stale or repeated decisions, schema-invalid
records, duplicate ids and anything the site build would reject; it writes
nothing in those cases. `reject` keeps the current listing and records the page
version, meaning "the listing is still right for this page". Roles no longer found
are removed on approval unless `--keep-missing` keeps them as status unknown.
Where a re-read leaves a descriptive field blank (postcode, commitment, timings,
who can apply, skills, eligibility) because the page does not say, `approve` keeps
the current value and says so; `--take-blanks` accepts the blanks instead.
Screening, status and intake are never carried forward: unknown is the safe value.
Renamed roles: `--same "New title=Old title"` keeps the existing id and links.

Then commit `data/` and push; Cloudflare deploys it. Close the PR without
merging. Do not loosen the gate to reduce the queue.

## Setup

1. Follow [AI setup](../docs/ai-setup.md) using the intended Google account.
2. Confirm the API key's project is Free Tier and has no billing account attached.
   The workflow fixes `AI_DAILY_USD=0`; it cannot inspect project billing itself.
3. Settings → Actions → General → allow Actions to create pull requests.
4. Change `USER_AGENT` in `config.py` to a real contact URL before the first run.
   A charity that wants us to stop needs somewhere to say so.
5. Email the charities before the first real run (spec §16). It converts a possible
   grievance into a relationship, and several may just offer better data.

## What it deliberately doesn't do

- **No client-side rendering.** A page whose roles load via JavaScript yields almost
  no text; the fetcher reports that honestly rather than extracting from a shell. If
  several charities turn out to be React apps, that's a Phase 3.1 conversation about
  a headless browser — not something to paper over.
- **No automatic deletion.** A role that vanishes is queued for review; existing
  published records remain until a human approves a change. Pages get restructured.
- **No writing to `provenance.reviewed_by_human`.** Only a human running
  `review.py approve` sets that, which is why the model can't reach it.
