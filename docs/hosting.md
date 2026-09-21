# Hosting

The site is static HTML. There is no server, no database and no runtime API, so
almost anything will serve it. Two constraints shape the choice:

**It must be served from the root of a domain.** Every internal reference is
root-absolute — `/assets/app.css`, `/weekly/hackney/`. On a subpath such as
`user.github.io/repo/` every one of them 404s and you get a page with no
stylesheet. A custom domain fixes this on any host.

**The build imports nothing outside the Python standard library.** No
`pip install`, no lockfile, nothing to go stale. Build command is one line.

---

## The setup, for 8houses.co.uk

**Use Workers, not Pages.** Since Workers gained native static-asset serving,
Cloudflare's own guidance is to start new projects there; Pages still works and is
not deprecated, but their investment has moved. The dashboard steers you to Workers
by default, and that is now the right default.

`wrangler.jsonc` in the repo root does the configuring. It declares an
**assets-only** Worker — no script, nothing executed — which keeps the deployment
consistent with spec §3 (no runtime intelligence) and §2 A4 (nothing that can be
abused or run up a bill).

1. Push the repo to GitHub.
2. Cloudflare dashboard → **Workers & Pages** → **Create** → **Import a
   repository**, and pick it.
3. Build settings:

   | Field | Value |
   |---|---|
   | Build command | `python3 site/build.py` |
   | Deploy command | `npx wrangler deploy` |

   There is no "output directory" field — `wrangler.jsonc` says `./dist`.

4. Environment variables → add `SITE_URL` = `https://daily.8houses.co.uk`. The
   Python version comes from `.python-version` in the repo.
5. Deploy. You get a `*.workers.dev` URL immediately — a root, so it works before
   any custom domain exists.
6. **Custom domain** → add `daily.8houses.co.uk`. The zone is in the same account,
   so Cloudflare writes the DNS record and issues the certificate itself.
7. **Analytics** (optional, one click) → Web Analytics. Cookieless and
   IP-anonymising, which is what spec §13 asks for, and it needs no consent banner
   because it sets nothing.

Two settings in `wrangler.jsonc` are load-bearing. `html_handling:
auto-trailing-slash` makes `/about/` resolve to `/about/index.html`, which the
whole URL scheme depends on. `not_found_handling: 404-page` serves the paper's own
"No such page in this edition" instead of a bare Cloudflare error.

## Option B — GitHub Pages

Keeps everything in one place, which matters because the weekly freshness check
already runs there. `.github/workflows/deploy.yml` is written and ready.

1. Settings → **Pages** → Source: **GitHub Actions**.
2. Settings → **Secrets and variables** → **Actions** → **Variables** → add
   `SITE_URL`. The workflow fails loudly without it rather than quietly publishing
   canonical URLs pointing at `example.org`.
3. Add a custom domain in Settings → Pages. This writes a `CNAME` file, which the
   workflow checks for — **without a custom domain the deploy deliberately fails**,
   because a project page serves from `/repo/` and the site would be broken.
4. Push to `main`.

## Neither, for now

`python site/build.py --serve` runs it at `localhost:8000`. Fine for showing
someone. Or drag `dist/` onto [netlify.com/drop](https://app.netlify.com/drop) for
a throwaway URL — the same build command and output directory apply if you later
connect the repo properly.

---

## DNS, once you have picked a name

A subdomain is easier than the apex and does not tie the paper to the main site's
DNS:

```
CNAME   daily   <target given by your host>
```

Apex domains need ALIAS/ANAME support, which Cloudflare has and many registrars do
not. Use a subdomain unless you have a reason not to.

---

## What still needs doing regardless of host

- ~~A separate page for the crawler's contact URL.~~ **Done.** The paper builds
  its own `/bot/` page, and `pipeline/config.py` points the user agent at it. The
  page describing the crawler is built by the same repository that runs the
  crawler, so the two cannot drift apart. It goes live with the first deploy.
- **`ANTHROPIC_API_KEY`** as a GitHub repository *secret* — for the weekly
  freshness check, not for the site build. The site build never calls a model.
- Settings → Actions → General → **allow Actions to create pull requests**, so the
  weekly check can open its review PR.
- **A spend limit** in the Anthropic console.

---

## Costs

| Item | Cost |
|---|---|
| Hosting | £0 — both options are free well beyond any traffic this will see |
| Domain | ~£10–15/year |
| Weekly freshness check | under £1/month of model usage |
| Everything else | £0 — no server, no database, no runtime API |

---

## Two things that will bite

**Canonical URLs are invisible when wrong.** `SITE_URL` feeds the sitemap, the
canonical tags and the Open Graph tags. Set it wrong and nothing looks broken —
you simply do not rank, and you find out months later. Check one page's
`<link rel="canonical">` after the first deploy.

**Do not commit `dist/`.** It is generated and `.gitignore`d. If it ever appears in
a diff, something has gone wrong with the build setup rather than with the site.

---

## Which one

Both are free and both work. The differences that matter for *this* project:

| | GitHub Pages | Cloudflare Pages |
|---|---|---|
| Works before you own a domain | **No** — a project page serves from `/repo/` and every root-absolute path breaks | **Yes** — `*.pages.dev` is a root |
| Preview URL per pull request | No | **Yes** |
| Build config lives in the repo | **Yes** — `deploy.yml` is version-controlled | Partly — `.python-version` yes, build command and `SITE_URL` are in a dashboard |
| Cookieless analytics included | No | **Yes** — Web Analytics, free, no consent banner |
| Deploy logs beside the freshness logs | **Yes** — one Actions tab | No — two places to look |
| Build limits | 10/hour, 100GB/month bandwidth | 500/month, unlimited bandwidth |
| CDN | Fastly-backed, fine | More points of presence |

Neither the bandwidth nor the build limits matter here. The site is 1.7MB.

**Recommendation: Cloudflare Pages**, for one reason above the others. The whole
freshness pipeline is built around a weekly pull request that changes what the
notices say, and a preview URL lets you *look at the rendered change* before
merging it. That fits the review workflow this project already has. The cookieless
analytics is a second, smaller reason: spec §13 asks for exactly that, and the
alternative is adding a third party.

**The case for GitHub Pages** is real though, and it is about legibility: the whole
deployment is described by a file in the repo that anyone can read, which fits a
project whose stated failure mode is the maintainer disappearing. If you already
own the domain and value that over previews, take it — `deploy.yml` is written.

**What would change my mind:** if the DNS for `8houses.co.uk` is not on Cloudflare
and you would rather not move it, GitHub Pages avoids a second vendor for very
little loss.
