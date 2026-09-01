# The 8 Houses Daily — freshness pipeline

Implements spec §11. Feeds `site/build.py`, which sets the paper. Checks every charity's volunteering page once a week, extracts
role data, and decides what may go live without a human and what may not.

## The shape of it

```
fetch ──▶ isolate main content ──▶ follow role sub-pages ──▶ extract
      ──▶ verify ──▶ copyright guard ──▶ gate ──┬─▶ commit to main
                                                └─▶ pull request
```

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
export ANTHROPIC_API_KEY=sk-ant-...
export PYTHONPATH=pipeline

python pipeline/run.py --dry-run                    # writes nothing
python pipeline/run.py --dry-run --only manna-society
python pipeline/run.py                              # the real thing
python -m pytest pipeline/test_gate.py -q
```

Exit codes: `0` nothing needs review · `1` review needed · `2` the run itself broke.

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
   judges whether the page actually supports it. Silence is not support.
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

The Action opens one PR. Read `pipeline/state/review.json`: each item carries the
reasons, the changed fields, and the proposed records. Accept what's right into
`data/orgs/*.json`, set `provenance.reviewed_by_human: true`, merge.

Expect roughly eight items a week — ten minutes of reading. If it's consistently
more, the confidence threshold is probably too tight rather than the pages being
unusually volatile.

## Setup

1. `ANTHROPIC_API_KEY` as a repository secret.
2. **Set a spend limit in the Anthropic console.** The Action can't enforce one.
   Realistically this costs well under £1/month, but a limit turns a runaway loop
   into a failed job rather than a bill.
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
- **No deletion.** A role that vanishes from a page is set to `unknown` and queued
  for review, never removed. Pages get restructured.
- **No writing to `provenance.reviewed_by_human`.** Only a human merging a PR sets
  that, which is why the model can't reach it.
