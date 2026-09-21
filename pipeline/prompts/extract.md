You are reading one UK charity's volunteering page and recording the roles it
describes, so that a signposting site can help people in London find something they
can actually do.

The site does not take applications and does not vet charities. It links people to
this page. Its only job is to describe accurately what is on offer, so someone does
not travel across London to discover they needed a DBS check, or that the programme
closed in March.

## The two rules that matter more than completeness

**1. Unknown beats a good guess.**

If the page does not state something, record it as `unknown` (for `dbs` and
`status`) or `null` (everywhere else). Do not infer, do not draw on what similar
charities usually require, and do not fill a field because it looks incomplete.

This matters most for:

- `screening.dbs` — only `none` if the page explicitly says no check is needed. A
  page that simply doesn't mention DBS is `unknown`, not `none`. If the page says a
  DBS check is required but doesn't say which level, use `required_unspecified` —
  that is a real and useful fact, and collapsing it to `unknown` throws it away.
- `screening.min_age` — only if stated as a number.
- `status` — `open` only if the page says roles are available. A page that lists
  roles without saying whether they're recruiting is `unknown`. **Where a page's
  prose describes role types but its vacancy list is empty or says something like
  "opportunities coming soon", trust the vacancy list: record the roles as
  `closed`, not `open`.** Describing a role is not offering it, and akt's page
  does exactly this — several hundred words on mentoring and Pride events above an
  opportunities section with nothing in it.

  **And if a closure notice looks old, say so in `page_notes`.** West London
  Mission still carries a notice headed "COVID-19 update" saying they are not
  taking volunteers. Record `closed`, because that is what the page says, but a
  reader deserves to know the notice may be years out of date rather than being
  quietly turned away by it.
- `next_intake` — only an actual date on the page.

A record full of `unknown` is useful: it tells a human reviewer to look, and it
tells the site to link rather than assert. A record full of plausible inventions is
worse than no record at all.

**2. Write your own words, never theirs.**

`what_youd_do` must be an original sentence describing the activity, not the
charity's sentence with the words moved around. Never copy a phrase of eight or
more consecutive words from the page. The pipeline checks this mechanically and
rejects extractions that fail, so paraphrasing properly saves a retry.

Write it as what a volunteer would physically be doing: "Cook and serve lunch for
around 80 guests, then help clear down" — not "opportunities within our catering
support function".

## What counts as a role

One record per distinct thing a person could sign up to. If the page describes a
kitchen shift, a shop assistant post and a trustee vacancy, that is three records
with different commitments and screening.

Do not create a record for:

- Donating money, goods, or signing a petition — those aren't volunteering roles.
- A generic "get in touch to volunteer" invitation with no described activity. If
  the whole page is that, return an empty `roles` array and say so in `page_notes`.
- Paid jobs. If it's advertised with a salary, skip it.

## Field guidance

`commitment` — how often, not how long each time.
`one_off` a single occasion · `flexible` ad hoc, no pattern · `weekly`,
`fortnightly`, `monthly` a recurring slot · `long_term` a role with a minimum term
of several months or more, such as mentoring, hosting or trusteeship.

`typical_shift_hours` — hours per occasion. For hosting or overnight roles, the
duration of the stay.

`when` — up to three. Choose from the enum only. If the page says "flexible" or
gives no timing, use `["flexible"]`.

`specific_times` — the page's actual stated timing, briefly: "Saturdays 9am–12pm",
"Tuesday and Thursday mornings", "October to March". Null if not stated.

`activity` — exactly one, the dominant activity. Use `practical` for gardening,
decorating, maintenance and similar hands-on work; `shop_warehouse` is for a shop
floor or a stockroom and does not cover it. A role that genuinely spans two has
been described too broadly; pick the one a volunteer would spend most time on. Use
`varies` only for a rotating programme or calendar where the page deliberately does
not fix the activity — not as an escape hatch when you are merely unsure.

`commitment` — `flexible` means **the volunteer chooses** how often, and the page
must actually say so. If the page simply does not mention frequency, that is
`unknown`, not `flexible`. The two behave oppositely on the site: a flexible role
appears behind every door because any frequency works; an unknown one behind none,
because we never offer a match we cannot support. Five records were filed as
flexible when they were really unknowns.

`location_type` — use `own_home` where the volunteering happens at the volunteer's
own address, such as hosting someone overnight. That is not the same as `remote`.

`eligibility` — a bar on *who may apply*, kept separate from `skills`, which is
what someone can do. Record it only where the page states a restriction: a
women-only service, a role requiring lived experience of homelessness, a host role
requiring a spare room. If the page merely says a quality is welcome or preferred,
that is not eligibility and belongs nowhere.

`postcode_district` — the outward code only (`SE1`, `E8`, `N16`), and only if the
page gives an address or clear location. Null for remote roles and when unstated.

`apply_url` with `url_specificity` — if there is a link or form specific to this
role, use it and set `role`. If the only link is the general volunteering page, use
that and set `org_volunteer_page`. If neither, use the page you are reading and set
`org_volunteer_page`. Never invent a URL.

`seasonal_window` — month numbers, for roles that only run part of the year: winter
night shelters, Christmas appeals, summer events.

## page_notes

Anything a human reviewer should know and the schema can't hold: the page looked
out of date, roles were described ambiguously, there was a contradiction, the page
mentioned a waiting list. This is not published. Keep it under 300 characters.
