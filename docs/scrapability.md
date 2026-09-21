# Phase 0 reconnaissance — what the real pages actually look like

**Date** 25 August 2026
**Method** Manual fetch and read of live volunteering pages, treating each as the
pipeline would. Three organisations done in full; findings generalise.
**Status** **Complete.** All 32 organisations read; 75 roles across 30. Four of
the original 34 turned out not to be sources of volunteering roles: StreetLink and
Homeless Link excluded up front by judgement, Streets of London and Cardboard
Citizens found by reading them (Finding 4g).

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

## Finding 4b — Marketing prose describes roles the vacancy list does not offer

**akt is the clearest case yet of the bait problem in Finding 1.**

Their volunteering page runs several hundred words on what volunteers do —
mentoring a young person for an hour a week, walking in a Pride parade, presenting
at a local school, fundraising. Rich, specific, quotable. Then the *opportunities*
section reads:

> new volunteering opportunities coming soon... Stay tuned!

There are no open roles. An extractor reading the prose would confidently produce
three open vacancies, each with plausible detail, and send people to apply for
nothing.

Two consequences.

**For the extraction prompt.** Describing a role type is not offering it. The
prompt already says `status: open` only where the page says roles are available,
but this is the case that makes it concrete, and it is worth naming in the prompt
explicitly: prefer the vacancy list over the prose when the two disagree.

**For the records.** Both akt roles are stored with `status: "closed"` and
confidence 0.5–0.6, which puts a `NOT RECRUITING` stamp on the notice. That is
more use than hiding them — someone can see akt exists, see it is shut, and check
back — and far more use than sending them to apply.

## Finding 4c — A closure notice can be years out of date

West London Mission's volunteer page reads:

> **COVID-19 update:** Please note that we are not taking on volunteers at the
> moment but please keep checking this page to see our update on WLM volunteering

Still live in 2026. The notice is not wrong about anything except its own age, and
there is no way to tell from the sentence itself how old it is — except that it
mentions COVID-19.

This is a third distinct failure mode, after akt's empty vacancy list:

| Pattern | What the page does | What to record |
|---|---|---|
| Bait (akt) | Prose describes roles; vacancy list empty | `closed`, low confidence |
| **Stale notice (WLM)** | **Says "not taking volunteers", notice years old** | **`closed`, and say the notice is old** |
| Silence (most) | Lists roles, never says if recruiting | `unknown` |

**Why it matters more than it looks.** A reader who sees "not recruiting" walks
away. If that notice is five years old they have been turned away by a page rather
than by a charity — and WLM's own page carries three named staff with direct phone
numbers, which look current. So the record is `closed` at confidence 0.5, with an
`unsupported_fields` entry saying the notice is headed COVID-19 and is worth a
phone call.

**For the pipeline.** `fetchpage.cms_updated()` already captures a CMS-published
"last updated" date where one exists. This is the case that makes it valuable: a
closure notice on a page last touched in 2021 should be weighted differently from
one on a page updated last week. Worth wiring into the confidence calculation
rather than leaving as metadata.

## Finding 4d — Hands-on volunteering can sit behind a corporate paywall

Two of the largest day centres in this set reserve their front-line volunteering
for companies that pay them.

**The Connection at St Martin's** — Europe's largest homeless day centre, over a
hundred people a day — lists exactly **one** opportunity open to an individual:
helping at fundraising events. Catering, artistic activities and Christmas are
corporate only, and the page says why: *"We reserve these opportunities for our
financial partners as part of their partnership with us."* 627 corporate
volunteers worked the day centre last year.

**The Passage** is the same shape: *"all our volunteering opportunities are part of
these packages and we are unable to accommodate requests for one-off volunteering
days."*

This is not a criticism. Managing volunteers costs staff time, and a partnership
that funds the service while supplying the labour is a rational answer. But it is
**material to a reader**, and invisible unless someone says it. A person who wants
to serve lunch at the busiest day centre in Europe cannot, unless their employer
writes a cheque.

**Recorded without a new enum.** `eligibility`, added for Women at the Well,
carries it exactly: `["Companies that are financial partners of the charity"]`
alongside `who_can_apply: "team_only"`. The notice prints **Only for: Companies
that are financial partners**, which is the honest version of what a reader needs
to know before they email.

**It is not universal, though.** Single Homeless Project — larger than either, over
10,000 Londoners a year — says the opposite: *"There are many opportunities for
individuals or groups to support us, either on a one-off or regular basis."* Its
Peer Mentor programme is open to any Londoner who meets the eligibility, and its
skills-based volunteering takes individuals and teams alike.

So the pattern is a choice each charity makes, not a consequence of size. Worth
tracking across the remaining organisations: if it clusters among the large
central-London day centres, the paper's most useful function for an individual may
be steering them towards the charities where the door is genuinely open.

## Finding 4e — Third-party volunteering portals are richer and less reliable

Twice now the only place with real detail about a role has been a platform the
charity does not control.

**Ace of Clubs.** Their own page says little; **Lambeth Council's volunteer
portal** gives the shift as 9.30am to 3pm, Monday to Friday. The detail looks
current and is almost certainly right.

**Thames Reach.** Their own page names no roles at all, pointing instead at a
vacancies list. **The GLA's Team London platform** carries a detailed BSL support
role at Brent Reach — one-day core training, safeguarding and boundaries, travel
paid up to £10, £5 towards lunch over five hours. It also refers to *"lock down
times"* and a *"COVID risk assessment"*, which dates it to 2020 or 2021.

**Why this matters for the pipeline.** These portals are exactly what a search
surfaces first, because they are better structured than the charities' own pages.
They are also where listings go to die: a charity updates its own site and forgets
the copy it posted on a council portal five years ago.

**How it is handled here.** `source_url` records where a fact actually came from,
not where the reader should apply. Ace of Clubs' shift times point at the Lambeth
portal, so when the weekly check reads aceofclubs.org.uk and never finds them it
will honestly downgrade rather than assume. Thames Reach's training and expenses
sit in `unsupported_fields` with a note naming the source and its age.

**A rule for extraction.** The pipeline only ever reads the charity's own
`volunteer_url`, so it will never see these portals — which is the right default.
The corollary is that a human adding detail from a portal must record the source,
or the weekly check will silently treat a five-year-old third-party claim as
verified first-party fact.

## Finding 4f — Some volunteering is only open to students

`pipeline/seed.py` flagged New Horizon Youth Centre's URL as pointing at a paid
jobs page. That was right, and the reason is more interesting than the flag.

Their get-involved page is a jobs page **because their volunteering runs as
student placements**:

> You must be able to demonstrate valid enrolment at a UK or EU higher level
> institution (i.e. University level or above) and we can only offer placements to
> students aged 18 or over.

The actual role descriptions — kitchen, ESOL tutor, sports assistant — are on
**UCL's student volunteering platform**, not on New Horizon's site at all. Third
time a third-party portal has held the detail (see Finding 4e), and the second
time it has been a university rather than a council.

**Why it matters.** A reader who is not a student cannot volunteer here, and
nothing on the charity's own volunteering route says so until you reach a
paragraph about placements. The `eligibility` field carries it:
`["Students enrolled at a UK or EU university, aged 18 or over"]`, so the notice
prints **Only for: students enrolled at a UK or EU university** before anyone
spends time on it.

**For the pipeline.** This is the case where `url_specificity: "org_homepage"` and
the seeded-URL flags earn their keep. A landing page that is really a jobs page
will yield paid roles unless something stops it, and the build invariant that
refuses a homepage-only link at high confidence is the backstop.

## Finding 4g — Two more of the 32 place no notices at all

`seed.py` excluded StreetLink and Homeless Link up front, by judgement. Reading all
32 found two more, by evidence.

**Streets of London** is a grant-giving charity. Its volunteer page does not list
roles; it sends you elsewhere, and does so rather well:

> You can visit Homeless Link and search for charities in your area... there are at
> least 150 different homelessness organisations in London alone, so don't hesitate
> to try several!

**Cardboard Citizens** is a theatre company whose members are people who have
experienced homelessness. Its get-involved route is sponsored events — The Big
Tramp is an all-night walk with a £39 entry fee. Paying to take part in a fundraiser
is not volunteering, and listing it as such would misdescribe both.

**Recorded with `link_status: "link_only"`**, which the schema has had since v0.2
for precisely this. Both stay in scope at 32; they simply never appear in a column.
No new field, no exclusion, no empty pages.

**It also exposed a wrong sentence on every page.** The publisher's notice read
*"30 of 32 charities read so far"*, which implied two were unread. All 32 have now
been read; two place nothing. It now reads *"30 of 32 charities place notices
here"* — a different claim, and the true one.

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
