# Phase 0 reconnaissance — what the real pages actually look like

**Date** 25 August 2026
**Method** Manual fetch and read of live volunteering pages, treating each as the
pipeline would. Three organisations done in full; findings generalise.
**Status** 5 of 32 organisations have verified role data (11 roles). 27 remain.
Two of the original 34 were excluded as not being sources of volunteering roles.

---

## Why this changed the build

I expected Phase 0 to be data entry. It turned out to be a design review, because
four things about real charity pages contradict assumptions baked into the spec and
the pipeline. Two were bugs, two are product decisions you need to make.

---

## Finding 1 — The pipeline's change detection was broken (fixed)

**Severity: high. This would have killed the project quietly.**

Glass Door's volunteering page returned roughly 6,000 tokens of navigation, language
switcher, tag cloud, "Latest", "Most read", newsletter form and footer, wrapped
around about **200 tokens of actual role content**. Measured boilerplate ratio on a
representative fixture: 76–85%. On the real page it was closer to 95%.

Two failures follow:

1. **The model would see bait.** "Sleep Out", "2027 London Marathon", "Challenge
   Events" and "Jobs at the charity" all sit in the navigation. An extractor reading
   the whole page can invent roles from them.

2. **Every page would look changed every week.** The "Latest" sidebar rotates
   whenever the charity publishes news. Hashing the whole page means all 34 pages
   change every run, all 34 get re-extracted, and the review PR is permanently full.
   The maintainer stops reading it inside a month, and §11.5's decay banner fires on
   a system that was technically working the whole time.

That second one invalidated the pipeline's entire cost model — the "roughly eight
diffs a week, ten minutes of reading" estimate in §11.3.

**Fixed.** `fetchpage.py` now isolates main content (trafilatura, with a DOM-
stripping fallback) *before* hashing or extracting, and hashes only that region.
`test_fetch.py::test_hash_stable_when_only_sidebar_changes` is the load-bearing
test: same role content, rotated sidebar, hash must not move.

## Finding 2 — Role detail lives on sub-pages (fixed)

The volunteering landing page is usually a signpost, not content. Glass Door's
landing page says only that volunteers "help run our winter night shelters, support
caseworkers... deliver donations... and help us with translation". Everything useful
— 21 venues, 6pm–9pm, November to April, currently closed — is one click down at
`/winter-night-shelter-volunteers`.

Extracting from the landing page alone would have produced four near-empty records
per charity.

**Fixed.** `find_role_links()` follows up to six role links one level down and
concatenates them into a single extraction payload. It filters out the things that
look like roles but aren't: donate pages, marathons, sleep-outs, paid jobs, blog
posts. `test_role_links_found_and_junk_excluded` covers this.

## Finding 3 — "Teams only" is a category the spec didn't model (fixed)

**The Whitechapel Mission accepts no individual volunteers at all.** Their programme
is designed for corporate and community teams, booked through an online diary, one
booking per organisation per month. There's also an access restriction: they ask
people not to volunteer in the third trimester of pregnancy.

Every Whitechapel role in the Phase 1 prototype was an individual role. Listing them
that way sends individuals to be turned away — precisely the harm this whole site
exists to prevent, and it would have been our most visible failure.

**Fixed.** New field `who_can_apply: individual | team_only | either | unknown`.
§5 treated corporate organisers as "a Phase 4 concern at most"; that was wrong.
Team-only isn't a nice-to-have segment, it's a **safety flag on existing roles**.

## Finding 4 — The screening facet probably cannot work (needs your decision)

**Not fixed. This is a product decision, not a bug.**

Across all 7 verified roles, `screening.dbs` is `unknown` **7 times out of 7**. None
of the three charities states a DBS requirement, a minimum age, or a references
policy anywhere on its volunteering pages.

That's a problem, because §Appendix A called screening tolerance "the facet nobody
else offers" and §4 G2 made it one of four decision-critical facts. If the source
data is silent, the filter has nothing to filter on. "No DBS needed" would return
zero results — and per principle 4, a facet that can't discriminate isn't a facet.
It's the PoC's failure mode reached from the opposite direction.

Three options:

- **(a) Demote it to display only.** Keep showing "Their page doesn't say — worth
  asking before you commit", which is genuinely useful and honest, but drop it as a
  filter. Cheapest, and available today.
- **(b) Ask the charities.** This is the strongest argument yet for §19 Q3 going the
  relationship route rather than staying purely observational. One email per charity
  with four questions would populate the field properly. Costs goodwill and time you
  said you didn't have.
- **(c) Drop the claim.** Remove screening from G2 and stop advertising it.

My recommendation is **(a) now, (b) opportunistically** — put the four questions in
the §16 launch email you're sending anyway, and take whatever comes back. Do not
ship a screening filter on observational data.

## Finding 5 — Three of my own enums were too narrow (fixed)

Each of these was forced by a specific real page, and each mattered.

**`dbs: "required_unspecified"`.** Depaul's Nightstop pages confirm a DBS check is
required but never say which level. Recording that as `unknown` throws away the
actionable half of the fact — "you will definitely need a check" is very different
guidance from "we don't know whether you need one". First page in five to state a
DBS requirement at all.

**`location_type: "own_home"`.** Nightstop hosting happens at the volunteer's own
address. Travel time is meaningless and an area filter must not exclude it. Marking
it `remote` would have matched correctly but described it wrongly, and "Remote —
anywhere" is a strange thing to say about someone sleeping in your spare room.

**`activity: "varies"`.** HandsOn London runs a rotating calendar of one-off
projects rather than fixed roles. Picking a single activity would have been
fabrication. Roles marked `varies` show when no activity filter is set and are
excluded when one is — we never promise a match we can't support.

The extraction prompt teaches all three explicitly, with a warning that `varies` is
for genuinely rotating programmes and not an escape hatch for uncertainty.

## Finding 6 — `commitment` conflates frequency with depth (not fixed)

Nightstop hosting exposed this. The *shifts* are entirely flexible — you pick your
nights, host as often or as little as you like. But *becoming* a host means a home
visit, a DBS check and safeguarding training. It is low-frequency and high-depth.

A weekly kitchen shift is the opposite: high-frequency, low-depth. One field can't
carry both, and right now `commitment: long_term` is doing the work of routing
hosting to Door C, justified by §7.1's own definition, while `specific_times`
carries the flexibility.

That holds for now. If it starts producing wrong answers, the fix is a separate
`depth` field rather than more commitment values. Flagging rather than fixing,
because two orgs is not enough evidence to restructure a primary axis.

---

## Scrapability by CMS pattern

| Pattern | Seen at | Main content isolable? | Notes |
|---|---|---|---|
| WordPress, simple theme | Manna Society | Yes, cleanly | Role detail on the page itself. Easiest case. |
| Bespoke / static | Whitechapel Mission | Yes | Role detail split across `/volunteering`, `/process`, `/volunteering/clothing-challenge`. Needs sub-page following. |
| ASP.NET charity CMS | Glass Door | Yes, after stripping | ~95% boilerplate. Publishes its own "Updated:" date — a better freshness signal than our hash. |
| Modern marketing site | Depaul UK | Yes | Role detail spread across `/nightstop-volunteer/`, `/nightstop-faqs/` and per-city pages. The FAQ page held the screening detail the main page omitted. |
| Squarespace-style | HandsOn London | Partly | Roles live behind an account-gated booking calendar. Only the named campaigns (Wrap Up London) are enumerable from public pages. |

**Bonus win:** several CMSes print a real "Updated: 29th July, 2026" in the page.
`cms_updated()` now captures it. Where present, trust it over the content hash.

**Not yet encountered but expected:** client-rendered sites (React/Vue) where the
role list loads via JavaScript. `fetchpage.fetch()` reports these honestly rather
than extracting from an empty shell — `"main content only N chars — page is probably
client-rendered"`. If more than about five of the 34 turn out this way, that's a
conversation about a headless browser in CI, not something to paper over.

---

## Verified data so far

| Organisation | Charity no. | Roles | Notable |
|---|---|---|---|
| Manna Society | 294691 | 2 | Kitchen 9.30am–1.45pm, **3-month minimum**, waiting list. Computer suite Mon–Fri 10.00–13.15. |
| The Whitechapel Mission | 227905 | 2 | **Teams only.** Breakfast Challenge from 5.45am. |
| Glass Door | 1083203 | 3 | Night shelter **currently closed**, reopens November. 21 venues, 6–9pm weekly. |
| Depaul UK | — | 2 | Nightstop host — **at your own home**, nights you choose, DBS and home visit. Plus a driver role. |
| HandsOn London | 1140291 | 2 | Wrap Up London coat collection, November only. Community Day calendar is account-gated. |

**11 roles across 5 organisations.** Two structural gaps in the earlier dataset are
now closed: Door C ("Something bigger") had nothing in it, and both one-off roles
were teams-only, so "One day + on my own" returned zero. Both now return results.

Screening picture across all 11: `unknown` × 9, `required_unspecified` × 2. Still no
page anywhere states a DBS *level*, a minimum age, or a references policy. Finding 4
stands, and the launch email in `launch-email.md` is the route to fixing it.

Note what the data does *not* claim. Seven roles, seven `dbs: "unknown"`, five
`min_age: null`, two `status: "unknown"`. Every one of those is a page being silent,
recorded as silence rather than guessed at. Two Glass Door records carry
`confidence: 0.4` because the landing page named the role but no detail page
confirmed it.

---

## Phase 2 note — the map is blocked on data, not code

The borough tile map is built and works. What it cannot yet do is filter by travel
time, because no role has coordinates. Of 11 roles: 3 carry a postcode district, 4
inherit their organisation's borough coverage, and 4 have no location at all
(hosting happens at your home; two HandsOn programmes move around).

That is why it is a tile cartogram rather than a pin map. Pins on a street map imply
address-level accuracy; a borough tile says exactly as much as we know. It also
makes small inner boroughs — Islington, Hackney, Kensington, where most services
actually are — as easy to tap as Havering.

`pipeline/reach.py` is written and runnable. `--compute` deliberately refuses to
produce an empty index and tells you the data is missing instead. Populate `coords`
during extraction and the map upgrades from borough filtering to travel time
without a redesign.

## The remaining 27

Now that the fetcher handles boilerplate and sub-pages, the pipeline can do the
first pass rather than you doing it by hand. Recommended order:

1. ~~**Seed the org files.**~~ Done — `pipeline/seed.py`, 32 in scope, idempotent.
2. **`python pipeline/census.py`** — no API key needed. Which pages fetch, which are
   client-rendered, which are robots-blocked, boilerplate ratio for each, and the
   role sub-pages extraction would read.
3. **Read `docs/census.md` before extracting anything.** If it says 25 of 27 are
   clean, proceed. If most are client-rendered, stop — that's a different project.
   The census distinguishes `client_rendered` (framework mount point; needs a
   different URL or a headless browser) from `thin` (real prose, no role detail;
   link-only permanently). Those lead to opposite decisions.
4. **Run for real.** Everything lands in a review PR, because §11.3 routes all new
   roles to review regardless of confidence. Expect a large first PR; that's correct
   for a cold start, and it's a one-off.
5. **Then send the §16 emails**, with the four screening questions attached.

Do not skip step 3. The census is cheap and it's the difference between finding out
now and finding out after you've published 160 unreliable records.
