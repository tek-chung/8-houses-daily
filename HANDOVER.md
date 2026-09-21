# The 8 Houses Daily — handover

**For:** an assistant or collaborator picking this project up with no prior context.
**Written:** 2 September 2026, at the end of the design-and-build phase.
**Status:** built and tested, not launched, blocked on data rather than code.

Read this first, then `london-volunteering-spec-v0.3.md` for the reasoning behind
every decision. This document is the operational briefing; the spec is the product
argument. Where they disagree, the repository wins — it is the source of truth, and
claims about it should be checked against the code rather than recalled.

---

## 1. What this is, in one paragraph

A free newspaper of volunteering notices from London homelessness charities. It
lists **posts, not organisations**, because you cannot volunteer for an
organisation — you volunteer for a particular morning, in a particular building,
having satisfied whatever they ask first. Every notice links to the charity's own
page. There are no applications, no accounts, no vetting and no advertising.
Everything is static: no server, no database, no runtime API. Running cost is the
domain.

It replaced an earlier proof of concept called "8 Houses Community", which was a
filterable directory of 34 charity cards. That version is dead. If anything you
read describes charity-level records, a three-bucket taxonomy, a night-navy
palette, amber accents or Astro, it predates the rebuild.

---

## 2. Facts you can rely on

| | |
|---|---|
| Name | The 8 Houses Daily |
| Live at | `https://daily.8houses.co.uk` |
| Repo | `github.com/tek-chung/8-houses-daily` |
| Local | `C:\Users\tekka\8houses\Code\homelessness-portal` |
| Hosting | Cloudflare Workers, assets-only, custom domain on an owned zone |
| Stack | Python 3.12, standard library only. Node solely for browser tests |
| Site build | `python site/build.py` → `dist/`, 197 pages |
| Tests | 162 — 42 pipeline, 120 site |
| Data | **All 32 read. 75 roles across 30; two place none.** |
| Build invariants | 12 conditions that refuse to publish |
| Spec | `london-volunteering-spec-v0.3.md` |

---

## 3. Where it stands

| Phase | State |
|---|---|
| 0 — data | **Complete.** All 32 read; 75 roles across 30 |
| 1 — site | Built. 197 pages, 162 tests, no console errors |
| 2 — map | Real ONS/OS geography done. Travel-time reach blocked: no `coords` |
| 3 — pipeline | Built and tested. **Never run against a live charity page** |
| 4 — later | Seasonality, corporate days, follow-up survey |

Phase 0 was the bottleneck through two spec versions. Reading all 32 changed the
product as much as it filled it — five schema additions forced by real pages, and
three bugs found in code already called finished.

### The critical path

1. **Deploy.** The crawler's user agent points at the paper's own `/bot/` page,
   which must resolve before the crawler visits any charity.
2. **`py pipeline\run.py --dry-run`.** The pipeline has never met a live charity
   page. It now has 75 hand-written records to diff against, which is a much
   better first run than a cold start.
3. **Send the launch email** with the four screening questions.
4. **Populate `coords`** to unblock `pipeline/reach.py`.

## 4. The repository

```
README.md                        quickstart, structure, the three pre-launch musts
london-volunteering-spec-v0.3.md the spec. §0 lists what v0.2 got wrong
london-volunteering-spec-v0.2.md kept for the §0 comparison only
wrangler.jsonc                   assets-only Worker config
.python-version                  3.12, honoured by Cloudflare's build image
package.json                     jsdom and wrangler; no runtime dependencies

site/build.py                    the static site generator. One file, pure stdlib
site/static/app.css              the whole design system
site/static/app.js               coupon, filtering, map, typeahead
site/tools/build_map.py          ONS/OS boundaries → data/london-map.json
site/test_build.py               114 tests on the built site
site/js/smoke.js                 jsdom harness: runs each page, reports the console
site/js/labels.js                map label-placement stress cases
site/README.md                   design system, mobile, map, tests

pipeline/census.py               "can we read these pages?" No API key. Run first
pipeline/seed.py                 creates org stubs. Already run
pipeline/fetchpage.py            robots, conditional GET, main-content isolation
pipeline/extract.py              model call, verification pass, copyright guard
pipeline/gate.py                 what may auto-publish. Safety-critical, pure
pipeline/schema.py               the data model
pipeline/decay.py                freshness state → data/freshness.json
pipeline/reach.py                travel-time precompute. Blocked on coords
pipeline/run.py                  orchestrator
pipeline/test_gate.py            28 tests
pipeline/test_fetch.py           14 tests on content isolation
pipeline/README.md               pipeline operations

data/orgs/*.json                 32 files, one per organisation
data/london-map.json             generated, committed so the build needs no network
docs/hosting.md                  deployment
docs/scrapability.md             what reading real charity pages taught us
docs/launch-email.md             the email to send all 32
.github/workflows/refresh.yml    weekly freshness check
.github/workflows/deploy.yml     GitHub Pages alternative, unused
```

`dist/` is generated. Never edit it, never commit it.

---

## 5. The data model

**Roles, not charities.** This is the spine and the single best decision in the
project. A charity-level record cannot answer "can I do this on Saturday", which is
why the PoC's facets matched two-thirds of its own corpus and discriminated
nothing. 32 organisations should yield perhaps 160 role records.

Two record types, JSON in the repo, one file per organisation. Full schema in
`pipeline/schema.py`. Four fields exist only because real pages forced them:

- **`who_can_apply`** — `individual | team_only | either | unknown`. The
  Whitechapel Mission takes no individuals at all. Listing its roles without
  saying so would send people to be turned away, which is the exact harm the site
  exists to prevent.
- **`screening.dbs: "required_unspecified"`** — a check is required but the page
  does not say which level. Collapsing that to `unknown` throws away the actionable
  half.
- **`location_type: "own_home"`** — Nightstop hosting happens at the volunteer's
  address. Travel time is meaningless and no area filter may exclude it.
- **`activity: "varies"`** — a rotating calendar, not a fixed role. Shown when no
  activity filter is set, excluded when one is.

---

## 6. The five findings that shaped everything

These came out of reading real charity pages. They are the reason the product looks
the way it does, and re-deriving them costs weeks.

**1. Charities do not publish their screening requirements.** Across 11 verified
roles, `dbs` is `unknown` nine times and `required_unspecified` twice. Not one page
states a DBS level, a minimum age or a references policy. v0.2 called screening
tolerance "the facet nobody else offers"; on observational data it is silent almost
always, making it a facet that cannot discriminate. It is now a displayed field
reading "Not stated", plus one note above a column explaining the pattern. Printing
the long form on every notice turned six words into wallpaper — `/all/` said "worth
asking" nine times.

**2. "Teams only" is a safety flag, not a segment.** On a role page this fact
appears second, directly after the lead, before the screening conditions, because
it decides whether the reader can apply at all. A test asserts that ordering.

**3. Change detection was broken before it ever ran.** Charity CMS pages are 76–95%
boilerplate. Glass Door's volunteering page returned roughly 6,000 tokens of
navigation and a rotating news sidebar around about 200 tokens of role content. The
sidebar rotates whenever they publish news — so every page would have looked
changed every week, all 32 re-extracted, the review queue permanently full, and the
maintainer giving up inside a month. Fixed by isolating main content before hashing.
The load-bearing test is `test_hash_stable_when_only_sidebar_changes`.

**4. Role detail lives on sub-pages.** The volunteering landing page is usually a
signpost. Everything useful about Glass Door's shelter role — 21 venues, 6pm–9pm,
November to April, currently closed — is one click down.

**5. `commitment` conflates frequency with depth. Unresolved.** Nightstop hosting
is low-frequency and high-depth: flexible shifts, but a home visit, a DBS check and
safeguarding training to become a host. A weekly kitchen shift is the reverse. If
this starts giving wrong answers the fix is a separate `depth` field, not more
commitment values. Two organisations is not enough evidence to restructure a
primary axis.

---

## 7. Design

A newspaper, because volunteering roles **are** classified advertisements. "WANTED:
kitchen volunteer, Southwark, Saturdays, apply within" is the format papers used
for exactly this content for two centuries.

**Palette.** Newsprint cream `#f2ede1`, boxed surfaces `#e8e1d1`, warm near-black
ink `#17130f`, secondary `#453c33`, labels `#5a5044`, one spot red `#9e2b23`,
hairlines `#b8ae98`. **Three tiers of ink, not four** — papers have ink and less
ink, and hierarchy comes from size, weight, caps and rules. Verified to WCAG AA on
every surface; worst ratio 5.10:1, re-derived from the stylesheet by a test.

**Type.** Fraunces for display, Literata for body, Archivo for labels. All chosen
for legibility at the sizes actually used. Bodoni Moda's hairlines vanished below
24px; EB Garamond's low x-height made 17px read like 14. Blackletter is gone —
beautiful at 3em, muddy at 30px, and a masthead is the most-read type there is.
Nothing is set below 11px and small caps are never tracked past 0.14em.

**Stamps mark exceptions only.** `TEAMS ONLY`, `CLOSED FOR THE SEASON`, `RECRUITING
NOT STATED`. There is no `RECRUITING NOW` stamp, because that is the default and
stamping it would flatten the signal.

**Engravings, not photography.** Hand-drawn SVG line art keyed to each role's
activity — a steaming pot, a guttering lamp, a swaying coat, a lit fanlight. They
loop gently and hold still under `prefers-reduced-motion`. §16 forbids poverty
tourism and stock imagery of people sleeping rough would be exactly that. **A test
asserts no `<img>` tag exists anywhere on the site.**

**Mobile-first.** Base rules target 360px; wider layouts are additive at 480, 640,
700 and 900. Two bugs found by measuring: iOS Safari zooms the viewport whenever a
focused control is under 16px, and rotated stamps scroll a phone sideways without
`overflow-x: hidden`.

**`/help/` deliberately breaks the design.** No drop caps, no "Situations Vacant",
no search box, no data payload — a double-ruled public notice with plain type,
three services and 999 for emergencies. The period voice is charming for a
volunteer and would be actively wrong for someone sleeping rough. A test fails if
any of the decoration leaks in.

---

## 8. Interaction

**Three doors, first.** The front page leads with the headline, then three calls to
action — one day, every week or so, something bigger — each ending in a button.
Nothing comes between the headline and the first button; a test asserts the gap
contains no text at all. A kicker and a standfirst both lived there and both were
cut. The front page is 268 words and there is a test that fails above 320.

**The form of enquiry.** The sentence builder set as a printed coupon. Below 640px
it is labelled rows with a dotted rule to fill in, because inline dropdowns inside
a sentence wrap into nonsense on a phone. Filling a slot inks it red. Per-blank
reset happens by choosing the placeholder in the blank's own dropdown.

**The map.** Real ONS/OS borough outlines with the Thames threaded through them.
The Thames comes from the boroughs themselves: in the source file they meet along
the middle of the channel, so the seam between north-bank and south-bank boroughs
*is* the river, at exactly the precision of the shapes it must align with. A test
samples the path and checks every riverside borough against its real bank. No text
inside the SVG — counts are HTML badges positioned by percentage, separated by an
iterative pass with leader lines. The shapes are `aria-hidden`; the chips beneath
are the control, because 33 focusable paths would be 33 duplicate tab stops. On a
phone there are only chips.

**Notice pages are articles composed from the record.** Five or six paragraphs,
every sentence a restatement of something the record holds, and where a field is
empty the sentence says so rather than being quietly dropped. That is the
difference between reporting and inventing.

---

## 9. The pipeline

Weekly GitHub Action. Fetch, isolate main content, follow role sub-pages, extract,
verify, gate, publish or open a pull request.

**Confidence is derived, not self-reported.** The model is never asked how
confident it is — self-reported confidence is weakly calibrated and tends to be
cheerful. A second pass sees each critical claim beside the page and judges whether
the page supports it; silence is not support. Unsupported claims are forced to
`unknown` before the gate sees them, and confidence is `supported / checked`. A
failed verifier scores 0.0.

**The gate is pure and fails closed.** No I/O, no clock, so it can be tested
exhaustively. `screening.*`, `status` and `next_intake` go to human review
regardless of confidence — those are the claims that waste someone's day. 28 tests,
including one that fails if a field is added to `CRITICAL_FIELDS` but never
compared.

**Copyright is enforced, not requested.** The prompt asks for paraphrase;
`extract.py` checks. Any verbatim run of eight or more words shared with the source
fails the whole extraction.

**Designed decay.** At 21 days without a successful check, notices stop printing
anything we cannot stand behind and keep only the link. At 60 days a banner says
the paper is not being kept up and points elsewhere. The likeliest failure is the
maintainer getting busy, so it is built in rather than hoped for.

**Cost:** under £1/month. Roughly 8 of 32 pages change weekly, at ~6k tokens each.
Conditional requests mean an unchanged page costs a 304.

---

## 10. Do not reopen these without new evidence

Each was decided against for a reason that still holds. The spec's Appendix records
them; this is the short form.

| Rejected | Because |
|---|---|
| A free-text natural-language matcher | Hides the system's capability so users under-specify; needs a runtime endpoint; not indexable |
| Any model call at request time | A model runs at build time only. No public endpoint that can be abused or run up a bill |
| An LLM re-rank at request time | Templated rationales read better down a column and cost nothing |
| Charity-level records | You volunteer for a role. This is what made every PoC facet useless |
| A runtime isochrone API | Precomputed reach is free, faster, offline-capable, keyless |
| Astro, or any JS framework | Two toolchains for one maintainer |
| A screening *filter* | The source data is silent almost always |
| A borough tile cartogram | Replaced by real geography at Tek's request, and it is better |
| Blackletter type | Muddy at 30px, and a masthead is the most-read type there is |
| SVG text inside a scaled viewBox | font-size resolves in user units. 5 units rendered at 43px |
| A second river dataset | The borough seam *is* the river, at the precision it must match |
| Committing `dist/` | Generated. If it appears in a diff, the build setup is wrong |

---

## 11. Working practices

**The repo is the source of truth.** Verify claims against the code rather than
describing from memory. Several confident descriptions in this project turned out
to be wrong about the code they described.

**Prefer adding a test to fixing a bug silently.** Tests are grouped by who breaks
if they fail: honesty, reachability, accessibility, SEO, responsive, engravings,
readability, concision, map, badge placement. Several exist because something was
*silently absent* — `plate()`, four engravings, their CSS and keyframes were all
written and wired to nothing. Every page built, all 89 tests passed, and the
signature element of the design was missing from the site. A suite that checks
structure has no opinion about whether a decoration exists.

**A Python suite cannot execute the page.** That blind spot hid two serious bugs at
once: a null dereference that threw on every results page and stopped the map
drawing, and behind it a second copy of the card markup that then overwrote all
eleven server-rendered notices. `site/js/smoke.js` loads every built page in jsdom
and reports what the console would show.

**Measure rather than assume.** The contrast failure, the boilerplate ratio, the
label overlaps, the river's accuracy and the front page's word count were all
found by counting, not looking.

**Never invent charity data.** Shift times, DBS requirements, minimum ages and
intake dates are facts about real organisations. Where a page is silent, the record
says so. Fabricating a plausible value is the one unrecoverable mistake here.

**Tek's preferences:** British English, straightforward answers, and a confidence
percentage at the end of substantive responses. He develops on Windows in
PowerShell — `py` not `python`, `$env:VAR = "x"` not `export`, backslash paths.
Two Windows-only bugs have already been fixed (locale-dependent file encoding, and
the glibc-only `%-d` strftime flag); both worked perfectly on the machine they were
written on, which is why they now have tests.

---

## 12. Open questions

**Q1. Does this carry the 8 Houses name?** Answered in practice — the domain and
masthead are both 8 Houses — but not deliberately. A consumer PropTech brand on a
homelessness signpost invites a cause-washing reading however sincere it is, and
ties a commercial reputation to accuracy on safeguarding-adjacent facts about other
organisations. Worth a decision rather than a default.

**Q2. London only, or London first?** The architecture is city-agnostic; the copy,
the masthead and the URL structure are not.

**Q3. Observational, or charity relationships?** Finding 1 is the strongest
argument yet for asking. The launch email is a soft opening either way.

**Q4. Who reads the weekly pull request?** If only Tek, the decay mechanism is
doing real work.

---

## 13. Legal, editorial, safeguarding

- **We do not vet.** Stated in the colophon on every page. Listing is not
  endorsement.
- **We do not host applications.** All screening sits with the charity, where the
  duty of care belongs.
- Charity numbers are shown and linked so anyone can check the register.
- An **opt-out removes the organisation from the build** rather than hiding the
  card, enforced by a build invariant.
- Corrections go to `tek@8houses.co.uk` with a 72-hour target.
- Boundary data carries both required Crown copyright statements — Open Government
  Licence plus the OS OpenData Licence — printed under the map.
- The crawler identifies itself as `SomewhereToHelpBot`, honours robots.txt, makes
  one request per second, and its user agent points at `/bot/`, a page the site
  builds itself explaining what it does and how to stop it.
- `/help/` exists so that anyone arriving in need rather than offering is routed to
  real services within one click. It is the one duty of care that cannot be
  delegated.

---

## 14. Things that will bite

**`SITE_URL` is invisible when wrong.** It feeds the sitemap, canonical tags and
Open Graph tags. Set it wrong and nothing looks broken — you simply do not rank.

**The site must be served from a domain root.** Every internal reference is
root-absolute. A subpath breaks all of them.

**The census must come before extraction.** Extraction produces *claims* that land
in a review PR and, if wrong, send someone across London for nothing. The census
tells you whether those claims can be grounded in anything, free, in two minutes.

**Regenerate the map after changing its tolerances.** `data/london-map.json` is
committed; a test compares its recorded settings against the code's constants.

**Two card renderers is a trap.** There were, and they drifted to different class
names and different copy. `app.js` now filters server-rendered notices by
`data-id`; `site/build.py`'s `card()` is the only renderer.
