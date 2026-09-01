# Launch email to charities

Spec §16 requires contacting every listed organisation before the first real run.
Two reasons, and the second is the more important one: it converts a possible
grievance into a relationship, and it's the cheapest available route to fixing
Finding 4 in `scrapability.md` — that no charity page states its screening
requirements, which leaves that facet unusable on observational data.

Send from **tek@8houses.co.uk**. One at a time, addressed to a person where the
site names a volunteer coordinator. Thirty-two emails is an evening.

**Before sending:** `https://8houses.co.uk/bot` must exist. It's the contact URL in
the crawler's user agent, and a charity that wants us to stop needs somewhere to go.
A single page saying what the crawler does and how to opt out is enough.

---

## Template

**Subject:** Listing your volunteering roles on a free London signpost site

---

Hello,

I'm building a small free website that helps people in London find volunteering
they can actually commit to — filtered by how much time they have, where they are,
and what they'd be doing. It links straight through to each charity's own
volunteering page. I don't take applications, I don't vet charities, and there's no
advertising or funding behind it.

I'd like to include [ORGANISATION]. Three things you should know:

**How I keep it accurate.** Once a week an automated check reads your public
volunteering page and notes whether anything has changed — roles, timings, whether
you're recruiting. If something significant changes, I review it by hand before the
site updates. The site shows when each listing was last checked, and if I stop
maintaining it the pages say so rather than going quietly stale.

**How the crawler behaves.** It identifies itself as `SomewhereToHelpBot`, honours
your robots.txt, and makes one request per second — about the load of one person
reading a couple of pages. Details at https://8houses.co.uk/bot.

**How to change or remove anything.** Reply to this email and I'll fix or remove a
listing within a few days. If you'd rather not be listed at all, say so and that's
the end of it — no negotiation.

**One thing that would genuinely help.** While reading volunteering pages across
London I noticed almost none of them state their screening requirements up front.
That matters, because it's often the thing that decides whether someone can
volunteer, and people find out weeks into an application. If you have a moment,
four short answers would let me show it properly:

1. Do your volunteer roles need a DBS check, and is it basic or enhanced?
2. Is there a minimum age?
3. Do you ask for references or an interview?
4. Roughly how long from first contact to a first shift?

If it's easier to say "it varies by role", that's a useful answer too and I'll
show it that way.

Thank you for the work you do — and for reading a cold email about a website.

Tek
tek@8houses.co.uk

---

## Variant: organisations that only take teams

For The Whitechapel Mission and any others the census flags as team-only. Replace
the "I'd like to include" paragraph with:

> I'd like to include [ORGANISATION], and I want to get one thing right in
> particular: I understand you take volunteer teams rather than individuals. The
> site flags that clearly on the listing, so people applying on their own aren't
> sent to you and turned away. If I've misunderstood how it works, please tell me.

## Variant: organisations whose volunteering URL I couldn't find

For Simon Community, Cardboard Citizens, New Horizon Youth Centre, and anything the
census returns as `thin` or `dead`. Add:

> I couldn't find a page describing your volunteering roles — only your homepage.
> Rather than guess, I'd rather ask: is there a page I've missed? If you don't
> currently recruit volunteers, tell me and I'll leave you off entirely.

---

## Tracking

Record replies in the org file rather than a spreadsheet, so consent travels with
the data:

```jsonc
"contact": {
  "emailed": "2026-09-02",
  "replied": "2026-09-04",
  "consent": "happy_to_be_listed",   // happy_to_be_listed | opt_out | no_reply
  "screening_answers": true          // did they answer the four questions
}
```

An `opt_out` must remove the organisation from the build, not just hide the card.
Worth adding an assertion to the site build that fails if an opted-out org appears
in the bundle — a promise enforced by code is worth more than one in a document.
