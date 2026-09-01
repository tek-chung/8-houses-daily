# The 8 Houses Daily — product specification

**Version** 0.3
**Date** 26 August 2026
**Status** Built and tested. Not launched. Blocked on data, not code.
**Supersedes** v0.2 (24 August 2026), v0.1, and `eight-houses-community-preview.html`

---

## 0. What changed since v0.2, and why it matters

v0.2 was written before anything was built. Building it overturned nine things in
that document. They are listed here rather than buried, because a spec that
quietly absorbs its own corrections teaches nobody anything.

| v0.2 said | Reality | Where |
|---|---|---|
| Records are roles, not charities | Held. The single best decision in the project. | §5 |
| Screening tolerance is "the facet nobody else offers" | **Wrong.** No charity publishes it. 9 of 11 roles are `unknown`. Unusable as a filter. | §6.1 |
| Corporate teams are "a Phase 4 concern at most" | **Wrong.** One charity takes *no individuals at all*. It is a safety flag, not a segment. | §6.2 |
| Commitment is the primary axis | Held, but it conflates frequency with depth. | §6.4 |
| Astro for the site build | Python. One toolchain beats two for one maintainer. | §11 |
| Pre-render one- and two-blank combinations | Only those with results. Empty combinations are thin content. | §11.3 |
| Night-navy and lamplight | A newspaper. Roles *are* classified advertisements. | §9 |
| A borough tile cartogram | Real ONS/OS geography. Tek asked, and it is better. | §10 |
| The freshness pipeline as specified | Change detection was broken before it ever ran. | §12.1 |

Two further things v0.2 did not think about at all: what happens when a page is
silent (§6.1), and that a test suite which cannot execute the page is blind to an
entire class of failure (§13.2).

---

## 1. Summary

A free newspaper of volunteering notices from London homelessness charities. It
lists **posts, not organisations**, because you cannot volunteer for an
organisation — you volunteer for a particular morning, in a particular building,
having satisfied whatever they ask first. Every notice links to the charity's own
page. No applications, no accounts, no vetting, no advertising.

Everything is static. There is no server, no database, and no public endpoint that
can be abused or run up a bill. Running cost is the domain registration.

---

## 2. Assumptions

- **A1.** The audience has already decided to help. Explaining homelessness to them
  wastes the fold.
- **A2.** The site never processes applications, holds accounts, or takes money.
- **A3.** Success is a click through to a charity's own page. What happens after is
  not observable and must not be pretended otherwise.
- **A4.** One maintainer, near-zero budget. **This has veto power.** It removed the
  runtime matcher in v0.2 and the second toolchain in v0.3.
- **A5.** Scope is the 32 organisations in `pipeline/seed.py`. Two of the original
  34 were excluded as not being sources of volunteering roles at all.

---

## 3. Goals and non-goals

**Goals.** A first-time reader reaches a shortlist in under a minute without
learning a taxonomy. Every notice carries what actually decides whether you can
take it. Data stays accurate without manual upkeep, and the site is visibly honest
about how fresh it is. Every view is a shareable, indexable URL. Someone who will
not volunteer still leaves having done something.

**Non-goals.** Applications. Vetting. Accounts. Anywhere but London. Any runtime
intelligence — no live model calls, no personalisation, nothing that cannot be
explained from the visible constraints.

---

## 4. Measures

| Measure | Target |
|---|---|
| Sessions with a click through to a charity | ≥ 35% |
| Median seconds to a result set of ≤ 8 notices | ≤ 45 |
| Sessions reaching any result set | ≥ 70% |
| Sessions filling ≥ 2 of the 3 coupon blanks | ≥ 50% |
| Apply URLs returning 200 | ≥ 98% |
| Median days since last successful check | ≤ 7 |

None of these measure whether anyone volunteered. That is not observable from
here, and a proxy dressed up as the real thing would be worse than admitting it.

---

## 5. The data model

**Roles, not charities.** This is the spine. A charity-level record cannot answer
"can I do this on Saturday", so the PoC's facets matched two-thirds of its own
corpus and discriminated nothing. 32 organisations yield perhaps 160 role records.

Two record types, JSON in the repo, one file per organisation. Full schema in
`pipeline/schema.py`. Four fields exist only because real pages forced them:

- **`who_can_apply`** — `individual | team_only | either | unknown`. The Whitechapel
  Mission takes no individuals. Listing its roles without saying so would send
  people to be turned away, which is the exact harm this site exists to prevent.
- **`screening.dbs: "required_unspecified"`** — a check is required but the page does
  not say which level. Collapsing that to `unknown` throws away the actionable
  half: "you will definitely need one" is very different advice from "we don't
  know if you need one".
- **`location_type: "own_home"`** — Nightstop hosting happens at the volunteer's
  address. Travel time is meaningless and no area filter may exclude it. `remote`
  would match correctly and describe it absurdly.
- **`activity: "varies"`** — a rotating calendar, not a fixed role. Picking one
  activity would be fabrication. These appear when no activity filter is set and
  are excluded when one is, because we never promise a match we cannot support.

---

## 6. What the build taught us about the data

### 6.1 Charities do not publish their screening requirements

Across 11 verified roles: `dbs` is `unknown` nine times and
`required_unspecified` twice. **Not one page states a DBS level, a minimum age or
a references policy.**

v0.2 called screening tolerance "the facet nobody else offers". On observational
data it is silent almost always, which makes it the PoC's failure reached from the
opposite direction — a facet that cannot discriminate.

**Resolved as follows.** Not a filter. A displayed field reading "Not stated", plus
**one** note above a column of notices explaining the pattern, printed only where
the gap is actually common. The long phrasing on every notice turned six words
into wallpaper: `/all/` said "worth asking" nine times. Explaining the pattern once
tells the reader something the individual notices cannot.

**Still open:** the four questions in `docs/launch-email.md` are the only route to
real data here, and they cost nothing to attach to an email being sent anyway.

### 6.2 "Teams only" is a safety flag, not a segment

The Whitechapel Mission accepts corporate and community groups, booked by diary,
and no individuals. On a role page this fact appears **second, directly after the
lead** — before the screening conditions — because it decides whether the reader
can apply at all. A test asserts that ordering.

### 6.3 Two of the 34 are not sources of roles

StreetLink is a referral service and belongs in the five-minute actions. Homeless
Link is a sector job board that aggregates other charities' roles; listing it would
duplicate our own function, so it belongs in `/about/` and in the decay banner as
an onward pointer. Four more have URLs pointing at homepages, a paid-jobs page, or
a third-party platform — which would mean the freshness check watching the wrong
site. All recorded in `pipeline/seed.py` with reasons.

### 6.4 `commitment` conflates frequency with depth — unresolved

Nightstop hosting exposed it. The shifts are entirely flexible; *becoming* a host
means a home visit, a DBS check and safeguarding training. Low frequency, high
depth. A weekly kitchen shift is the reverse.

`commitment: long_term` currently routes hosting to the third door, justified by
§7.1's own wording, and `specific_times` carries the flexibility. If that starts
giving wrong answers the fix is a separate `depth` field, not more commitment
values. Two organisations is not enough evidence to restructure a primary axis.

---

## 7. Interaction

### 7.1 Three ways, first

The front page leads with the headline, then three calls to action — one day, every
week or so, something bigger — each ending in a button. Nothing comes between the
headline and the first button; a test asserts the gap contains no text at all. A
kicker and a standfirst both lived there and both were cut.

Everything secondary follows: the publisher's notice, the five-minute actions, and
the lookup field. The lookup was in the masthead, above everything, serving the
minority who already know the charity they want.

### 7.2 The form of enquiry

The sentence builder from v0.2, set as a printed coupon. Below 640px it is labelled
rows with a dotted rule to fill in, because inline dropdowns inside a sentence wrap
into nonsense on a phone. Above that the rows collapse into the prose sentence.
Filling a slot inks it red — completion is rewarded, not merely recorded.

Per-blank reset happens by choosing the placeholder in the blank's own dropdown
rather than by a separate × button. Same control, no extra UI.

### 7.3 Notices are classified advertisements

Roles *are* small ads. "WANTED: kitchen volunteer, Southwark, Saturdays, apply
within" is the format newspapers used for exactly this content for two centuries.
Boxed and ruled with the particulars in a definition list, because that is what
they are: labelled facts, not prose.

**Stamps mark exceptions only.** `TEAMS ONLY`, `CLOSED FOR THE SEASON`, `RECRUITING
NOT STATED`. There is no `RECRUITING NOW` stamp — that is the default, and stamping
it would flatten the signal. On a phone stamps sit in the flow; from 700px they are
struck diagonally across the ad, because a struck stamp on a narrow card covers the
particulars.

### 7.4 Notice pages are articles, composed from the record

A card with a bigger headline is not an article. The body is generated from the
record's own fields — five or six paragraphs, every sentence a restatement of
something we hold, and where a field is empty the sentence says so rather than
being quietly dropped. That is the difference between reporting and inventing.

Reading the output caught five defects a passing build had hidden: a doubled full
stop, a missing space after one, "takes about 14 hours at a time" for an overnight
stay, a borough list where the names contain "and" so the commas read as one long
name, and the teams-only fact appearing fifth. Tests now sweep every article for
each of those.

### 7.5 `/help/` deliberately breaks the design

No drop caps, no "Situations Vacant", no kicker, no columns, no lookup field, no
data payload. A double-ruled public notice with plain type, three services, 999 for
emergencies, and a section saying flatly that we cannot help and they should use
the others. The period voice is charming for a volunteer and would be actively
wrong for someone sleeping rough. A test fails if any of the decoration leaks in.

---

## 8. URLs

Every meaningful view is a real path. Roughly 45 pages today, ~500 at full data.

```
/                       /one-day/            /weekly/hackney/
/all/                   /weekly/             /one-day/cooking-serving/
/role/{id}/             /charity/{id}/       /near/{district}/
/help/  /about/  /data/  /five-minutes/
```

**Only combinations with results are emitted.** v0.2 said one- and two-blank
combinations; real data shows that generating every combination produces hundreds
of empty pages — thin content, an SEO liability, and a promise the site cannot
keep. Three-blank states resolve client-side and carry `noindex`.

Borough pages disclose what they are padded with: `/one-day/tower-hamlets/` shows
four notices of which two are London-wide, and says so, because the title promises
a borough.

---

## 9. Design

A newspaper. Newsprint cream, warm near-black ink, one spot red. **Three tiers of
ink, not four** — papers have ink and less ink, and hierarchy comes from size,
weight, caps and rules. Fraunces for display, Literata for body, Archivo for
labels, all chosen for legibility at the sizes actually used.

Engravings rather than photography: a steaming pot, a guttering lamp, a swaying
coat, a lit fanlight, keyed to each notice's activity, looping gently and holding
still under `prefers-reduced-motion`. §16 forbids poverty tourism, and stock
imagery of people sleeping rough would be exactly that. **A test asserts no `<img>`
tag exists anywhere on the site.**

Mobile-first: base rules target 360px and wider layouts are additive, at 480, 640,
700 and 900. Two bugs found by measuring rather than assuming — iOS Safari zooms
the viewport whenever a focused control is under 16px, and rotated stamps scroll a
phone sideways without `overflow-x: hidden`.

Every palette value is verified to WCAG AA on every surface it is used against;
worst ratio 5.10:1, re-derived from the stylesheet by a test. An earlier build
shipped a token at 3.51:1 while the spec called AA non-negotiable.

---

## 10. The map

Real ONS/OS borough outlines with the Thames threaded through them. Generated by
`site/tools/build_map.py`, committed so the build needs no network.

**The Thames comes from the boroughs.** In the source file boroughs meet along the
middle of the channel, so the seam between north-bank and south-bank boroughs *is*
the river — at exactly the precision of the shapes it must align with. A separate
river dataset would be a second set of rounding errors that would not sit on the
banks. A test checks every riverside borough against its real bank, because north
or south of the river is how a Londoner places a borough.

**No text inside the SVG.** Counts are HTML badges positioned by percentage. An
earlier version put labels inside a scaled viewBox and they rendered at 43px,
because font-size there resolves in user units. Badges are separated by an
iterative pass with leader lines and a count-only fallback, stress-tested at twenty
badges in one corner.

**The shapes are decorative; the chips are the control.** Thirty-three focusable
paths would put thirty-three duplicate tab stops in front of a keyboard user. On a
phone there are only chips.

Attribution — both Crown copyright statements — is required by the OGL and the OS
OpenData Licence and prints under the map.

**Travel-time reach is still blocked on data.** `pipeline/reach.py` is written and
refuses to produce an empty index: no role has `coords`.

---

## 11. Architecture

Python throughout. v0.2 named Astro; one maintainer carrying two toolchains means
two dependency trees to rot, two CI setups and two things to relearn. `site/build.py`
is one file with no dependencies emitting static HTML — which is what Astro would
have produced.

Every page renders server-side. With JavaScript off, all notices are visible, all
links work, every pre-rendered URL is indexable. JavaScript makes filtering instant
and adds the map.

**One card renderer.** There were two — Python and JavaScript — and they had
drifted to different class names and different copy. `app.js` now filters the
server-rendered notices by `data-id`; changing the commitment navigates to the
pre-rendered page, because a results page holds only its own notices.

### 11.1 Build invariants

`site/build.py` refuses to build — exit 2, nothing written — on any of ten
conditions, each demonstrated by deliberately breaking the data:

a role pointing at an organisation that is not in the build · an opted-out charity
still in the build · `dbs: "none"` without a verified source · nothing to link to,
so the button would lie · a homepage-only link at high confidence · duplicate role
ids · `seasonal_closed` with no window · a minimum term on a one-off role · an
`apply_url` on a different domain from the charity · `status: open` where
provenance says the source does not support it.

A promise enforced by the build is worth more than one written in a document.

---

## 12. The freshness pipeline

Weekly GitHub Action. Fetch, isolate main content, follow role sub-pages, extract,
verify, gate, publish or open a pull request. Full detail in `pipeline/README.md`.

### 12.1 Change detection was broken before it ever ran

Charity CMS pages are 76–95% boilerplate. Glass Door's volunteering page returned
roughly 6,000 tokens of navigation, tag cloud and rotating news sidebar around
about 200 tokens of role content.

Two failures followed. The model would have seen "Sleep Out" and "London Marathon"
in the navigation and could invent roles from them. And — worse — the sidebar
rotates whenever the charity publishes news, so **every page would have looked
changed every week**: all 32 re-extracted, the review queue permanently full, the
maintainer giving up inside a month, and the decay banner firing on a system that
was technically working the whole time. That invalidated the phase's entire cost
model.

Fixed by isolating main content before hashing, and following role links one level
down because landing pages carry no role detail. The load-bearing test is
`test_hash_stable_when_only_sidebar_changes`.

### 12.2 Confidence is derived, not self-reported

The model is never asked how confident it is — self-reported confidence is weakly
calibrated and tends to be cheerful. A second pass sees each critical claim beside
the page and judges whether the page supports it; silence is not support.
Unsupported claims are forced to `unknown` **before the gate sees them**, and
confidence is `supported / checked`. A failed verifier scores 0.0, because a broken
verifier is not permission to publish.

### 12.3 The gate

Pure, no I/O, no clock, so it can be tested exhaustively. Fails closed: anything
unclassifiable goes to review. `screening.*`, `status` and `next_intake` go to
review regardless of confidence — those are the claims that waste someone's day.
28 tests, including one that fails if a field is added to `CRITICAL_FIELDS` but
never actually compared.

### 12.4 Copyright is enforced, not requested

The prompt asks for paraphrase; `extract.py` checks. Any verbatim run of eight or
more words shared with the source fails the whole extraction.

### 12.5 Designed decay

At 21 days without a successful check, notices stop printing anything we cannot
stand behind and keep only the link. At 60 days a banner says the paper is not
being kept up and points elsewhere. The likeliest failure is the maintainer getting
busy, so it is built in rather than hoped for.

---

## 13. Testing

145 tests: 42 on the pipeline, 103 on the site.

### 13.1 Grouped by who breaks

Honesty (a reader is misled about what we know) · reachability · accessibility ·
SEO · responsive · engravings · readability · concision · map · badge placement.

### 13.2 A Python suite cannot execute the page

That blind spot hid two serious bugs at once. `toggleBlank()` dereferenced a
wrapper id the newspaper coupon does not have and threw on every results page,
which meant **the map never drew at all** — the page merely looked empty. Behind
that exception sat the second card renderer, which the fix then let overwrite all
eleven server-rendered notices.

Neither was visible to any test. `site/js/smoke.js` now loads every built page in
jsdom and reports what the console would show, plus borough counts, badge counts
and coupon state. My first harness reported **zero errors on a visibly broken
page**, because jsdom routes uncaught exceptions through a VirtualConsole rather
than `window.onerror`.

### 13.3 Tests that exist because something was silently absent

`plate()`, four engravings, their CSS and their keyframes were all written and
wired to nothing. Every page built, all 89 tests passed, and the signature element
of the design was **absent from the site**. A suite that checks structure has no
opinion about whether a decoration exists.

---

## 14. Where it stands

| Phase | State |
|---|---|
| 0 — data | **5 of 32 organisations, 11 roles. The bottleneck.** |
| 1 — site | Built. 45 pages, tested, no console errors. |
| 2 — map | Geography done. Travel-time reach blocked on `coords`. |
| 3 — pipeline | Built and tested. **Never run against a live page.** |
| 4 — later | Seasonality, corporate days, follow-up survey. |

### The critical path

1. **`python pipeline/census.py`** — no API key, about two minutes. Answers whether
   the remaining 27 pages can be read at all, and distinguishes `client_rendered`
   (needs a different URL or a headless browser) from `thin` (real prose, no role
   detail — link-only permanently). Those lead to opposite decisions.
2. **Read `docs/census.md`** before extracting anything. If most pages are
   client-rendered, that is a different project and worth knowing before publishing
   a hundred unreliable records.
3. **Run the extraction.** Everything lands in a review PR; the first will be large
   and that is correct for a cold start.
4. **Send the launch email** (`docs/launch-email.md`) with the four screening
   questions attached.

### Before any of it

- `https://8houses.co.uk/bot` must exist. It is the contact URL in the crawler's
  user agent, and a charity that wants us to stop needs somewhere to go.
- Set `BASE_URL` in `site/build.py`; sitemap and canonicals depend on it.
- Set a spend limit in the Anthropic console. Under £1/month realistically, but a
  limit turns a runaway loop into a failed job rather than a bill.

---

## 15. Open questions

**Q1. Does this carry the 8 Houses name?** Answered in practice — the contact
address and the masthead are both 8 Houses — but not deliberately. A consumer
PropTech brand on a homelessness signpost invites a cause-washing reading however
sincere it is, and ties a commercial reputation to accuracy on safeguarding-adjacent
facts. Worth a decision rather than a default.

**Q2. London only, or London first?** The architecture is city-agnostic; the copy,
the masthead and the URL structure are not.

**Q3. Observational, or charity relationships?** §6.1 is the strongest argument yet
for asking. The launch email is a soft opening either way.

**Q4. Who reads the weekly pull request?** If only you, the decay mechanism is
doing real work.

---

## 16. Legal, editorial, safeguarding

We do not vet — stated in the colophon on every page. We do not host applications;
all screening sits with the charity, where the duty of care belongs. Charity
numbers are shown and linked so anyone can check the register. Corrections go to
one address with a 72-hour target, and an opt-out removes the organisation from the
build rather than hiding the card — enforced by a build invariant.

No poverty tourism, enforced by a test. Boundary data carries its required Crown
copyright statements. `/help/` exists so that anyone arriving in need rather than
offering is routed to real services within one click; it is the one duty of care
that cannot be delegated.

---

## Appendix — decisions not to revisit

| Decided against | Because |
|---|---|
| A free-text natural-language matcher | Hides the system's capability, needs a runtime endpoint, not indexable |
| An LLM re-rank at request time | Templated rationales read better and cost nothing |
| Charity-level records | You volunteer for a role. This is what made every PoC facet useless |
| A runtime isochrone API | Precomputed reach is free, faster, offline-capable, keyless |
| Astro | Two toolchains for one maintainer |
| A tile cartogram | Tek asked for real geography, and it is better |
| Blackletter | Beautiful at 3em, muddy at 30px, and a masthead is the most-read type there is |
| SVG text inside a scaled viewBox | font-size resolves in user units. 5 units rendered at 43px |
| A screening *filter* | The source data is silent almost always |
| A second river dataset | The borough seam is the river, at the precision it must match |
