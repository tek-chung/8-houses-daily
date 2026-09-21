# Pending changes

Everything that has changed since you pushed the first commit. Written so you can
apply it in one go later without reconstructing the conversation.

**Simplest path: re-extract `eight-houses-daily.zip` over the folder, then read
`git diff`.** One download, nothing to miss, and git shows you exactly what moved.
The archive contains source only — no `dist/`, no `.venv`, no `node_modules` — so
nothing local gets clobbered.

```powershell
cd C:\Users\tekka\8houses\Code\homelessness-portal
# extract the zip here, overwriting
git status
git diff --stat
```

Expect roughly 8 changed files and 3 new ones. Current tree: 67 source files.

---

## 1. Windows portability — two bugs, both mine

Neither was your setup. Both worked perfectly on the machine they were written on,
which is exactly why they now have tests.

**File encoding.** `Path.read_text()` defaults to the *locale* encoding — UTF-8 on
Linux and macOS, cp1252 on Windows. `site/static/app.css` uses box-drawing
characters in its section comments, so the build crashed reading its own
stylesheet. All 48 file reads and writes across `site/` and `pipeline/` now pin
`encoding="utf-8"`, and a test walks the AST of every Python file and fails if one
appears without it.

**Date formats.** `%-d` (day of month, no leading zero) is a glibc extension.
Windows' C library rejects it with `ValueError`, and the Windows spelling `%#d`
fails on Linux — no format string works on both. Replaced with two helpers that
assemble the string by hand. A test scans every string literal for `%-` and `%#`.

> Files: `site/build.py`, `site/test_build.py`, `site/tools/build_map.py`,
> `pipeline/census.py`, `decay.py`, `extract.py`, `fetchpage.py`, `reach.py`,
> `run.py`, `seed.py`, `README.md`

Also swept for the other usual Windows traps — hard-coded `/tmp`, `shell=True`,
POSIX separators, unix-only modules like `fcntl`. Clean.

## 2. Deploy as a Cloudflare Worker, not Pages

Cloudflare's guidance changed: since Workers gained native static-asset serving,
new projects start there and Pages is effectively in maintenance mode. My earlier
Pages advice was out of date — the dashboard steered you correctly.

**New file `wrangler.jsonc`** declares an assets-only Worker: no `main`, no script,
nothing executed. Two settings in it are load-bearing.

- `html_handling: auto-trailing-slash` — every page is `/path/index.html`, so
  directory URLs must resolve to the index inside them. Without it the entire URL
  scheme 404s.
- `not_found_handling: 404-page` — serves the paper's own "No such page in this
  edition" instead of a bare Cloudflare error.

`package.json` pins wrangler and adds `npm run deploy` / `npm run preview`. Three
tests check the config against what the build actually produces, because a wrong
directory deploys an empty site *successfully*.

> Files: `wrangler.jsonc` (new), `package.json`, `docs/hosting.md`, `README.md`,
> `site/test_build.py`

## 3. `SITE_URL` comes from the environment

`BASE_URL` was a constant you had to edit. It now reads `SITE_URL`, so the same
commit deploys to a preview and to production. It feeds the sitemap, canonical tags
and Open Graph tags — and a wrong value ships *silently*, because everything looks
fine while pointing at `example.org`.

> Files: `site/build.py`, plus tests that it reads from the environment, that every
> internal reference is root-absolute, and that the build needs no third-party
> packages

## 4. The crawler now has its own contact page

You needed `/bot` to exist before the crawler could visit any charity. The paper
builds it — 46 pages became 47 (now 64 with The Passage added). It gives the exact user-agent string, the rate, and
three ways to stop it including the robots.txt snippet to copy.
`pipeline/config.py` points the user agent at it, so the page describing the
crawler is built by the same repository that runs the crawler and the two cannot
drift apart.

> Files: `site/build.py`, `pipeline/config.py`, `site/test_build.py`

## 5. The Passage — 8 new roles

Read off their live vacancy pages. Data went from 11 roles across 5 charities to
**19 across 6**, and the site from 47 pages to 64.

Two findings worth keeping:

- **The seeded URL was wrong.** `passage.org.uk/volunteering/` redirects; the roles
  live at `/volunteering-vacancies/`. Corrected. The census would have flagged
  this as `redirected`.
- **They accept no one-off group days at all** — corporate volunteering is only
  available inside a paid partnership. A different shape from Whitechapel's
  teams-only, and the schema does not model it. Worth a field if a second charity
  does the same.

> Files: `data/orgs/the-passage.json` (new), `data/site-bundle.json`

## 5b. Groundswell — 2 new roles

The richest screening data found anywhere so far, and the first organisation whose
page states its conditions in full. The Homeless Health Peer Advocate role requires
a DBS check, an interview, four weeks of training before you start, monthly
supervision, at least two days a week, and lived experience of homelessness,
addiction, recovery, mental health or prison. Charity number 1089987, based at
Brixton Road, SW9.

It matters beyond one record: 67% of Groundswell's staff, volunteers and trustees
have experienced homelessness. These are the first `lived_experience` roles in the
dataset, and the first `campaigning` activity.

Data now stands at **21 roles across 7 charities**, and the site at 69 pages.

> Files: `data/orgs/groundswell.json` (new), `data/site-bundle.json`

## 5c. akt — 2 roles, both closed, and a finding for the prompt

akt's volunteering page runs several hundred words on mentoring, Pride parades and
school talks, then its opportunities section reads *"new volunteering opportunities
coming soon... Stay tuned!"* There are no open roles.

This is Finding 1's bait problem in its clearest form: an extractor reading the
prose would produce three confident vacancies with plausible detail and send people
to apply for nothing. Both records are stored `status: "closed"` at confidence
0.5–0.6, which puts a NOT RECRUITING stamp on the notice — more use than hiding
them, far more use than sending someone to apply.

The extraction prompt now says explicitly: where the prose describes role types but
the vacancy list is empty, trust the vacancy list. Describing a role is not
offering it. `docs/scrapability.md` records it as Finding 4b.

Data now stands at **23 roles across 8 charities**, and the site at 73 pages. akt
also brings the first `lgbtq` focus group.

> Files: `data/orgs/akt.json` (new), `pipeline/prompts/extract.md`,
> `docs/scrapability.md`, `data/site-bundle.json`

## 5d. Providence Row — 2 roles, and a fourth enum value

**The second charity found that states its screening plainly.** The Welcome Host
role at the Dellow Centre in Whitechapel: one shift a week, Monday to Friday,
8.30–11.30am or 11.30am–2.30pm, and *"due to the nature of the role (working with
vulnerable adults), DBS Disclosure barring checks are sought"*. The process is a
short chat, then a tour, then a taster day. Charity number 1140192, E1 7SA.

Their rooftop garden role fitted none of the thirteen activities, so
**`activity: "practical"`** is added — gardening, decorating, maintenance.
`shop_warehouse` is a shop floor or a stockroom and does not cover it; someone
looking for outdoor work would never find it there. Fourth enum value forced by
real data, after `required_unspecified`, `own_home` and `varies`.

Data now stands at **25 roles across 9 charities**, and the site at 78 pages. Four
of 25 roles now state a DBS requirement, up from two of eleven — the gap is a
habit, not an impossibility.

> Files: `data/orgs/providence-row.json` (new), `pipeline/schema.py`,
> `site/build.py`, `site/static/app.js`, `pipeline/prompts/extract.md`,
> `data/site-bundle.json`

## 5e. Ace of Clubs and NLAH — 3 roles, and north London at last

**Ace of Clubs** (Clapham, SW4, charity 1055187): lunch service 9.30am to 3pm,
Monday to Friday, feeding 140 to 170 people. The head chef trains you on the job
and lunch is provided.

One provenance note worth understanding. The shift times are published on
*Lambeth Council's volunteer portal*, not on the charity's own page — so
`source_url` points at the portal rather than at aceofclubs.org.uk. That is
deliberate: when the weekly check reads the charity's own page and never finds
those times, it should honestly downgrade them rather than assume they hold.

**NLAH** (Stoke Newington, N16, charity 1139024) brings the **first north London
coverage** — Hackney, Haringey and Islington. Two roles: the twice-weekly drop-in
meal service, and an occasional supplies driver if you have a car or van.

It also produced a small honesty problem worth seeing. **Their own pages disagree
on the Wednesday supper time** — 6pm on two, 7pm on a third. Printing either as
fact would send someone an hour early or an hour late, so the record reads
*"Monday lunch from noon; Wednesday evening — check the time"* and the
`unsupported_fields` entry says exactly why. This is the kind of contradiction the
extraction prompt's `page_notes` field exists to surface for a human.

Data now stands at **28 roles across 11 charities**, and the site at 87 pages.
Boroughs covered: Hackney, Hammersmith and Fulham, Haringey, Islington, Kensington
and Chelsea, Lambeth, Southwark, Tower Hamlets, Wandsworth, Westminster.

> Files: `data/orgs/ace-of-clubs.json`,
> `data/orgs/north-london-action-for-the-homeless.json`, `data/site-bundle.json`

## 5f. Spitalfields Crypt Trust — 4 roles, and the line worth reading

SCT (founded 1965, East London: Hackney, Tower Hamlets, Waltham Forest) runs two
social enterprises and eight charity shops. Four roles: Paper and Cup coffee shop,
Restoration Station furniture workshop, charity shop volunteering, and
office/fundraising/communications.

Their volunteer page carries the single most consequential sentence found in any
of these charities:

> Cautions and convictions do not necessarily prevent an individual from working
> with SCT.

No other charity says this. On a site whose audience includes people with lived
experience of homelessness — and Groundswell's entire volunteer team has it — that
sentence changes whether someone applies at all. It is recorded in
`screening.induction` on all four roles.

Data now stands at **32 roles across 12 charities**, and the site at 99 pages.
Six of 32 roles state a DBS requirement.

> Files: `data/orgs/spitalfields-crypt-trust.json` (new), `data/site-bundle.json`

## 7. The build now schema-checks records — and stayed dependency-free

Writing SCT exposed a real gap. A record with a 158-character field in a
120-character slot **built 99 pages successfully**. The pipeline validates its own
output; nothing validated a record written by hand.

Fixing it produced a second, worse bug that a test caught immediately. My first fix
made `jsonschema` an effective requirement of the site build — and Cloudflare's
build command is `python3 site/build.py` with **no pip install**, so it would have
refused to run and broken deployment outright.

The resolution splits the two concerns properly:

- **The build** validates when jsonschema happens to be available and prints a note
  when it is not. It never fails for want of a package. Hosting stays a one-line
  build command.
- **A test** (`test_every_record_matches_the_schema`) is the real check, running
  locally and in CI where the package is installed. Verified both ways: the build
  exits 0 with jsonschema absent, and the test fails when a record is broken.

The ten invariants that stop a reader being *misled* remain pure stdlib. A field
being 38 characters too long is data hygiene, not a lie.

> Files: `site/build.py`, `site/test_build.py` — 157 tests now

## 5g. West London Mission — 1 role, and a closure notice from the pandemic

WLM's volunteer page still reads *"COVID-19 update: Please note that we are not
taking on volunteers at the moment"*. Live in 2026.

This is a **third** distinct failure mode, and the most troubling of them:

| Pattern | What the page does |
|---|---|
| Bait (akt) | Prose describes roles; vacancy list empty |
| **Stale notice (WLM)** | **Says "not taking volunteers"; notice is years old** |
| Silence (most) | Lists roles, never says whether recruiting |

Why it matters more than it looks: a reader who sees "not recruiting" walks away.
If the notice is five years old they have been turned away by a *page* rather than
by a charity — and WLM's own page lists three named staff with direct phone
numbers that look entirely current.

So the record is `status: "closed"` at confidence 0.5, with an
`unsupported_fields` entry saying the notice is headed COVID-19 and is worth a
phone call. Recorded as Finding 4c in `docs/scrapability.md`, and the extraction
prompt now asks for stale notices to be flagged in `page_notes`.

**One thing worth doing later:** `fetchpage.cms_updated()` already captures a
CMS-published "last updated" date where one exists. This is the case that makes it
worth wiring into the confidence calculation — a closure notice on a page last
touched in 2021 should not weigh the same as one updated last week.

Data now stands at **33 roles across 13 charities**, and the site at 103 pages.
WLM also brings the first `veterans` focus group.

> Files: `data/orgs/west-london-mission.json` (new), `docs/scrapability.md`,
> `pipeline/prompts/extract.md`, `data/site-bundle.json`

## 5h. Spires — 3 roles, and the first outreach in the dataset

The most useful single organisation so far. Charity 1076888, going since 1990,
across Stockwell, Brixton, Streatham, Tooting, West Norwood and Croydon.

Three roles, each with real detail from their own published weekly schedule:

- **Rough Sleeper Drop-In** — 9am to 11.30am; Monday Tooting, Tuesday and Friday
  West Norwood, Thursday Streatham. Cooking and serving breakfast.
- **Women's Outreach** — four night sessions a week with women involved in
  street-based sex work. Health and safety training first, then shadowing shifts
  *"until both you and the team are ready"*.
- **Women's Space** — Thursdays 9am to noon at their Stockwell office.

**A new kind of commitment statement.** Spires ask for *"a minimum commitment of
three hours per month"* — a floor on hours rather than a term in months. The schema
has `min_term_months`, which cannot express it, so it sits in
`screening.induction`. Worth watching: if a second charity states hours rather than
months, that is a field rather than a workaround.

This fills the last big gaps — **first `outreach` roles**, and Croydon brings the
count to 13 boroughs and 13 of 14 activity types.

Data now stands at **36 roles across 14 charities**, and the site at 110 pages.

> Files: `data/orgs/spires.json` (new), `data/site-bundle.json`

## 5i. Women at the Well — 3 roles, and a fifth schema gap

Charity 1118613, King's Cross (WC1H). A women-only drop-in, 12.30pm to 3.30pm
Monday to Thursday, for women whose lives have been affected by prostitution or
sexual exploitation. Three roles: kitchen, activities, reception.

Two firsts, both of which the schema needed to grow for.

**The first genuinely `oversubscribed` roles.** Their page says plainly: *"We often
only have limited spots available for volunteering... we encourage you to apply and
be held on our waitlist."* `oversubscribed` has existed in the schema since v0.2
with nothing populating it, so the `OVER SUBSCRIBED` stamp had never rendered. It
does now, on three notices.

**A new field: `eligibility`.** Their page states *"We are a women-only service and
can only accept applications from women"*, citing the statutory exemption. That is
a hard bar on **who may apply**, and there was nowhere to put it — I had it in
`skills`, where it read as a competence and would have appeared beside "cooking" in
a skills filter.

Two existing records had the same shape and were mis-filed the same way:
Groundswell's requirement for lived experience of homelessness, and Nightstop's for
a spare room. All three migrated. On a classified it prints as **Only for**,
directly after the hours; in an article it is the second paragraph, because it
decides whether the rest is worth reading. Every record now carries the field, with
`[]` where there is no restriction — the schema's discipline is that a missing
field is a bug, not an absence.

Fifth enum or field forced by data, after `required_unspecified`, `own_home`,
`varies` and `practical`.

**Two prose defects this exposed**, both from combinations that had never occurred
before:

- "worth asking" appeared twice on one page — once in the DBS sentence, once in the
  oversubscribed one. They had never co-occurred until an oversubscribed role
  existed. Caught by the concision test.
- "It is in WC1H (WC1H)" — the district-to-borough map had not kept up with the
  districts the research added. Extended to nineteen entries, with a guard so a
  future hole cannot print the district twice.

Data now stands at **39 roles across 15 charities**, and the site at 116 pages.

> Files: `data/orgs/women-at-the-well.json` (new), `pipeline/schema.py`,
> `site/build.py`, `site/static/app.js`, `pipeline/prompts/extract.md`,
> all 15 org files (eligibility backfill), `data/site-bundle.json`

## 5j. The Connection at St Martin's — and a pattern worth watching

Charity 1078201, Adelaide Street beside Trafalgar Square. Europe's largest homeless
day centre, over a hundred people a day.

Its "Current opportunities" list has **exactly one role open to an individual**:
helping at fundraising events. Catering, artistic activities and Christmas are
corporate only, and the page says why — *"We reserve these opportunities for our
financial partners as part of their partnership with us."* 627 corporate volunteers
worked the day centre last year.

**The Passage is the same shape** — *"all our volunteering opportunities are part of
these packages and we are unable to accommodate requests for one-off volunteering
days."* Two of the largest day centres in the set, both with front-line
volunteering behind a corporate paywall.

Not a criticism: managing volunteers costs staff time, and a partnership that funds
the service while supplying the labour is a rational answer. But it is **material
to a reader** and invisible unless someone says it. Someone who wants to serve
lunch at the busiest day centre in Europe cannot, unless their employer writes a
cheque.

**Recorded with no new enum.** The `eligibility` field added for Women at the Well
carries it exactly: `["Companies that are financial partners of the charity"]`
alongside `who_can_apply: "team_only"`. The notice prints **Only for: Companies
that are financial partners** — which is what a reader needs before they email.

Recorded as Finding 4d. Worth watching across the remaining sixteen: if it is
common among the large charities, this paper's most useful function for an
individual may be steering them towards the smaller ones, where the door is
genuinely open.

Data now stands at **41 roles across 16 charities** — half the organisations in
scope — and the site at 121 pages.

> Files: `data/orgs/the-connection-at-st-martins.json` (new),
> `docs/scrapability.md`, `data/site-bundle.json`

## 5k. Single Homeless Project — and the paywall is a choice, not a consequence

SHP is larger than either of the two charities in Finding 4d — over 10,000
Londoners a year — and says the opposite: *"There are many opportunities for
individuals or groups to support us, either on a one-off or regular basis."* So
the corporate paywall is a choice each charity makes, not something size forces.
Finding 4d is updated with the counter-example rather than left implying a rule.

Two roles. The **Peer Mentor** programme has the most precise eligibility statement
found anywhere:

> anyone living in London who is abstinent from illegal and problematic substances
> and who has been free of serious mental health episodes or offending behaviour
> for at least six months

Both clauses are recorded in `eligibility`. Forty-plus Londoners graduate a year,
with accredited training run throughout.

**Two prose defects this exposed**, both fixed:

- *"open only to londoners"* — the eligibility sentence lower-cases its opening
  word so it reads as part of the sentence, which mangles proper nouns. Now
  preserved.
- **An internal contradiction.** Paragraph 1 said the programme runs "across
  Camden, Islington and Westminster"; paragraph 5 said "their page does not say
  where in London it takes place". Both generated from the same record. The cause
  is a real schema gap: **boroughs exist only at organisation level**, and SHP is
  the first charity whose roles differ from each other geographically. The claim
  came out of the prose and the gap is recorded in `provenance`. Deferred rather
  than fixed — one case is not enough to add a field, which is the same judgement
  applied to `depth` and to hours-based minimums.

Data now stands at **43 roles across 17 charities**, and the site at 126 pages.

> Files: `data/orgs/single-homeless-project.json` (new), `site/build.py`,
> `docs/scrapability.md`, `data/site-bundle.json`

## 5l. Thames Reach — and a test for borrowed facts

Their own volunteer page names **no roles at all**, pointing instead at a separate
vacancies list, so the record is `status: "unknown"` at confidence 0.5. What their
page does say is worth recording: volunteering there is openly framed as a route
into paid work in the sector, and they have case studies of people who took it.

The detailed role — BSL support at Brent Reach, one-day core training, travel paid
up to £10 — is on **the GLA's Team London platform**, not their site. That listing
also refers to *"lock down times"* and a *"COVID risk assessment"*, dating it to
2020 or 2021. So it sits in `unsupported_fields` with its source and age named
rather than being presented as current fact.

**Finding 4e** records the pattern: third-party volunteering portals are better
structured and less reliable than charities' own pages. They are what a search
surfaces first, and they are where listings go to die — a charity updates its own
site and forgets the copy it put on a council portal five years ago.

**And a new test, which failed the moment I wrote it.**
`test_facts_taken_from_someone_elses_site_say_so` asserts that any record whose
`source_url` is off the charity's own domain must declare it. Ace of Clubs failed:
its shift times come from Lambeth Council's portal, and I had recorded that in the
change log but **not in the record**. Now fixed.

Why it matters: the weekly check only ever reads the charity's own
`volunteer_url`. An undeclared third-party fact is therefore treated as verified
first-party data forever, and a five-year-old council listing outlives the thing it
described.

Data now stands at **44 roles across 18 charities**, and the site at 127 pages.
158 tests.

> Files: `data/orgs/thames-reach.json` (new), `data/orgs/ace-of-clubs.json`,
> `docs/scrapability.md`, `site/test_build.py`, `data/site-bundle.json`

## 5m. Solace Women's Aid — the first enhanced DBS, and two prose guards

Charity 1082450, London's largest domestic abuse and sexual violence charity, ~300
staff. Their published role description for the North London Rape Crisis helpline
is a **PDF on their own site** — the best provenance for screening found anywhere:

> our volunteer opportunities are open to women only (exempt under the Equality Act
> 2010, Schedule 9, Part 1), and these volunteer roles are exempt from the
> rehabilitation of offenders act 1974 and subject to **enhanced DBS checks**

**First `enhanced` DBS in the dataset.** Also the first `min_term_months` from a
stated range (six to twelve), and the statutory ROA exemption means spent
convictions must be declared — recorded in `induction`.

Their definition of women explicitly includes trans women, which the eligibility
entry records rather than paraphrasing away.

`status: "unknown"` at confidence 0.9: the role description is dated January 2024
and no live listing was found, so whether they are recruiting is genuinely not
stated. High confidence in the *facts*, no confidence in the *availability* — the
two are separate and the record keeps them separate.

**Two prose defects, both now guarded in code rather than patched in data:**

- *"open only to women only"* — I had written an eligibility phrase with a leading
  "only" twice by this point, so the sentence builder now strips a duplicate
  instead of my correcting each record.
- *"Their page does not set out the hours, and takes about 4 hours at a time"* —
  the clauses did not compose when a page gives no clock time but the shift length
  is known. It now reads *"Their page does not set the time of day, though a shift
  is about 4 hours."*

Data now stands at **45 roles across 19 charities** — nearly two-thirds of the
organisations in scope — and the site at 129 pages.

> Files: `data/orgs/solace-womens-aid.json` (new), `site/build.py`,
> `data/site-bundle.json`

## 5n. Stonewall Housing — the first remote role, and the first stated age

Founded 1983, the leading charity for LGBTQ+ people facing homelessness. Their
volunteer page is unusually complete about what they ask:

> Volunteers must be 18+ and living in the UK. We will need to run our own DBS
> check for you. You will also need access to your own computer, tablet or smart
> phone, with access to the internet for each of your shifts.

Three firsts in one record:

- **The first genuinely `remote` role.** Not `own_home`, which is for hosting
  someone at your address — this is work done from anywhere, on a platform they
  train you on, with a supervisor present for every shift.
- **The first stated minimum age** in 46 roles. `min_age` has been null everywhere
  until now.
- The first role where the *equipment* is the requirement: own device, own
  internet.

Data now stands at **46 roles across 20 of 32 charities**, and the site at 130
pages.

### The screening picture, after twenty charities

`docs/scrapability.md` originally concluded that charities do not publish their
screening requirements, on a sample of five. Twenty in, that needs qualifying:

| | Phase 0 (5 orgs) | Now (20 orgs) |
|---|---|---|
| Roles | 11 | 46 |
| DBS stated | 2 (18%) | 8 (17%) |
| Minimum age stated | 0 | 2 |
| Enhanced DBS | 0 | 1 |

The proportion has barely moved, so the original finding holds — **a screening
filter still cannot work**. But the shape of the gap is clearer: it is not that
the information is unavailable, it is that most charities do not think to publish
it. Groundswell, Providence Row, Solace and Stonewall Housing all state their
requirements in full, and Solace publishes a role-description PDF. Those that do
tend to be the ones running the most sensitive services.

That strengthens the case for **§19 Q3 going the relationship route**: the four
questions in `docs/launch-email.md` are asking for something a fifth of these
charities already publish voluntarily.

> Files: `data/orgs/stonewall-housing.json` (new), `data/site-bundle.json`

## 5o. New Horizon Youth Centre — a seed flag confirmed, and why

`pipeline/seed.py` flagged NHYC's URL as pointing at a paid jobs page. Correct —
and the reason matters more than the flag. Their get-involved page **is** a jobs
page because their volunteering runs as student placements:

> You must be able to demonstrate valid enrolment at a UK or EU higher level
> institution and we can only offer placements to students aged 18 or over.

The role descriptions — kitchen, ESOL tutor, sports assistant — are on **UCL's
student volunteering platform**, not on New Horizon's site at all. Third time a
third-party portal has held the detail, second time it has been a university
rather than a council.

A reader who is not a student cannot volunteer here, and nothing on the charity's
own route says so until a paragraph about placements. `eligibility` carries it, so
the notice prints **Only for: students enrolled at a UK or EU university** before
anyone spends time on it. All three roles are `status: "unknown"` at confidence
0.6 — no live listing exists on their site, CharityJob or NHS Jobs.

Recorded as Finding 4f.

Data now stands at **49 roles across 21 of 32 charities**, and the site at 134
pages. Five roles now state a minimum age; thirteen carry an eligibility bar.

> Files: `data/orgs/new-horizon-youth-centre.json` (new), `docs/scrapability.md`,
> `data/site-bundle.json`

## 5p. Simon Community — 4 roles, and a second seed flag corrected

Charity 1090938, founded 1963, 129 Malden Road NW5. Run almost entirely by
volunteers: previously homeless residents and live-in volunteers share a house and
run nine outreach services a week between them.

`seed.py` flagged the seeded URL as a homepage. **Corrected** —
`/volunteering/` resolves and carries full role detail. That is the second seeded
URL this session that was wrong in the way `seed.py` predicted; the flags were
worth having.

Four roles, all from their own page:

- **Street Work** — a set route through central London, about two hours, food and
  hot drinks. They suggest *"once every week or two"*, which is the first
  `fortnightly` commitment in the dataset.
- **Minibus Driver** — *"over 25 and a clean licence"*. The only over-25
  requirement anywhere, and a different kind of bar from the others: an insurance
  floor rather than a safeguarding one.
- **Live-in Volunteer** — the only residential volunteering in the set. Move into
  the house, six to twelve months, board, food, travel and bills covered, time off
  in a separate house, 19 or over.
- **Social Media, Bids and Procurement** — a few hours of a professional skill.

**A judgement worth recording.** The live-in role's term and expenses are
corroborated by CharityJob and VolunteerMatch rather than stated on their own
page, so it sits at confidence 0.8 with that named in `unsupported_fields`. The
`min_age: 19` reads as their own copy and is quoted identically across three
sites, so it is verified.

Minimum ages now stated across three roles at 18, 19 and 25 — `min_age` was null
in all 11 roles at the start of this session.

Data now stands at **53 roles across 22 of 32 charities**, and the site at 139
pages.

> Files: `data/orgs/simon-community.json` (new), `data/site-bundle.json`

## 5q. SPEAR — one role, and a rule holding up

Working across Richmond, Kingston, Merton, Sutton and Wandsworth since 1987. Their
volunteer page names one current role — fundraising — and says plainly that *"we
advertise new roles frequently so remember to keep checking this page"*, which is
recorded in `unsupported_fields` so the notice does not imply more permanence than
exists.

**It tests a rule written into the extraction prompt two batches ago** and the rule
holds. SPEAR says: *"We welcome applications from people from all backgrounds,
particularly those who have first-hand experience of homelessness."*

That is a **preference, not a bar**, and the prompt says a preference belongs
nowhere: `eligibility` is for restrictions on who may apply. Recording it there
would have inverted an open invitation into a restriction — turning "we would
especially like to hear from you" into "only for people who have been homeless".
It sits in the prose instead, where it reads as the welcome it is.

Worth noting because it is the first time one of these rules has been tested
against data it was not written for, and it produced the right answer.

**South-west London is now covered** — Richmond, Kingston, Merton and Sutton were
blank until this record. Seventeen of thirty-three boroughs now carry notices.

Data stands at **54 roles across 23 of 32 charities**, and the site at 144 pages.

> Files: `data/orgs/spear.json` (new), `data/site-bundle.json`

## 5r. Emmaus — the seed treated a federation as one charity

Worth flagging as a **scope correction**, not just new data. `seed.py` recorded
"Emmaus" as a single organisation pointing at `emmaus.org.uk`. Emmaus is a
federation of 30+ independent charities, each with its own registration, own
volunteer page and own roles. London has three: **Greenwich** (1064472),
**Lambeth** and **Barnet**.

This record is now **Emmaus Greenwich** — the one with published roles. Plumstead
base, shops in Poplar and Lewisham, a home and work for up to 45 companions funded
by its own furniture and fashion trade. Three roles:

- **Retail Volunteer** — at least one full day a week, 9am to 5pm, on a day that
  suits you. 18 or over, full induction with health and safety.
- **Street Souls Outreach** — their outreach service for people sleeping rough.
- **Furniture and Upcycling** — workshop restoration alongside the companions.

**Greenwich and Lewisham are new boroughs**, taking coverage to 19 of 33.

**The open question this raises.** Emmaus Lambeth and Emmaus Barnet are separate
charities with their own volunteering, and neither is in scope. Adding them takes
the count from 32 to 34. Flagged rather than decided: it is a scope change, and
§2 A5 fixes scope at the 32 in `seed.py`. The same question will arise for any
federated charity.

**And a note on the build refusing.** Two length caps fired while writing this — a
203-character summary against a 200 cap, and an over-long induction. The build
exited 2 and wrote nothing, which is the schema invariant added earlier in this
session doing exactly what it was added for. Before that change, both would have
shipped.

Data stands at **57 roles across 24 of 32 charities**, and the site at 150 pages.

> Files: `data/orgs/emmaus.json`, `data/site-bundle.json`

## 5s. Crisis — the best screening policy found, and two invariants firing

Charity 1082947. Skylights in Tower Hamlets, Croydon and Brent. Their volunteering
page is the most complete **policy** statement anywhere in this set:

> Not all our roles require references, but those volunteering in our Skylights and
> Head Office do. We will ask for one reference... Some of our roles may require a
> disclosure check; you will be able to see this on the role description. Some
> roles may require a basic disclosure check, others may require an enhanced
> disclosure check.

**First `references: True` and first `references: False` in 60 roles**, from the
same page. That field has been null everywhere until now.

Three roles: Welcome and Reception, One-to-One Member Support (three to six
months, DBS required), and Charity Shop. All `status: "unknown"` — their page says
roles appear on the live board only when a Skylight has vacancies, so availability
is genuinely not stated between listings.

### Two build invariants fired. One was mine, one was the invariant's.

**Mine.** I set `dbs: "none"` on the shop role, reasoning that their policy names
only some roles as needing a check and shops are not among them. The build refused:
*"claims no DBS needed without a verified source"*. It was right — that is my
inference, not their statement, and `none` means the page says no check is needed.
Corrected to `unknown` with the reasoning recorded in `unsupported_fields`. This is
exactly the invariant's purpose and the first time it has caught a real error
rather than a deliberate test.

**The invariant's.** It refused `volunteer.crisis.org.uk` as a foreign domain
against `crisis.org.uk`. That is Crisis's own volunteering board — a subdomain, not
a third party. The check compared netlocs exactly, so every charity running
`volunteer.`, `jobs.` or `shop.` on its own domain would have been refused. Now
compares registrable domains, with the leading dot that stops
`evil-crisis.org.uk` matching.

Data stands at **60 roles across 25 of 32 charities**, and the site at 157 pages.

> Files: `data/orgs/crisis.json` (new), `site/build.py`, `data/site-bundle.json`

## 5t. St Mungo's — the richest record in the set, and a splitting decision

Charity 1149085. 450+ volunteers last year. The only charity that publishes
**actual shift times per borough**, which makes it the first record where the
"posts, not organisations" principle had to be applied to a single advert.

Their one Outreach Volunteer advert covers three boroughs with genuinely different
propositions:

| | Shifts | Extra |
|---|---|---|
| Westminster | 6–10am or 8.30pm–midnight, any day | one shift a month minimum |
| Brent | 6–10am, Monday to Friday | they would rather you lived in Brent |
| Ealing | Monday 10pm–2am, or Wed and Fri 5–8am | **a driving licence is required** |

**Recorded as three roles, not one.** Spec §5 says you volunteer for a particular
morning in a particular building — and a 6am Brent shift and a Monday-midnight
Ealing shift needing a car are not the same offer. Collapsing them into one record
with a paragraph of caveats is exactly the charity-level thinking the project was
rebuilt to escape.

Two more roles: **First Response** (go out in pairs to find people reported
through StreetLink) and **Gardening Sessions**.

**Facts worth having beyond the records:**

- A **two-hour online core training** for most roles — the most concrete induction
  figure found anywhere.
- **London travel refunded up to a zones 1-6 travelcard.**
- They ask about **spent convictions** under the ROA 1974 exemption — second
  charity after Solace.
- *"If you volunteer with us more than 3 months, we also offer professional
  references"* — they give references rather than demand them, the inverse of
  Crisis.
- A genuinely thoughtful accessibility note: outreach shifts inside stations *"may
  be a suitable volunteering option for those with physical disabilities or
  accessibility needs"*. No other charity says anything like it.

**DBS is `unknown` on all five, deliberately.** Their FAQ refers to DBS
requirements without stating them per role, and after the Crisis shop mistake I am
not inferring a check from the fact that a role involves vulnerable adults. The
ROA exemption is recorded as the fact it is.

Data stands at **65 roles across 26 of 32 charities**, and the site at 166 pages.
Twenty-one boroughs, thirteen of fourteen activity types, four overnight roles.

> Files: `data/orgs/st-mungos.json` (new), `data/site-bundle.json`

## 5u. Centrepoint — a source that no longer exists

Their own volunteer page describes the *process* — application, then a discussion
meeting about the role — and names no roles at all. It also says they are
**Investing in Volunteers accredited since 2024**, which is an externally audited
standard for volunteer management and the only such accreditation found in the set.

The role detail is on **vInspired, a platform that has ceased operating.** Finding
4e in its most severe form: not a stale listing on a live portal, but a listing on
a dead one. Both records declare it and sit at confidence 0.7 and 0.5.

The **Volunteer Mentor** role is the longest commitment in the dataset — matched
with one young person for a **full year**. That comes from an NCVO case study of
their programme rather than their own page, which the record says.

Data: **67 roles across 27 of 32 charities**, site at 171 pages.

## 8. Unconfirmed notices now say so on the classified, not just the article

Writing Centrepoint pushed the low-confidence count to **11 of 67 notices — 16%**,
which was enough volume to expose a real honesty gap.

An article page prints "Confidence low" in its byline. **A classified printed
nothing.** So a reader scanning a column of sixty-seven notices had no way to tell
which eleven rested on a thin page, a third-party portal or a defunct platform.
Disclosure on the detail page only is disclosure to the people who were already
going to read it.

Classifieds below 0.7 confidence now carry, under the particulars:

> *We could not confirm these particulars — read their own page before you go.*

Two tests, deliberately in both directions: every low-confidence notice must
carry it, and confident notices must not. A marker that appears everywhere marks
nothing — the same reasoning that rejected a `RECRUITING NOW` stamp.

> Files: `data/orgs/centrepoint.json` (new), `site/build.py`,
> `site/static/app.css`, `site/test_build.py` — 160 tests now

## 5v. Shelter — the first verified "no check needed", and an under-18 role

The best-documented charity in the set on age and screening. Four roles across
twelve London shops (Crouch End to Turnham Green) and their local hubs.

**The first verified `dbs: "none"` in 71 roles.** Their shop advert says it
outright: *"You will not undergo a criminal record check for this role."* The build
invariant has required a verified source for that claim since v0.2 and this is the
first record that legitimately satisfies it — a week after it caught me inferring
the same thing for a Crisis shop with no such statement.

**The first under-18 role.** Shops take volunteers from **14** with a parent or
carer's consent, and young volunteers are supervised by two adults. Services,
campaigns and fundraising are 18+. Minimum ages in the dataset now run 14, 18, 19
and 25 — all null at the start of this session.

Also worth recording, because no one else says it: *"you can volunteer if you
receive benefits"*, expenses reimbursed in full, and *"committed to making sure
that no-one misses out because they can't afford to volunteer."*

## 9. The apply_url invariant needed an escape hatch, not a relaxation

Shelter's shop opportunities live on **Better Impact** — a genuine third-party
volunteering platform, not a Shelter subdomain. The invariant refused, correctly,
and exposed a design problem: charities routinely run volunteering on hosted
systems (Better Impact, Reach, Assemble), so as written the rule made every one of
them unpublishable.

The fix is acknowledgement rather than prohibition. A foreign `apply_url` passes
only when **both** hold:

- `provenance.reviewed_by_human` is true, and
- the record names the platform in `unsupported_fields`

A machine-extracted record can satisfy neither, which is the point — the risk the
invariant exists for is a model inventing a URL or a link going stale, not a
charity choosing a hosted platform.

Verified all three ways: it builds with the declaration, exits 2 without it, and
exits 2 when `reviewed_by_human` is false.

Data stands at **71 roles across 28 of 32 charities**, site at 178 pages.

> Files: `data/orgs/shelter.json` (new), `site/build.py`,
> `data/site-bundle.json`

## 5w. Big Issue Foundation — a third seed flag corrected, and a duplicate I made

`seed.py` flagged the seeded URL as `reachvolunteering.org.uk` — a third-party
platform, which would have had the weekly check watching the wrong site. Their
Reach page is dated **2019**. Corrected to their own current volunteering page.
Third seed flag confirmed this session; all three were right.

One role: the frontline office in London — admin, and the front desk where vendors
come in. Training in safeguarding, health and safety and data protection; some
roles ask for a reference, though they do not say which.

**A mistake of mine worth recording.** I created `big-issue-foundation.json` while
`seed.py` had already made `the-big-issue-foundation.json`, taking the org count to
**33 when spec §2 A5 fixes scope at 32.** Merged onto the seeded id and the
duplicate deleted. Nothing caught it except the build's own count line — worth a
test if the org set is ever edited by hand again.

## 10. One rule for off-domain links, checked the same way twice

Big Issue exposed a case neither the invariant nor the test handled: their
volunteering page is on **bigissue.com** while the Foundation's site is
**bigissue.org.uk**. The same organisation on two domains — not a third-party
platform at all, so a declaration saying "platform" would have been untrue.

Both checks now require the same thing: **the foreign domain must be named** in
`provenance.unsupported_fields`.

- The build invariant looked for the word "platform" — too loose and too narrow at
  once.
- The test looked for phrases like "comes from" — so an honest declaration worded
  differently failed, and a vague one passed.

Naming the domain is unambiguous and auditable. It immediately caught a real gap:
New Horizon's records said "UCL's student volunteering platform" in prose but never
named `studentsunionucl.org`. Now they do, as do Ace of Clubs
(`volunteer.lambeth.gov.uk`), Shelter (`app.betterimpact.com`) and Big Issue.

Seven roles in the set now cite an off-domain source, and every one names it.

Data stands at **72 roles across 29 of 32 charities**, site at 193 pages.

> Files: `data/orgs/the-big-issue-foundation.json`, `site/build.py`,
> `site/test_build.py`, `data/orgs/new-horizon-youth-centre.json`,
> `data/orgs/ace-of-clubs.json`, `data/orgs/shelter.json`,
> `data/site-bundle.json`

## 5x. Housing Justice — the best find of the tail

Pages dated 2026 and three genuine routes, filling two gaps at once.

- **Citadel Volunteer** — *one to two hours a week*, north, north-east and
  south-east London. Walking alongside someone who has just been housed, because
  keeping a tenancy is a different problem from getting one. The lowest-commitment
  regular role in the set.
- **Volunteer Host** — take a destitute migrant into your spare room. **Second
  `own_home` role** after Depaul's Nightstop. They arrange the DBS check and
  provide immigration advice.
- **Winter Night Shelter** — every night from January to April, Croydon and
  elsewhere. **Only the second `seasonal_window`** after Glass Door, so the
  CLOSED FOR THE SEASON stamp now appears on more than one charity.

Data: **75 roles across 30 of 32 charities**, site at 202 pages.

## 11. Two integrity tests — and one found a bug older than my own

I said last batch that the duplicate org file I created deserved a test. It does,
and the test found something worse.

`test_the_organisation_set_matches_the_seed_exactly` reconciles the files on disk
against `seed.py`, checks the filename matches the id inside it, and asserts the
count is 32. `test_every_role_id_belongs_to_its_organisation` catches a role filed
under the wrong charity — the build refuses an *unknown* `org_id` but not a wrong
one.

**What it found:** `whitechapel-mission.json` on disk against
`the-whitechapel-mission` in the seed. A naming drift dating from the original
Phase 0 research, months before this session. **Both sets counted 32**, so no count
check could ever have caught it — only reconciling the two sets by id. Renamed;
role ids left alone so the `/role/` URLs stay stable.

**A note on my first attempt.** The test grepped `seed.py` for `"id":` and found
nothing, because seed.py keys on organisation *names* and derives ids with
`slug()`. It then reported the empty set as the failure — a test that cannot read
its own reference is worse than no test. It now imports the module.

> Files: `data/orgs/housing-justice.json` (new),
> `data/orgs/the-whitechapel-mission.json` (renamed), `site/test_build.py`,
> `data/site-bundle.json` — 162 tests now

## 5y. The last two — and a wrong sentence on every page

**All 32 organisations have now been read.** The final two place no notices at all.

**Streets of London** is a grant-giving charity. Its volunteer page lists no roles
and sends you elsewhere, rather well: *"there are at least 150 different
homelessness organisations in London alone, so don't hesitate to try several!"*

**Cardboard Citizens** (charity 1042457) is a theatre company whose members have
experienced homelessness. Its get-involved route is sponsored events — The Big
Tramp is an all-night walk with a **£39 entry fee**. Paying to enter a fundraiser
is not volunteering, and listing it as one would misdescribe both.

Both recorded with **`link_status: "link_only"`**, which the schema has had since
v0.2 for exactly this. They stay in scope at 32 and simply never appear in a
column. No new field, no exclusion, no empty pages.

`seed.py` excluded StreetLink and Homeless Link up front by judgement; these two
were found by evidence. Four of the original 34 are not sources of roles.

### The sentence this corrected

The publisher's notice — on **every page of the site** — read *"30 of 32 charities
read so far"*. That implied two were unread. All 32 have been read; two place
nothing. It now reads *"30 of 32 charities place notices here"*.

A small wording change, but it was the site's central honesty claim and it had
quietly become false the moment the research finished. The test that checks the
banner was matching the old wording, so it was enforcing the wrong sentence
faithfully.

> Files: `data/orgs/streets-of-london.json`,
> `data/orgs/cardboard-citizens.json`, `site/build.py`, `site/test_build.py`,
> `docs/scrapability.md`, `data/site-bundle.json`

## 12. Documentation brought back in line with reality

With Phase 0 done, the spec, handover, README and scrapability notes all described
a project blocked on data. All four updated, and **every number verified against
the repo** rather than taken from my own edits — which caught two I had wrong:
HANDOVER said 11 build invariants and the spec listed 10, when the code has 12.

Spec §6.1 now carries the finding on the full sample rather than the first eleven
roles. The conclusion survives — **a screening filter still cannot work**, 16% of
roles state a DBS against 18% in the original sample — but the gap is a habit
rather than an impossibility, which is a different argument for the launch email.

## 13. A third of the corpus was unreachable from the front page

The three doors filtered by **exact commitment match**, so they led to 50 of 75
notices. `flexible` (18), `monthly` (4) and `fortnightly` (3) had pages of their
own that nothing linked to.

The labels already promised ranges. "Every week or so" plainly covers fortnightly
and monthly — the "or so" is doing that work. So doors are now sets, not equality:

| Door | Holds |
|---|---|
| One day | `one_off` + flexible |
| Every week or so | `weekly`, `fortnightly`, `monthly` + flexible |
| Something bigger | `long_term` + flexible |

**`flexible` appears behind every door**, because it means the volunteer chooses —
someone wanting a single day can do a flexible role once, someone wanting it weekly
can do it weekly. That is a promise, not an absence.

### Which exposed a schema anomaly, and 5 mislabelled records

`dbs`, `status` and `who_can_apply` all have an `unknown`. **`commitment` did
not** — so "their page does not say how often" was being filed as `flexible`.
**Five of eighteen flexible roles were really unknowns**, and under the new rule
they would have appeared behind every door, promising a match the page cannot
support. Exactly what the `activity: "varies"` rule forbids.

`commitment: "unknown"` added, the five reclassified. It behaves like `varies`:
shown on `/all/`, behind no door. Flexible is a promise and unknown is an absence,
and they now behave oppositely, which is the honest distinction.

Sixth schema addition forced by real data, after `required_unspecified`,
`own_home`, `varies`, `practical` and `eligibility`.

Doors now: one-day 21, weekly 58, bigger 17, all 75 on `/all/`. Filter pages went
from 92 to 171 — every one with results, since empty combinations are never
emitted.

> Files: `pipeline/schema.py`, `site/build.py`, `pipeline/prompts/extract.md`,
> `london-volunteering-spec-v0.3.md`, `HANDOVER.md`, `README.md`,
> `docs/scrapability.md`, five org files, `data/site-bundle.json`

## 14. The client bundle shipped four times more than it read

With 75 roles, `data.js` reached **101KB**, loaded on every results page. It
carried all 23 fields of every record — including **28KB of provenance**, which
the client cannot use for anything.

That was a leftover. When `app.js` rebuilt cards itself it needed the whole
record; since it started filtering server-rendered notices by `data-id` it needs
only the nine fields `match()` tests, plus the title for the lookup field.

| | before | after |
|---|---|---|
| raw | 101.3 KB | **24.1 KB** |
| gzipped | 15.7 KB | **4.2 KB** |

Two tests, in both directions. One asserts the bundle carries nothing outside the
nine — the other asserts every field `app.js` reads is actually shipped, because
trimming too far breaks filtering **silently** rather than loudly.

It also forced a distinction the test suite had been eliding. `data()` now reads
`data/site-bundle.json`, the full records as the build sees them; `shipped()`
reads `dist/assets/data.js`, what the browser receives. Six tests were asserting
on a reader's experience using the client's slim view, which happened to work only
because the two were identical.

### Verified at full scale while I was there

The map holds: 20 lit boroughs, 20 badges, **zero overlaps**, no console errors, 75
classifieds intact. The badge placement was stress-tested synthetically at 33 and
has now met the real thing.

Page weight, all gzipped: front page **2.6 KB**, `/all/` 30 KB, assets 37.7 KB
cached once. 276 pages, 13 MB — well inside Cloudflare's 20,000-file limit.

> Files: `site/build.py`, `site/test_build.py` — 164 tests now

## 6. `HANDOVER.md`

A 3,200-word cold-start briefing for anyone picking this up with no context —
current state, the five findings from reading real charity pages, the twelve
decisions already settled and why, working practices, and the things that will
bite. Every number in it verified against the repo.

> File: `HANDOVER.md` (new)

---

## Suggested commits

Splitting them keeps the history legible:

```powershell
git add site/ pipeline/ README.md
git commit -m "Fix two Windows-only bugs: locale file encoding, and the glibc-only %-d strftime flag"

git add wrangler.jsonc package.json docs/hosting.md
git commit -m "Deploy as an assets-only Cloudflare Worker; SITE_URL from the environment"

git add data/orgs/the-passage.json data/site-bundle.json
git commit -m "The Passage: 8 roles, and correct their redirecting volunteer URL"

git add HANDOVER.md
git commit -m "Add a cold-start handover document"

git push
```

## Then verify

```powershell
$env:PYTHONPATH = "pipeline"
py -m pytest pipeline/ site/ -q      # expect 156 passed
py site\build.py --serve             # 64 pages
```

If the jsdom tests report *skipped* rather than passed, `npm install` did not run.
Those are the ones that caught the map failing to draw, so they are worth having.

## And the deployment

- Cloudflare → the Worker → Settings → **Variables**: `SITE_URL` =
  `https://daily.8houses.co.uk`
- Check `https://daily.8houses.co.uk/bot` resolves — nothing should touch a
  charity's server until it does
- Check any page's `<link rel="canonical">` shows your domain, not `example.org`
- Check `https://daily.8houses.co.uk/about/` loads, which proves `html_handling`
- Check `https://daily.8houses.co.uk/nonsense` shows the paper's own 404

## Still outstanding, unchanged

- `py pipeline\census.py`, then read `docs/census.md` — the next real decision
- `ANTHROPIC_API_KEY` as a GitHub repository secret
- Settings → Actions → General → allow Actions to create pull requests
- A spend limit in the Anthropic console
- Remove the three stale files from Claude Project knowledge:
  `eight-houses-community-preview.html`, `index-filters-snippet.astro`,
  `categories.js`
