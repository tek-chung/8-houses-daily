# Role check, 31 October 2026

All 47 charities re-checked in nine batches (`findings/A to I.json`), starting from the 24 October data. The brief added lessons from the last run: role-specific evidence only, `who_can_apply` needs a statement, no URL tricks, no retirement without a quote. `apply.py` validated and applied the findings. Procedure: `docs/claude-update-playbook.md`.

**Result in `data/orgs` (uncommitted, awaiting approval):** 163 roles (157 before). 29 updated, 6 new, 0 retired, 97 unchanged. Tests: 440 passed, 12 skipped. Nothing is marked `reviewed_by_human: true`.

## Crisis: read afterwards, in the main session
The Crisis agent could not read the Rosterfy feed (see its findings), so I read the whole feed myself at your request: 10 pages of 8, 78 offers, last page with no next page, so complete. 47 are London offers, 30 are elsewhere.
- **Matches:** 26 of our 31 Crisis roles match a live offer; DBS, interview and minimum age agree with the feed on every one. The collapsed shop role is backed by 17 live London shop offers.
- **No longer listed:** `crisis-christmas-arts` and `crisis-skylight-green-fingers-lead` are gone from the feed, so both are set to status unknown (not closed or retired: absence is not a quote). Please decide whether to retire them.
- **Updated:** `crisis-skylight-welcome` times now match the feed (London 4 hours a week; Croydon Thursdays, ideally 10am to 4pm), with closing dates noted (11 and 13 November); Brent admin closes 20 November.
- **Not added as separate roles:** Nurse, Pharmacist, Physiotherapist, Podiatrist and Nail Technician Christmas offers (the healthcare record already covers the group, and nails sit with hair and nails); the Croydon Welcome offer (already covered by the Welcome record).
- **E-Commerce and Collections:** the feed does not mark them as London (Canning Town warehouse; no place), so the weekly automated job would drop them. Kept as they were.
- This was a feed read only: the Crisis role pages are client-rendered and were not read, and no spot-check was done on Crisis this run.

## What changed
- **`who_can_apply`:** `individual` becomes `unknown` on many roles (Centrepoint, Thames Reach, Ace of Clubs, AKT, Emmaus, Groundswell, Kingston, All People All Places, Housing Justice Citadel, St Mungo's new roles), because no page states it. This is the main reason 29 records changed. It has a side effect: a changed record is unreviewed, so the build falls back to the charity's volunteering page for roles that previously linked directly (Centrepoint gardening x2, Thames Reach x3, Shelter Walk for Home). Approving them restores the direct links.
- **New (6):** St Mungo's Housing First Peer Volunteer (Haringey) and Creative Activities Volunteer (Westminster), both open and closing 25 November; Connection at St Martin's Day Centre Volunteer (closed, applications for Dec to Feb "open soon"); SCT Online Shop (unknown, location not on the page); Single Homeless Project Christmas Day Hostel Volunteer (unknown, from an undated Instagram embed); Your Place Community Partnerships Volunteer (unknown, page dated 2023). Drop the last three if you would rather not carry stale roles.
- **Place and status:** St Mungo's Outreach is back to Bournemouth and Reading only (the Brent and Ealing placements are gone), so it is hidden by the London rule. Centrepoint gardening roles set to unknown (no longer in the feed, pages still load). Depaul roles get `stated_places: London`.
- **Other corrections:** Whitechapel Breakfast Challenge age "over 18" (was 21); HandsOn Wrap Up London reworded and seasonal window widened to November to December; Upper Room UR4Meals DBS set to basic (from the homepage form); Shelter Walk for Home links to its own role page.
- **Left unknown, not retired (for you to decide):** Housing Justice winter shelter, West London Mission service (volunteer_url is a paid-jobs page, no replacement found), C4WS Jobs Club Mentor, Shelter Hub Support.

## Spot-check (`verify1.json`): inconclusive
30 claims sampled. 4 ok, 6 wrong, 20 unreadable (the fetch tool refuses a URL already fetched earlier in the session, so most pages could not be re-opened; they need a fresh session). The six wrong all cite the Emmaus Greenwich overview page, where the quoted age, DBS and references text is not present. Those values (18+, basic DBS, two references) are unchanged from the 17 October batch and are an org-wide claim; check them against the Emmaus role pages before relying on them.

## Read problems and flags
- Cardboard Citizens homepage still serves casino spam: possibly compromised; nothing read.
- Salvation Army: portal returned nothing; no London roles held. Whitechapel booking diary and Your Place role documents unreadable.
- North London Action for the Homeless: recruiting notice is headed August 2026 and still open.
- All People All Places roles say "Posted 23 Sept 2025" yet remain open.
- HandsOn London lists odd dates (a "Saturday 21 October"); Emmaus FAQ shifts disagree with role pages.
- Solace Next Steps Peer Mentor closes 6 November 2026 (interview date already passed; may close early).
- Several quotes sit next to bold markup or curly apostrophes on the live pages.

Files: `findings/`, `validation-report.json`, `sample1.json`, `verify1.json`, `apply.py`, `BRIEF.md`.
