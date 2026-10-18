# Role check, 17 to 18 October 2026

All 47 charities checked against their live pages (boards and feeds first, then pages). Every claim about screening, status, times, season or eligibility carries a quotation in `findings/`. `apply.py` validated and applied it: schema, the 8-word copyright rule, and any claim without a usable quotation forced to unknown.

**Result in `data/orgs`:** 145 roles (88 before) across 43 charities. 74 updated, 64 new, 7 retired, 2 kept as status unknown. 144 are shown on the site; St Mungo's Outreach Westminster names only Bournemouth and Reading, so it is hidden by design.

**Approved by Tek on 18 October 2026:** all changed and new records are marked `reviewed_by_human: true`, including the 11 direct platform links (Crisis, Centrepoint, Shelter, Thames Reach) and the 13 charities added today. The 7 retirements and the status-unknown downgrades below are part of that approval.

## Judgement calls worth knowing

- **Spot-check:** 51 sampled quotes were checked in a browser. 2 were wrong and 5 weak; those were corrected (see `OVERRIDES` in `apply.py`). The other quotes were not independently checked, so expect a similar error rate (roughly 1 in 10 weak or wrong) in the unsampled records.
- **Kept as status unknown, not deleted:** Housing Justice winter shelter (its own pages offer no night shelter), West London Mission services (its only source was a defunct closure notice). HandsOn London Community Day is also unknown: one reading said closed, a later browser read said community days run to 14 November.
- **Left as published:** The Big Issue frontline office (its volunteering page is on bigissue.com, the charity site on bigissue.org.uk).
- **Whitechapel Mission:** the pages say "over 21", recorded as eligibility wording rather than a minimum age of 21.
- **Not applied:** `volunteer_url` changes for HandsOn London (`/community-volunteering`), Cardboard Citizens (`/get-involved/`) and The Upper Room (`/volunteer/`, unconfirmed). West London Mission has no volunteering page on strides.org.uk.
- **Conflict left visible:** St Mungo's Outreach Westminster lists only Bournemouth and Reading, but the role page body still names Brent and Ealing shifts.
- **Not read:** FirmFoundation (no volunteering page found). NEWway Project was held back because its homepage served casino spam. Neither has a record of roles.
- **Logos:** 12 of the 13 new charities have one, redrawn small from the charity's own site. Emmaus SLC and Bench Outreach used white lettering that vanishes on cream, so those were recoloured dark; replace them with the charity's own dark version if you have one. Evolve Housing + Support has none (its mark is a white icon) and shows a blank plate. Charities without a logo show a blank plate rather than failing the build.
- **Places:** `site/locations.py` now reads London neighbourhoods and "South London"-style labels as London, so pages' own wording is stored verbatim in `stated_places`.
- **Provenance:** `source_url` for platform roles is the role page, and the platform host is named in `unsupported_fields`, which the build requires for any off-domain source.

Files: `findings/` (agent output with quotations), `validation-report.json`, `verify1.json` and `verify2.json` (spot-check), `apply.py` (validator and applier, kept for the audit trail), `BRIEF.md`.
