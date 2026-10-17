# Running the paper hands-off

The paper looks after itself. It tells you when it can't, and the fix is usually a
button in GitHub rather than a terminal.

**The one rule: if there is no open issue labelled `status: refresh` or
`status: deploy`, nothing needs you.** GitHub emails you when one opens or gets a
comment. You watch your own repository by default; check that **Watch** on the
repo page is not set to "Ignore".

## What runs by itself

| When | What | You hear about it |
| --- | --- | --- |
| Sundays, 04:00 UTC (GitHub may start it hours late) | **Weekly freshness check.** Reads every charity page. Listings the page still supports are confirmed; safe changes publish; everything else is held for you. | Status issue, only if something needs you |
| Every morning, 05:17 UTC | **Build and deploy.** Dates the masthead and applies the freshness rules: 21-day suppression, the 60-day banner, and "closed for the season" only outside the season. | Status issue, only if the build fails or cannot publish |
| When you choose | **Review a proposal.** Approve or reject from the browser. | Its run summary |

## How the weekly check decides

1. **Page unchanged** since the last approved version: the listing still stands.
   No AI is used.
2. **Page changed, or never approved**: first it asks whether the page still
   supports what we already publish. Every role must still be on the page, and
   every screening, status, intake, times, season, commitment, eligibility and
   team-only claim needs an exact quotation from it that contains the fact (an age
   of 18 needs the 18). If all of that holds, the check succeeds and **no record
   changes**. If the page also lists roles we don't carry, a second reading
   proposes just those, and if that reading contradicts a listed role on a
   critical fact, nothing is confirmed and step 3 applies.
3. Otherwise, the page is re-read in full and the gate decides. Changes to
   screening, recruitment status or intake, new roles and missing roles always
   wait for a person. Other changes publish by themselves if the build would
   accept them.

Confirmation can be switched off with `CONFIRM_EXISTING_LISTINGS` in
`pipeline/config.py`.

## What the status issue can say, and what to do

### "N charities have changes waiting for your decision"

Optional. Nothing is published until you decide. Meanwhile, those notices stop
asserting screening and status after 21 days, so the paper stays honest.

1. Open the **Freshness review** pull request. Each charity's changes are shown
   field by field. Also read the charity's own page: approving is your claim
   that you looked.
2. **Actions → Review a proposal → Run workflow**. Put the charity id (shown in
   brackets in the issue and the PR) under *charities*, choose approve or reject,
   and run it. Several ids can be decided together, comma-separated. Prefer that
   to starting several runs at once: GitHub keeps only one run waiting and
   cancels the one before it.
   - *drop*: leave out a proposed role, e.g. one that duplicates an existing
     role under another name. Titles separated by `|`.
   - *same*: a proposed role is an existing one renamed. Use
     `New title=Old title` so its links survive.
   - *keep missing*: keep roles the page no longer mentions, as status unknown.
3. The workflow commits the decision, redeploys, and updates the PR. The issue
   updates itself on the next run.

**Reject** means "the current listing is still right for this page". That
version of the page is not proposed again.

Locally it is the same thing: `py pipeline\review.py list`, `show <id>`,
`approve <id>` or `reject <id>`, then commit `data/` and push.

### "Some charity links are failing"

The page failed twice in a way a browser would also hit (a 404, or an expired or
mismatched certificate). Open it. If the charity moved its volunteering page, put
the new address in `volunteer_url` in `data/orgs/<id>.json` and push. If the fault
is theirs, there is nothing to do: their notices already show as not checked
recently, and the issue clears when the site recovers.

### "The AI check is not working"

The issue names the fix for the failure it saw:

- **Key refused (401/403), or HTTP 400**: make a new key in Google AI Studio, in
  the same Free Tier project, and replace the `GEMINI_API_KEY` secret (Settings →
  Secrets and variables → Actions).
- **Models unavailable (404)**: `py pipeline\ai.py models`, then set the
  `AI_GEMINI_MODELS` repository variable to two current Flash-Lite models.
- **Quota used up (429)**, or Gemini unreachable: normally clears by itself. It
  only needs you if it happens two weeks running.
- **No provider enabled**: the `GEMINI_API_KEY` secret is missing, or the
  `AI_GEMINI_FREE_TIER_CONFIRMED` variable is not `true`.

Existing listings are kept throughout.

### "The refresh stopped before it checked any charity page"

Usually a safety test failed, and the run refuses to touch anything until it
passes. Open the run and read the first red step. Locally:

```powershell
$env:PYTHONPATH = "pipeline"
py -m pytest pipeline/ site/ -q
```

A record edited by hand is the usual cause, and the failing test names it.

### "Deploy is failing — readers are seeing an old edition"

The build refused a record, or a site test failed. The log lists the record and
the reason. Fix or revert it in `data/orgs/` and push. The live site keeps its
last good edition meanwhile.

### "Deploy: GitHub cannot publish the site yet"

A one-off setup. Until it is done, nothing reaches readers unless you run
`npx wrangler deploy` yourself, and that includes the daily rebuild that keeps the
date and freshness rules true.

1. **Token:** Cloudflare dashboard → [Account API tokens](https://dash.cloudflare.com/?to=/:account/api-tokens)
   → **Create Token** → under *Permission policies*, open **Custom** → **Edit
   Cloudflare Workers** → limit it to your account → create, and copy the token
   (Cloudflare shows it only once).
2. **Account ID:** Cloudflare dashboard → **Workers & Pages** → *Account
   Details* → copy **Account ID**. Or press Ctrl+K and search "Copy account ID".
3. **GitHub:** repository → Settings → Secrets and variables → Actions → **New
   repository secret**, twice: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
   (A repository *variable* for the account ID works too.)
4. Actions → Build and deploy → Run workflow. The issue closes itself.

### "Listings are going stale" / "publication suspended"

The median charity has not been confirmed for 45 days or more. At 60 days every
page says publication is suspended. It lifts by itself as checks succeed.
Deciding waiting proposals speeds that up, because each decision resets that
charity.

## What never needs you

- **Sites that turn away automated checks** (HTTP 403 from GitHub's servers; seven
  at the last count). Their notices show as not checked recently after 21 days.
  That is their choice, and the honest result.
- **One page the AI could not read this week.** It is retried next week. It only
  needs you if the same charity is listed three weeks running.
- **Pages deferred** to next week's AI allowance.
- **Manual runs for a few charities** (the *only* box): they publish what they
  can, but leave the review PR and the status issue alone, because their report
  covers only those charities.

## Things GitHub does that you should know

- **Scheduled workflows in public repositories are switched off after 60 days
  without repository activity.** The weekly check commits every week, so this
  only happens after two months of a broken refresh, by which time the status
  issue will have emailed you about eight times. To turn them back on: Actions →
  the workflow → **Enable workflow**.
- **Scheduled runs can start hours late**, and during GitHub incidents are
  occasionally skipped. Nothing depends on the exact time.
- **Settings → Actions → General → "Allow GitHub Actions to create and approve
  pull requests"** must stay on for the review PR. If it is off, the proposals
  still appear in the run summary and the `freshness-run` artifact.
