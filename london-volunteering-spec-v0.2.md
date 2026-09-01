# London homelessness volunteering — product specification

**Version** 0.2 (draft for review)
**Date** 24 August 2026
**Status** Pre-build. Direction agreed. Open questions in §18 need answers before Phase 1 starts.
**Supersedes** v0.1 (24 August 2026) · `eight-houses-community-preview.html` (PoC)

### Changes in v0.2

The natural-language input in §7.3 is removed and replaced with a **tap-to-complete sentence builder** plus a separate **typeahead lookup**. Knock-on effects:

- **§6** — new principle 8: a model runs at build time, never at request time.
- **§7.1** — the three doors now pre-fill the sentence's first blank rather than being a separate mechanism.
- **§7.3** — rewritten. Two controls, two jobs: elicitation and navigation.
- **§10.5** — new: static synonym map, generated at build time and frozen.
- **§12** — the LLM re-rank layer is deleted. The deterministic matcher is the whole matcher.
- **§13** — privacy improves; no user-composed text leaves the browser.
- **§14** — new pre-render policy, needed now that sentence states are indexable.
- **§17** — the runtime abuse and unbounded-spend risks are gone.
- **§18** — Q5 (budget) resolves: domains only.
- Roadmap loses a phase. Former Phase 4 is deleted; former Phase 5 becomes Phase 4.

---

## 1. Summary

A London-only signpost that turns "I'd like to help with homelessness" into a specific, reachable, doable next step — and hands the person off to the charity's own page to actually apply.

The PoC was a filterable directory of 34 charities. This spec replaces it with a **decision tool built on role-level data**. Three changes carry almost all the value:

1. **Records are roles, not charities.** A charity is not a thing you can volunteer for. "Saturday morning kitchen shift at the Manna Society, 3 hours, no DBS needed, 18+" is. One organisation yields three to eight role records.
2. **Commitment is the primary axis.** Not charity type. Everyone knows whether they have one Saturday or six months; nobody arrives knowing whether they want "befriending".
3. **Freshness is the product.** An automated weekly check of every charity's volunteering page is the one thing this site can offer that a Google search cannot — and it is what makes the zero-maintenance constraint actually true rather than aspirational.

The whole system is static. Nothing runs at request time. There is no server, no database, and no public endpoint that can be abused or run up a bill.

---

## 2. Why the PoC needed rebuilding, in one paragraph

The filters didn't discriminate. "Advice" was tagged on 23 of 34 cards, "skills-based" on 19, "day centre" on 18; cards carried 4.9 tags each out of 13. Nineteen of 34 charities were tagged `london-wide`, and the area filter's logic passed those through regardless of selection, so choosing "North London" returned 20 of 34 results and "Central London" returned 25. Type filters used OR across groups, so adding a filter widened results. The net experience was operating controls and watching nothing happen. Underneath the filter problem sat an information problem: the page held nothing about time commitment, screening requirements, shift times or intake dates — the four things that actually decide whether a person volunteers.

---

## 3. Assumptions

Stated so they can be challenged rather than silently inherited.

- **A1.** Audience is people already in or near London who have decided they want to help, not people who need help. (Signposting people *into* services is a different product with different duty-of-care obligations — see §4 Non-goals.)
- **A2.** The site never processes applications, holds accounts, or takes money. It is a signpost.
- **A3.** Success is a click-through to a charity's own volunteering page. What happens after that is not observable to us, and we should not pretend otherwise.
- **A4.** This is a side project with a near-zero running budget and one maintainer. Every architectural choice below is made to survive that. **This assumption has veto power** — it is what removed the runtime matcher in v0.2, and it should be applied to any future feature that adds an attended component.
- **A5.** Initial scope is the 34 organisations already researched, expanded to full role-level coverage. No new organisations in Phase 1.

---

## 4. Goals, non-goals, success measures

### Goals

- **G1.** A first-time visitor reaches a shortlist of three to six genuinely suitable roles in under 60 seconds, without learning a taxonomy and without composing a sentence from scratch.
- **G2.** Every listed role carries the four decision-critical facts: commitment, when, where (and whether they can get there), and what screening is required.
- **G3.** Data stays accurate without manual upkeep, and the site is visibly honest about how fresh each record is.
- **G4.** A filtered view is a real URL — shareable, bookmarkable, indexable.
- **G5.** Someone who won't volunteer still leaves having done something useful.

### Non-goals

- Processing applications, accounts, messaging, donations, or DBS checks.
- Vetting or endorsing charities. We reflect what their own pages say; we do not assess them.
- Being a national directory. London only. (See §18 Q2.)
- Serving people experiencing homelessness. Different product, different obligations. We link to StreetLink and Shelter's helpline for anyone who lands here by mistake, and nothing more.
- **Any runtime intelligence.** No live model calls, no personalisation, no recommendations that can't be explained from the visible constraints.

### Success measures

| Measure | Definition | Phase 1 target |
|---|---|---|
| Outbound rate | Sessions with ≥1 click to a charity apply/volunteer URL | ≥ 35% |
| Time to shortlist | Median seconds from landing to a result set of ≤ 8 roles | ≤ 45s |
| Shortlist reach | Sessions reaching a result set at all | ≥ 70% |
| Blank completion | Sessions filling ≥ 2 of the 3 sentence blanks | ≥ 50% |
| Link health | Role records whose apply URL returns 200 | ≥ 98% |
| Freshness | Median days since last successful check | ≤ 7 |
| Share rate | Sessions producing a copied/shared deep link | tracked, no target yet |

Blank completion is the measure that tells us whether §7.3 worked. If people fill one blank and stop, the sentence isn't doing its job and we fall back to the two-blank variant described in §7.3.4.

Honest caveat: none of these measure whether anyone actually volunteered. A lightweight "did you get in touch?" follow-up is deferred to Phase 4 and would need consent handling, so it is out of scope for now.

---

## 5. Users and jobs

Three segments, served in this order of volume.

**The Saturday helper (largest).** Has a free weekend or two, wants to do something concrete and physical, worries about being useless or in the way. Job: *"Give me one thing I can turn up to that doesn't need six months of commitment."* Blocked by: not knowing what a shift actually involves, and vague "get in touch" pages.

**The skills giver.** Professional — legal, finance, IT, HR, comms — willing to give a few hours a month remotely. Job: *"Where can what I already know be useful?"* Blocked by: charity sites burying skills-based and trustee roles under generic volunteering copy.

**The committed one (smallest, highest value).** Ready for mentoring, befriending, hosting, or a trustee seat. Job: *"What's the serious version of helping, and what will it ask of me?"* Blocked by: not knowing about DBS timelines, training weekends, or minimum terms until deep into an application.

Two secondary considerations, not segments: **people with lived experience** of homelessness, for whom several organisations run specific peer roles — these must be findable and framed with dignity, not as a curiosity; and **corporate/team organisers** looking for a group day, who are a Phase 4 concern at most.

---

## 6. Product principles

1. **Elicit, don't ask people to articulate.** The system offers the words; the visitor picks. A blank input asks the visitor to guess what we understand, and they will guess low.
2. **Attribute, don't assert.** Every fact is presented as *what the charity's page says, checked on a date*, with a link. We never speak in our own voice about someone else's safeguarding requirements.
3. **Narrowing must narrow.** Adding a constraint always reduces the result count. No exceptions.
4. **A facet that matches most of the corpus isn't a facet.** Any filter value covering >60% of records gets removed or split.
5. **Degrade honestly.** If a check fails, if data is stale, if a link is dead — say so in the interface. A stale record that admits it is more trustworthy than a fresh-looking one that lies.
6. **Every dead end is an offer.** Empty states, closed roles, oversubscribed programmes — each offers the next thing to try.
7. **No account, no cookie banner, no email capture.** The absence of friction is a feature and should be visible.
8. **A model runs at build time, never at request time.** Extraction, synonym generation and data shaping are model work, done from a scheduled job on a controlled key with output routed to human review. Nothing a visitor touches calls a model. This keeps the runtime static, unattended, free and unabusable — and it is the rule to apply to any future idea that starts with "what if it could just understand…".

---

## 7. Core interaction model

### 7.1 The three doors

The landing screen asks one question — *how much can you give?* — as three doors:

| Door | Label | Covers |
|---|---|---|
| A | **One day** | One-off shifts, seasonal events, coat drives, sleep-outs, corporate days |
| B | **Every week or so** | Recurring shifts: kitchens, day centres, shops, drop-ins, outreach |
| C | **Something bigger** | Mentoring, befriending, hosting, live-in, peer advocacy, trustee |

Three large tap targets, each showing a live count ("47 one-day opportunities"). A fourth quiet link — *"Not sure yet — show me everything"* — goes to `/all/`.

**The doors are not a separate mechanism from §7.3.** Choosing a door pre-fills the first blank of the sentence and lands the visitor on the results view with that constraint already applied. The door is the low-effort entry (one tap, no reading); the sentence is where refinement happens. Commitment-first survives because it is both the first door and the first blank, and it drives the default sort: Door A sorts by *soonest*, Door B by *travel time*, Door C by *depth of role*.

### 7.2 The map as the page, not a feature

Geography is how this decision is actually made. The map is therefore the main canvas on desktop within a door, not a tab.

- London rendered dark, in the night-navy palette carried over from the PoC. Each role is a **lit window** — the lamplight motif doing real work rather than being shrunk into a 26px logo.
- Entering a postcode dims everything outside a **30-minute public-transport reach**. Sliders extend to 45 and 60 minutes.
- Remote roles sit in a fixed rail beside the map, not floated on it — they have no location and shouldn't pretend to.
- **The map is a view, not the source of truth.** The list is canonical; the map renders it. Every map interaction has a list equivalent, and mobile defaults to the list with the map behind a toggle. This is both an accessibility requirement (§13) and a hedge against the map being the slowest thing to build.

**Signature moment:** on first load, as the map settles, windows light one by one across the city — 200ms stagger, capped at 1.2s total, killed entirely under `prefers-reduced-motion`. Once. Not on every filter change.

### 7.3 Two controls, two jobs

v0.1 specified a single free-text box interpreted by a model. That was wrong twice over. A blank box hides the system's capability, so visitors hedge and type two keywords — meaning we'd have paid a model to do a facet's job badly. And a public inference endpoint would have been the only attended, spendable, abusable component in an otherwise entirely static system, in violation of A4.

The underlying job was real, though: **the vocabulary problem**. Nobody arrives knowing they want "befriending", and a bare facet list regresses to the PoC's failure. The fix is to elicit rather than to parse, and to separate two jobs that v0.1 had conflated.

#### 7.3.1 The sentence builder — for "help me decide"

A single sentence the visitor completes by tapping. It is pre-filled, always grammatical, always valid, and already returning results before it is touched.

> I've got **[one day ▾]** to give, I'm near **[add a postcode +]**, and I'd like to **[anything ▾]**.

| Blank | Source | Default | Options |
|---|---|---|---|
| 1 — commitment | Door choice, or `weekly` at `/all/` | pre-filled | 6 (§Appendix A) |
| 2 — reach | Postcode or station | unset, invitational | free entry, validated against a static district list |
| 3 — activity | none | `anything` | 12 (§Appendix A) |

Behaviour:

- **Always valid.** There is no submit button and no error state for an incomplete sentence. Unfilled blanks read as invitations (`add a postcode`), not as gaps.
- **Every change narrows and is announced.** Result count updates in a single live region; the count line names what the last change did ("postcode added — 47 → 12").
- **Unfillable options are shown disabled with the reason**, so a zero-result state can't be constructed. Principle 3, made visible.
- **Each state is a URL** (§7.4), which the free-text box could never have been.
- **Reset is per-blank**, not global — an × on each filled blank. The PoC's single "clear filters" was too blunt.

Rendering: inline prose on desktop; stacked labelled rows on mobile, where inline mad-libs tap targets get fiddly. Native `<select>` or a proper listbox pattern for blanks 1 and 3 — never a custom div-based dropdown. With JavaScript disabled it degrades to three selects and a "show results" button.

#### 7.3.2 The typeahead — for "I already know what I want"

A separate, persistent control in the header. This is **navigation, not matching**, and the two should never have shared an input.

It searches a closed, finite vocabulary of roughly 350 terms: 34 organisation names (plus common aliases — "St Mungo's", "Mungos"), 33 boroughs, ~120 postcode districts, ~160 role titles. Client-side, fuzzy enough to survive a misspelling, no network call, no ambiguity, instant. Selecting a result navigates to that entity's page; it does not filter the current view.

#### 7.3.3 The synonym map

The sentence builder needs to absorb colloquial vocabulary that isn't in the option labels — "soup kitchen", "night shelter", "help out at Christmas", "food bank". A static map of roughly 150 colloquial terms to facet values, generated at build time and reviewed by hand (§10.5). It powers the typeahead's fallback matches and the copy shown against each activity option, so the visitor sees their own words next to ours.

#### 7.3.4 Fallback if this doesn't test well

The known risk with this pattern is that it stops reading as a sentence when a blank's option list runs long. Blank 3 has twelve values, which is at the ceiling. **Three blanks is the hard maximum** — beyond that it is a form wearing a costume, which is worse than an honest form. If Phase 1 shows low blank-3 completion or confusion, demote blank 3 to an ordinary refinement chip row and keep the sentence at two blanks. Design for that fallback from the start rather than retrofitting it.

### 7.4 URL as state

Every meaningful view is a real path, not a query string.

```
/one-day/
/weekly/hackney/
/weekly/hackney/cooking/
/bigger/mentoring/
/near/e8/30min/
/role/manna-society-kitchen-shift/
/charity/manna-society/
```

Pre-render policy in §14. This is the acquisition channel — "volunteer homeless charity hackney" is a real search, and the PoC could not rank for it because it was a single page with no state. It is also an argument the free-text box would have lost: text queries are not indexable.

---

## 8. Information architecture

```
/                       Three doors + typeahead + five-minute actions
├── /one-day/           Sentence pre-filled to one-off; sorted by soonest
├── /weekly/            Sentence pre-filled to weekly; map primary
├── /bigger/            Sentence pre-filled to long-term; longer descriptions
├── /all/               Sentence at defaults, all refinements exposed
├── /near/{district}/   Reach-based entry point (pre-rendered per district)
├── /role/{slug}/       Single role detail
├── /charity/{slug}/    Organisation page: all its roles + verification info
├── /five-minutes/      Actions for people not volunteering today
├── /about/             What this is, who made it, what we don't do
├── /data/              How the freshness check works; link to the source data
└── /help/              For anyone who landed here needing help, not offering it
```

---

## 9. Screen specification

### 9.1 Home

- **Above the fold:** one sentence of framing, the three doors, the typeahead. No hero paragraph about the scale of homelessness — people who arrived here already care; explaining the problem to them wastes the fold.
- Below: three five-minute actions, and a single honest line — *"We list 34 London organisations and 160-odd roles. We check every one of their pages weekly. We don't take applications and we don't vet charities."*
- **Deliberately absent:** statistics, stock photography of people sleeping rough, a donation ask, a newsletter modal.

### 9.2 Door / results view

| Region | Desktop | Mobile |
|---|---|---|
| Sentence builder | Sticky, above the map and list | Sticky top; stacked rows |
| Map | 60% width, sticky | Behind a toggle; list default |
| List | 40% width, scrolls | Full width |
| Extra refinements | Collapsible row beneath the sentence | Bottom sheet (keep the PoC's — it was well built) |

The sentence is the primary control and carries the three highest-value constraints. Everything else — screening tolerance, who it's with, remote-only — lives in the secondary refinement row. Two competing controls of equal prominence is what made the PoC confusing; the hierarchy here must stay obvious.

Behaviours:

- Result count announced once via a single `aria-live="polite"` region.
- Hovering a list card highlights its map window and vice versa.
- **Card chips are clickable** — tapping "no DBS needed" on a card adds it as a refinement. The PoC's tags were decorative dead ends.
- Sort control: *soonest*, *nearest*, *least commitment*.

### 9.3 Role card (list item)

Four facts, always, in fixed positions so the eye can scan down a column:

```
┌────────────────────────────────────────────┐
│ Kitchen shift                  Manna Society│
│ Southwark · SE1 · 22 min from E8            │
│                                             │
│ Cook and serve lunch for around 80 guests,  │
│ then help clear down.                       │
│                                             │
│ Saturdays 9am–12pm · 3 hrs · Weekly          │
│ No DBS · 18+ · Trial shift first             │
│                                             │
│ Open · checked 2 days ago                   │
│ [ Apply on their site → ]                   │
└────────────────────────────────────────────┘
```

Rules:

- Maximum **three** attribute chips. The PoC's 4.9-tag average was noise.
- The blurb says what you would *do*, not what the charity *is*. Charity description belongs on `/charity/{slug}/`.
- Travel time renders only once a postcode is given; otherwise the line shows borough and district. Never show a placeholder like "— min".
- The status line is mandatory and carries the honesty burden: `Open` / `Closed for now` / `Oversubscribed` / `Seasonal — opens October` / `We couldn't check this page`.
- **The button never lies.** Without a role-specific apply URL it reads "Their volunteering page →", and failing that, "Their website →". Two PoC cards had a "Volunteer →" button pointing at a homepage.

### 9.4 Role detail

Everything from the card, plus: full role description (paraphrased, never copied), what a first session typically involves, training and induction requirements, published accessibility notes, the organisation's other roles, and a **verification block** — source URL, timestamp of last successful check, whether the record was machine-extracted or human-reviewed, and a "report a problem" link.

### 9.5 Empty and failure states

| State | Copy direction |
|---|---|
| No results | Name the binding constraint and offer to relax it: *"Nothing weekly within 30 minutes of E8. Try 45 minutes (adds 6) or one-day roles (adds 12)."* Buttons, not prose. |
| Postcode not recognised | Inline, beside the blank: *"That doesn't look like a London postcode. Try a district like E8, or pick a borough."* Never blocks the rest of the sentence. |
| Reach lookup fails | Fall back to borough selection silently; don't block. |
| Check failed on a record | *"We couldn't reach this page on 21 August. It may have moved — try their main site."* Card stays visible, demoted in sort. |
| Someone needing help | A persistent, quiet footer link to `/help/`, plus a typeahead term list that routes there. |

### 9.6 Five-minute actions

For the majority who will not volunteer today. Three, refreshed seasonally:

1. **Report someone sleeping rough** — StreetLink, with a plain explanation of what happens next.
2. **Give something specific** — nearest coat/sleeping-bag drop-off, or a named current appeal.
3. **Set a reminder** — winter shelter recruitment opens in autumn; an .ics download, not an email capture.

---

## 10. Data model

Two record types plus three lookups. Stored as JSON in the repo, one file per organisation.

### 10.1 Organisation

```jsonc
{
  "id": "manna-society",
  "name": "Manna Society",
  "aliases": ["the manna", "manna society southwark"],
  "charity_number": "1002259",
  "website_url": "https://...",
  "volunteer_url": "https://...",
  "summary": "Day centre near London Bridge providing meals, showers, clothing and welfare advice.",
  "coverage": "borough",
  "boroughs": ["southwark"],
  "focus_groups": ["rough_sleeping"],
  "lived_experience_roles": false,
  "check": {
    "last_attempt": "2026-08-22T04:00:00Z",
    "last_success": "2026-08-22T04:00:00Z",
    "link_status": "ok",
    "content_hash": "sha256:..."
  }
}
```

`aliases` is new in v0.2 — it feeds the typeahead (§7.3.2).

### 10.2 Opportunity (the important one)

```jsonc
{
  "id": "manna-society-kitchen-shift",
  "org_id": "manna-society",
  "title": "Kitchen shift",
  "what_youd_do": "Cook and serve lunch for around 80 guests, then help clear down.",

  "commitment": "weekly",
  "min_term_months": null,
  "typical_shift_hours": 3,
  "when": ["weekend_daytime"],
  "specific_times": "Saturdays 9am–12pm",

  "activity": ["cooking_serving"],
  "location_type": "in_person",
  "postcode_district": "SE1",
  "coords": [51.5012, -0.0876],

  "screening": {
    "dbs": "none",
    "references": false,
    "interview": false,
    "min_age": 18,
    "induction": "Trial shift first"
  },

  "skills": ["cooking"],
  "seasonal_window": null,
  "next_intake": null,
  "status": "open",

  "apply_url": "https://...",
  "url_specificity": "role",

  "provenance": {
    "extracted_at": "2026-08-22T04:00:00Z",
    "method": "llm",
    "reviewed_by_human": true,
    "confidence": 0.91,
    "source_url": "https://..."
  }
}
```

`activity` is new in v0.2 and is the field behind the sentence's third blank. It is deliberately single-valued in most cases — a role that claims five activities is a role we've described badly, and that was exactly the PoC's failure mode.

**Field-level rule:** anything inside `screening`, plus `status` and `next_intake`, may **never** be published on machine extraction alone. Those are the fields where being wrong wastes someone's day or misstates a safeguarding requirement. Human review required (§11.3).

### 10.3 Reach lookup

The reason this costs nothing to run.

Rather than calling an isochrone API at runtime, precompute **once**: for every London postcode district (~120) and every role location, the public-transport journey time. Store as an inverted index:

```jsonc
{ "E8": { "30": ["manna-society-kitchen-shift", "..."], "45": [...], "60": [...] } }
```

Generated offline with OpenTripPlanner against TfL's GTFS feed and OS Open Names. A few hundred KB gzipped, O(1) lookup in the browser, no API key, no rate limit, no per-request cost, works offline. Regenerate annually or when the role set changes materially.

### 10.4 Five-minute actions

A small hand-curated file. Three items, reviewed quarterly. Not everything needs automating.

### 10.5 Synonym map (new in v0.2)

Static JSON, roughly 150 entries, mapping colloquial vocabulary to facet values.

```jsonc
{
  "soup kitchen":      { "activity": ["cooking_serving"], "commitment": null },
  "night shelter":     { "when": ["overnight"], "seasonal": true },
  "help at christmas": { "commitment": ["one_off"], "seasonal": true },
  "food bank":         { "activity": ["cooking_serving", "shop_warehouse"] }
}
```

Generated at build time by a model against the role corpus, then **reviewed by hand and frozen as a committed file**. Regenerated only when the role set changes materially. It never runs at request time; it ships as data. Auditable, diffable in git, cannot hallucinate.

---

## 11. The freshness pipeline

This is what makes the "I don't want to maintain data" requirement genuinely true rather than aspirational, and it is the one place a model earns its keep — build time, controlled key, controlled rate, output to a pull request rather than to a stranger (principle 8).

### 11.1 Schedule and fetch

Weekly GitHub Action, Sunday 04:00 UTC.

For each organisation's `volunteer_url`:

- Respect `robots.txt`. If disallowed, skip and mark the record `link_only`.
- Identify honestly: `User-Agent: [BotName]/1.0 (+https://.../about/bot)` with a contact address and an opt-out route.
- One request per second, single-threaded. Thirty-four pages is a two-minute job; there is no reason to hammer anyone.
- Send `If-None-Match` / `If-Modified-Since`. A 304 costs nothing and skips extraction entirely.

### 11.2 Extract

If the content hash changed, pass the page text to Claude with the §10.2 schema and a strict instruction to return `unknown` rather than guess. Roughly 34 pages × maybe 8 changing per week × ~6k tokens — pennies per month on Haiku, low single-digit pounds on Sonnet. This is the only model spend in the system and it is bounded by a fixed number of pages on a fixed schedule.

Two hard constraints on the extractor:

- **Paraphrase, never reproduce.** `what_youd_do` must be an original one-line summary, not the charity's sentence with the punctuation moved. Store facts, not prose.
- **Unknown is a valid answer and is preferred to a plausible guess**, especially for `screening`.

### 11.3 Gate

| Change type | Route |
|---|---|
| No material change | Auto-publish, bump `last_success` |
| Non-critical field changed (description, shift hours, skills) with confidence ≥ 0.85 | Auto-publish |
| Any `screening`, `status`, or `next_intake` change | **Open a PR for human review.** Never auto-publish. |
| Confidence < 0.85 | PR for review |
| New role detected | PR for review |
| Role disappeared from page | Auto-set `status: unknown`, demote in sort, PR for review |
| Fetch failed twice consecutively | Set `link_status: dead`, surface in UI, PR |

The PR is the review queue. Reviewing eight diffs a week is ten minutes of reading, not a maintenance burden — and it keeps a human between the model and any claim about safeguarding.

### 11.4 Publish

Merged PR → static rebuild → deploy. Data lives in the repo, so the full history of every record is in git, which is also the audit trail.

### 11.5 Graceful decay

If the pipeline stops running — holiday, lost interest, broken token — the site must not silently rot:

- After **21 days** without a successful check, records show "not checked recently" and assertive fields (screening, status, intake) are **hidden**, leaving only the link.
- After **60 days**, a site-wide banner says the listings aren't being maintained and points to Reach Volunteering and Homeless Link's job board.

A site that admits it has stopped being maintained is more useful than one that quietly misleads.

---

## 12. Matching

**One layer. Deterministic. Entirely client-side.** The v0.1 LLM re-rank layer is deleted.

Scored, not merely filtered:

1. **Hard constraints** eliminate: commitment mismatch, outside the reach set, `activity` mismatch when blank 3 is set, screening tolerance breach.
2. **Score** the survivors: exact `when` match outweighs adjacent; nearer beats further; `status: open` beats `unknown`; `url_specificity: role` beats `org_homepage`; a role whose seasonal window is open now is boosted.
3. **Sort** by the door's default, overridable by the sort control.
4. **Explain** each result with a one-line rationale generated by template from the record's own fields — "Saturday 9am–12pm, 22 min from E8, no DBS needed". Templated rationales read *better* than generated ones here, because they're consistent down a column and the eye can compare them.

The entire matcher is a pure function over static JSON. It is testable, reproducible, works offline, costs nothing, and cannot be abused. Total data payload for 160 roles plus the reach index is well under 500KB gzipped.

---

## 13. Accessibility, performance, privacy

**Accessibility — WCAG 2.2 AA, non-negotiable.**
- The list is canonical; every map affordance has a list equivalent. Reach filtering works with zero map interaction.
- Sentence-builder blanks use native selects or a proper listbox pattern — never custom div dropdowns. Fully keyboard operable, with visible focus (the PoC's amber 3px outline is good — keep it).
- Exactly one `aria-live` region for result counts.
- Reduced motion respected, including the window-lighting sequence.
- Real heading hierarchy from a single `<h1>`. The PoC had no `<h1>` at all, having lost its hero markup while keeping ~60 lines of orphaned hero CSS.
- Colour never the sole carrier of status — "Closed" says Closed.

**Performance.** Static HTML, no framework on first paint. Map JS lazy-loads only when the map is shown. Target: LCP under 1.5s on 4G, full interactivity without JS for the list and all pre-rendered pages. Separating data from presentation is a precondition for all of this; the PoC was a single 70KB file with data hard-coded into markup.

**Privacy — improved in v0.2.** No user-composed text ever leaves the browser, because there is nothing to send it to. Postcodes resolve client-side against a static centroid file. No accounts, no cookies, no email capture, therefore no consent banner. Analytics via a cookieless, IP-anonymising provider. There is no request log containing anything a visitor typed, because there are no requests.

---

## 14. SEO and pre-render policy (expanded in v0.2)

Now that every sentence state is a URL rather than an unindexable text query, pre-rendering needs a rule to avoid combinatorial explosion.

**Pre-render one- and two-blank combinations only:**

| Pattern | Count |
|---|---|
| `/{commitment}/` | 4 |
| `/{commitment}/{borough}/` | ~132 |
| `/{commitment}/{activity}/` | ~48 |
| `/near/{district}/` | ~120 |
| `/role/{slug}/` | ~160 |
| `/charity/{slug}/` | 34 |
| **Total** | **~500 static pages** |

Trivial for a static build. Three-blank states resolve client-side and carry `noindex` — they're for sharing, not for ranking. Each pre-rendered page gets a distinct title, description and `VolunteerOpportunity` structured data, plus a real sitemap.

---

## 15. Content and tone

- **Second person, active, specific.** "Cook and serve lunch for around 80 guests" beats "opportunities in catering support".
- **The sentence builder's copy is product copy, not decoration.** Blank labels are plain and conversational; option labels use the visitor's vocabulary, not the sector's. If an option label needs a tooltip to be understood, it's the wrong label.
- **Never speak for the charity.** "Their page says an enhanced DBS is needed" — with a date and a link.
- **No poverty tourism.** No stock photography of doorways or sleeping bags. No statistics on the home page. The visitor already cares; the job is logistics.
- **Dignity in role framing.** Peer and lived-experience roles are described as skilled work, because they are.
- **Say what we don't do**, plainly and early: no applications, no vetting, no endorsement.
- British English throughout.

---

## 16. Legal, editorial and safeguarding

- **We do not vet.** Stated on the home page, the about page and every role detail. Listing is not endorsement.
- **We do not host applications.** All screening, DBS and safeguarding sits with the charity, where the duty of care belongs.
- **Charity Commission numbers** shown and linked, so anyone can check registration independently.
- **Proactive contact:** email all 34 organisations before launch — what the site is, that it links to them, how the weekly check works, how to correct a record, how to opt out. Cheap to do, and it converts a potential grievance into a relationship. Several may offer better data directly.
- **Correction route** on every record, target 72 hours.
- **Copyright:** we store structured facts and original paraphrase. We do not reproduce charity page copy, and the extractor prompt enforces this.
- **The `/help/` route** exists solely so that anyone arriving in need of help rather than offering it is routed to StreetLink and Shelter within one click. This is the one duty of care we cannot delegate.

---

## 17. Architecture and phasing

**Stack:** Astro (static output) · MapLibre GL JS with Protomaps tiles on R2 · JSON data files in git · GitHub Actions for the weekly check · Cloudflare Pages hosting. **No database, no server, no Worker, no runtime API, no keys anywhere near the client.** Running cost: the domains.

| Phase | Scope | Effort | Ships value? |
|---|---|---|---|
| **0. Data** | Role-level records for all 34 orgs (~160 roles), by hand, first pass. Settle the schema. | 2–3 weekends. Unglamorous. Non-negotiable. | No — but nothing works without it |
| **1. Core** | Astro build, three doors, sentence builder, typeahead, list, role cards, refinements, URL state, pre-rendered pages, five-minute actions, `/help/` | 2–3 weekends | **Yes — launchable** |
| **2. Reach + map** | OTP precompute, reach index, MapLibre view, lit-window signature | 2–3 weekends | Yes — the differentiator |
| **3. Pipeline** | Fetch, extract, gate, PR flow, synonym generation, decay banners | 1–2 weekends | Yes — makes it sustainable |
| **4. Later** | Seasonality automation, corporate days, follow-up survey, more orgs | — | — |

Phase 1 absorbs roughly half a weekend from the deleted LLM phase (sentence builder is more UI work than a text box) and saves the rest.

**Decision rule on ordering:** Phase 1 must launch with `screening`, `status` and `next_intake` **hidden** unless Phase 3 is committed within eight weeks. Hand-maintained safeguarding data is worse than no safeguarding data, because it looks authoritative and goes stale invisibly. If Phase 3 isn't happening, ship a link-only version and be proud of it.

**Phase 2 note:** blank 2 of the sentence needs the reach index. Until Phase 2, blank 2 offers boroughs rather than postcodes and the third row of the card omits travel time. The sentence structure doesn't change, so this isn't rework.

---

## 18. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Wrong screening/status data wastes someone's day or misstates a safeguarding rule | **High** | Human gate on those fields; attribute-don't-assert framing; visible check dates |
| Maintainer stops; site rots silently | **High** | Automated decay at 21 and 60 days (§11.5) — the failure mode is designed in |
| Charity objects to being scraped or listed | Medium | Identify the bot, respect robots.txt, low rate, proactive email, one-click opt-out |
| Traffic sent to an oversubscribed programme | Medium | `oversubscribed` status; sort demotion; alternatives on the role page |
| LLM extraction hallucinates a role or requirement | Medium | Schema validation, confidence gate, `unknown` preferred, human PR review |
| Sentence builder reads as a fiddly form, not a sentence | Medium | Three-blank cap; stacked rows on mobile; blank-completion metric; documented two-blank fallback (§7.3.4) |
| Map becomes the project and Phase 1 never ships | Medium | List is canonical; map is Phase 2 and cuttable |
| Brand adjacency questions | Medium | §19 Q1 |

*Removed in v0.2:* runtime API abuse, unbounded spend, rate-limit operations, prompt-injection exposure. All were consequences of the deleted inference endpoint.

---

## 19. Open questions — needed before Phase 1

**Q1. Does this carry the 8 Houses name?** Worth deciding rather than defaulting. A consumer PropTech venture attaching its brand to a homelessness signpost invites a "cause-washing" reading however sincere the intent, and it ties a commercial reputation to data accuracy on safeguarding-adjacent topics. Options: (a) 8 Houses branded, commercial relationship stated openly; (b) separate identity, quietly credited; (c) unbranded community resource. My inclination is (b). Affects domain, tone, about page and bot user-agent string.

**Q2. London only, or is London the pilot?** The architecture supports expansion — reach precompute is per-city, schema is city-agnostic — but copy, URL structure and name would need rethinking. Cheaper to decide now.

**Q3. Observational, or do you want charity relationships?** Opt-in data would beat extraction but introduces relationship management that doesn't fit A4. Recommend observational for Phase 1, with the launch email as a soft opening.

**Q4. Who reviews the weekly PRs?** If it's only you, the decay mechanism in §11.5 is doing real work and must be built in Phase 3, not deferred.

**Q5. Budget — resolved.** With the runtime matcher removed, the only recurring cost is domain registration. Model spend is build-time only: roughly 8 extraction calls per week plus an occasional synonym regeneration, comfortably under £1/month on Haiku, on your own key, with no public surface. Hosting is within Cloudflare Pages' free tier at any plausible traffic level.

---

## Appendix A — Facet taxonomy

Replaces the 13 charity-level tags that failed to discriminate. Every facet is defined at **role** level, and any value covering more than 60% of records gets split or dropped before launch.

**Commitment** — sentence blank 1. one-off · flexible · weekly · fortnightly · monthly · long-term (with minimum term)

**Activity** — sentence blank 3, 12 values, single-valued wherever honest. cooking & serving · welcoming & befriending · outreach · advice & casework · mentoring · teaching & skills · shop & warehouse · admin & back office · fundraising & events · campaigning · hosting · trustee & governance

**Reach** — sentence blank 2. Postcode district or station, resolved against the §10.3 index. Falls back to borough before Phase 2.

**When** (secondary refinement) — weekday daytime · weekday evening · weekend daytime · weekend evening · overnight · flexible

**Screening tolerance** (secondary refinement; the facet nobody else offers) — no DBS needed · basic DBS · enhanced DBS · references needed · training required · 18+ · 21+ · 25+

**Who it's with** (secondary refinement) — general · young people · LGBTQ+ · women · veterans · people with addiction experience · peer/lived-experience roles

**Where** (secondary refinement) — in person · remote · hybrid

---

## Appendix B — Superseded decisions

Kept so the reasoning isn't relitigated.

| Decision | Rejected because |
|---|---|
| Free-text natural-language matcher (v0.1 §7.3) | Hides system capability, so visitors under-specify; requires a runtime endpoint that violates A4; not indexable, which undercuts the SEO strategy in §14 |
| LLM re-rank layer (v0.1 §12) | Templated rationales read better and cost nothing; ranking was already deterministic |
| Charity-level records (PoC) | You volunteer for a role, not an organisation. Charity-level tagging is what made every facet non-discriminating |
| Runtime isochrone API | Precomputed reach index is free, faster, offline-capable and keyless |
| Generated one-line rationales | Inconsistent down a column; templates from record fields are more scannable |

---

*Draft for review. §19 first.*
