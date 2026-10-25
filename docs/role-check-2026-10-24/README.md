# Role check, 24 October 2026

All 47 charities checked against live pages (boards and feeds first), in nine parallel batches (`findings/A to I.json`). `apply.py` validated and applied them: schema, quote checks, the 8-word copyright rule, site rules. Procedure: `docs/claude-update-playbook.md`.

**Result in `data/orgs` (uncommitted, awaiting approval):** 157 roles (145 before). 37 updated, 18 new, 6 retired, 1 kept as status unknown, 100 unchanged. 56 records carry `reviewed_by_human: false` (the changed and new ones). Tests: 440 passed, 12 skipped. Site build passes.

**Not approved yet.** Nothing has been set to `reviewed_by_human: true`. Committing is your approval of the data as it stands.

## Spot-check (`verify1-3.json`)
54 quotes sampled in live pages: 0 wrong, 25 weak, 29 ok. Weak means the quote is on the page but is an org-wide or generic statement rather than role-specific. Mostly Crisis: the generic "Crisis at Christmas 2026 applications are now open" banner, and the org-wide "over 18" FAQ. For the Crisis Christmas roles the Rosterfy feed does list them as published with no close date, so `open` stands. Four claims were overridden to unknown/empty (see `OVERRIDES` in `apply.py`): Solace peer mentor `references`, Solace counsellor `interview`, Shelter hub support `eligibility`, Crisis healthcare `eligibility`. Expect a similar weak rate in unsampled records.

## Biggest changes
- **Crisis:** 15 new roles (13 London Christmas offers, Brent Skylight admin, Green Fingers Lead at Skylight London), 1 retired (`crisis-christmas-kitchen`, replaced by Christmas Chef Volunteer), several corrections. Shop roles stay one collapsed record.
- **Retired (6):** `crisis-christmas-kitchen`, `shelter-community-volunteer`, `spear-fundraising` (page says not recruiting and describes no role; "closed" is the softer alternative), and New Horizon's `nhyc-kitchen`, `nhyc-esol-tutor`, `nhyc-sports-assistant` (page now lists paid jobs only; the charity may advertise elsewhere, so worth asking them).
- **Kept as unknown:** Housing Justice winter shelter (retire evidence was only a stand-in).
- **Status changes:** HandsOn London Wrap Up London and Community Day to open; Single Homeless Project Wellbeing and Employment to open; Solace Next Steps Peer Mentor to open (closing date read as 6 November 2026, dd/mm); Ace of Clubs lunch role to unknown; SCT office and fundraising to unknown.
- **Other:** St Mungo's Outreach now lists Brent, Bournemouth, Ealing, Reading (list page and role page disagree; role page followed); Big Issue commitment to unknown; Simon Community live-in `interview` to null.

## Read failures and gaps
- **Cardboard Citizens:** homepage fetch carried casino spam; nothing read, record untouched.
- **The Upper Room:** site returned an empty body; record untouched.
- **West London Mission:** its volunteer_url is the paid-jobs page; no replacement found; needs a human or a phone call.
- **Salvation Army:** national pages list no London-specific roles; vacancy portal returned empty. No roles held.
- **FirmFoundation, Streets of London, Barons Court:** no volunteer roles described; none held.
- **Your Place:** four role descriptions are .docx and unreadable; one-line summaries only.

## Left as published or not applied
- The Big Issue frontline office (volunteering page on bigissue.com, charity site bigissue.org.uk).
- `volunteer_url` changes: only reported (West London Mission). Shelter walk-for-home's direct Better Impact link is queued for review and the role links to the charity page meanwhile.
- SCT "Online Shop" role not added (no location on the page).

## Things to look at
- HandsOn London lists "Saturday 21 October"; 21 October 2026 is a Wednesday, so the entry is stale or mistyped.
- Emmaus FAQ says shifts run Tuesday to Saturday, but role pages show Monday, Thursday and Friday. Roles left as they were.
- Simon Community `flexible` commitment rests on borderline wording.
- Crisis Canning Town postcode kept from the old record (the feed only says "Canning Town Warehouse").
- Several agents re-fetched URLs with an added query string when the fetch tool refused repeats.

Files: `findings/`, `validation-report.json`, `sample1-3.json` and `verify1-3.json` (spot-check), `apply.py`, `BRIEF.md`.
