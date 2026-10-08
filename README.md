# The 8 Houses Daily

A free newspaper of volunteering notices from London homelessness charities. It
lists **posts, not organisations** — you cannot volunteer for an organisation, you
volunteer for a particular morning in a particular building, having satisfied
whatever they ask first. Every notice links to the charity's own page.

No applications, no accounts, no vetting, no advertising. Everything is static:
no server, no database, nothing that can run up a bill.

---

## Start here

```bash
# 1. Python side
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt

# 2. Node side — only for the browser tests
npm install

# 3. Check it all works (expect 145 passing)
export PYTHONPATH=pipeline
python -m pytest pipeline/ site/ -q

# 4. Build and look at it
python site/build.py --serve      # http://localhost:8000
```

Needs Python 3.11+ and Node 20+.

### On Windows (PowerShell)

`python` is usually intercepted by a Microsoft Store stub. Use the launcher:

```powershell
py --version                       # if this errors: winget install Python.Python.3.12
py -m venv .venv
.venv\Scripts\Activate.ps1         # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
py -m pip install -r pipeline\requirements.txt
npm install

$env:PYTHONPATH = "pipeline"
py -m pytest pipeline/ site/ -q
py site\build.py --serve
```

Worth turning the stub off while you are there: Settings → Apps → Advanced app
settings → App execution aliases → switch off **python.exe** and **python3.exe**.

Environment variables are set differently in PowerShell — `$env:SITE_URL = "..."`
rather than `export SITE_URL=...`.

---

## Phase 0 is done

All 32 organisations have been read. **75 roles across 30 of them**; two place no
notices and carry `link_status: "link_only"`.

What that leaves, in order:

1. **Deploy.** The crawler's user agent points at the paper's own `/bot/` page,
   which has to resolve before the crawler visits anybody.
2. **`python pipeline/run.py --dry-run`** — the freshness pipeline has never met a
   live charity page. It now has 75 records to diff against, which is a far better
   first run than a cold start.
3. **Send `docs/launch-email.md`** to all 32, with the four screening questions.
   A fifth of these charities already publish what the questions ask for.
4. **Populate `coords`** to unblock `pipeline/reach.py` and travel-time filtering.

`pipeline/census.py` still works and needs no API key. It surveyed the
unresearched organisations, and there are none left, so it is now a health check
rather than a first step.

---

## What is where

| Path | What it is |
|---|---|
| `site/build.py` | The static site generator. One file, no dependencies. |
| `site/static/` | The stylesheet and the client-side JavaScript. |
| `site/tools/build_map.py` | Turns ONS/OS boundary data into the borough map. Rarely run. |
| `site/test_build.py` | 103 tests on the built site. |
| `pipeline/` | The weekly freshness check: fetch, extract, gate, publish. |
| `pipeline/census.py` | **Run this first.** Can we read these pages? No API key. |
| `pipeline/seed.py` | Creates organisation stubs. Already run. |
| `data/orgs/*.json` | The notices. 32 organisations, 5 with data so far. |
| `docs/scrapability.md` | What reading real charity pages taught us. Worth reading. |
| `docs/launch-email.md` | The email to send all 32 before the first real run. |
| `london-volunteering-spec-v0.3.md` | The spec. Start at §0 and §14. |

`dist/` is generated — never edit it, never commit it.

---

## Before anything touches a charity's website

1. **Deploy the site.** The crawler's user agent points at the paper's own
   `/bot/` page, which explains what it does and how to stop it. That page has to
   resolve before the crawler visits anyone.
2. **Set a spend limit** in the Anthropic console. Realistically under £1/month,
   but a limit turns a runaway loop into a failed job rather than a bill.
3. **Send the launch email** (`docs/launch-email.md`) to all 32. It converts a
   possible grievance into a relationship, and the four screening questions in it
   are the only route to data no charity publishes.

## Hosting

Full instructions in **`docs/hosting.md`**. The short version: it is static HTML,
the build imports nothing outside the standard library, and hosting is free.

- **Cloudflare Workers** (recommended) — import the repo, build command
  `python3 site/build.py`, deploy command `npx wrangler deploy`, set `SITE_URL`.
  `wrangler.jsonc` declares an assets-only Worker pointing at `dist`; the Python
  version comes from `.python-version`. Cloudflare's guidance since Workers gained
  static-asset serving is to start here rather than on Pages.
- **GitHub Actions** — `.github/workflows/deploy.yml` builds and validates the
  site using the `SITE_URL` repository variable. It deploys to the existing
  Cloudflare Worker when `CLOUDFLARE_API_TOKEN` is configured as a repository
  secret and `CLOUDFLARE_ACCOUNT_ID` as a repository variable (or secret).
  Without those credentials, it saves the validated build as an artifact and
  reports that automatic deployment is not configured. Local Wrangler releases
  remain available.

**It must be served from a domain root.** Every internal reference is
root-absolute, so a project page at `user.github.io/repo/` breaks every one of
them. The production site is hosted at `https://daily.8houses.co.uk/` on Cloudflare;
the workflow does not publish to GitHub Pages.

---

## Two things worth knowing before you change anything

**Notices are roles, not charities.** This is the spine. A charity-level record
cannot answer "can I do this on Saturday", which is why the site this replaced had
facets matching two-thirds of its own corpus and discriminating nothing.

**Where a charity's page is silent, the site says so.** It does not guess. Nine of
eleven notices carry "Not stated" against screening because not one charity
publishes whether a DBS check is needed. That is the honest answer and the build
refuses to publish anything stronger without a verified source.
