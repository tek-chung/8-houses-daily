# Scrapability census

**Generated** 01 September 2026, 22:50 UTC  
**Surveyed** 32 organisations. No extraction ran; nothing was written to org data.

## Verdict

| Verdict | Count | Means |
|---|---:|---|
| clean | 17 | Ready to extract |
| thin | 5 | Real page, but no role detail on it — treat as link-only |
| redirected | 1 | URL has moved — update it before extracting |
| dead | 9 | Broken — needs a new URL |

## What to do next

**Only 17 of 32 pages are ready.** Extract those, and treat the rest as link-only for now — a card that links out honestly is better than a card with invented detail. Revisit the `thin` and `redirected` ones by hand; they are usually a wrong URL rather than a hard problem.

## Per organisation

| Organisation | Verdict | Main text | Boilerplate | Role links | CMS date | Note |
|---|---|---:|---:|---:|---|---|
| [Ace of Clubs](https://aceofclubs.org.uk/volunteer/) | clean | 1,848 | 27% | 0 | — |  |
| [Cardboard Citizens](https://cardboardcitizens.org.uk/) | clean | 60,000 | 74% | 2 | — |  |
| [Centrepoint](https://centrepoint.org.uk/support-us/volunteer) | clean | 1,988 | 68% | 1 | — |  |
| [Crisis](https://www.crisis.org.uk/get-involved/volunteer/) | clean | 9,898 | 36% | 6 | — |  |
| [Emmaus](https://emmaus.org.uk/support-us/volunteering/volunteer-roles/) | clean | 12,605 | 52% | 5 | — |  |
| [Groundswell](https://groundswell.org.uk/volunteer-opportunities/) | clean | 3,720 | 64% | 2 | — |  |
| [HandsOn London](https://www.handsonlondon.org.uk/volunteer) | clean | 6,143 | 17% | 3 | — |  |
| [New Horizon Youth Centre](https://nhyouthcentre.org.uk/get-involved/jobs/) | clean | 1,789 | 81% | 0 | — |  |
| [SPEAR](https://www.spearlondon.org/get-involved/be-a-volunteer/) | clean | 1,778 | 52% | 0 | — |  |
| [Shelter](https://england.shelter.org.uk/support_us/volunteer) | clean | 3,972 | 26% | 2 | — |  |
| [Simon Community](https://www.simoncommunity.org.uk/) | clean | 1,487 | 44% | 1 | — |  |
| [Single Homeless Project](https://www.shp.org.uk/get-involved/volunteer/) | clean | 3,274 | 49% | 1 | — |  |
| [Spires](https://www.spires.org.uk/) | clean | 454 | 92% | 1 | — |  |
| [St Mungo's](https://www.mungos.org/get-involved/volunteer/) | clean | 862 | 87% | 2 | — |  |
| [Stonewall Housing](https://stonewallhousing.org/volunteer-opportunities/) | clean | 2,006 | 67% | 0 | — |  |
| [Thames Reach](https://thamesreach.org.uk/support-us/volunteer/) | clean | 2,568 | 54% | 1 | — |  |
| [Women at the Well](https://www.watw.org.uk/volunteer) | clean | 1,944 | 33% | 1 | — |  |
| [Depaul UK](https://www.depaul.org.uk/nightstop-volunteer/) | thin | 1,158 | 64% | 0 | — | no role sub-pages found and little text — likely a 'get in touch' page rather than described roles |
| [Glass Door Homeless Charity](https://www.glassdoor.org.uk/listing/category/volunteer-roles) | thin | 0 | 100% | 3 | — | only 0 chars, but it is real prose — this page genuinely doesn't describe roles. Link-only. |
| [North London Action for the Homeless](https://www.nlah.org.uk/volunteer/) | thin | 82 | 84% | 1 | — | only 82 chars, but it is real prose — this page genuinely doesn't describe roles. Link-only. |
| [Spitalfields Crypt Trust](https://sct.org.uk/support-us/volunteer/) | thin | 280 | 95% | 1 | — | only 280 chars, but it is real prose — this page genuinely doesn't describe roles. Link-only. |
| [Streets of London](https://www.streetsoflondon.org.uk/get-involved/volunteer) | thin | 693 | 40% | 0 | — | no role sub-pages found and little text — likely a 'get in touch' page rather than described roles |
| [The Passage](https://passage.org.uk/volunteering/) | redirected | 1,228 | 38% | 1 | — | now serves https://passage.org.uk/get-involved/volunteering/ |
| [Housing Justice](https://housingjustice.org.uk/donate-or-get-involved/volunteer) | dead | 0 | — | 0 | — | HTTP 404 |
| [Manna Society](https://www.mannasociety.org.uk/how-you-can-help/volunteer-time/) | dead | 0 | — | 0 | — | HTTP 404 |
| [Providence Row](https://www.providencerow.org.uk/pages/68-volunteering-opportunities) | dead | 0 | — | 0 | — | HTTP 404 |
| [Solace Women's Aid](https://www.solacewomensaid.org/get-involved/volunteer-with-us/) | dead | 0 | — | 0 | — | HTTP 403 |
| [The Big Issue Foundation](https://reachvolunteering.org.uk/org/big-issue-foundation) | dead | 0 | — | 0 | — | HTTP 403 |
| [The Connection at St Martin's](https://www.connection-at-stmartins.org.uk/volunteer/) | dead | 0 | — | 0 | — | HTTP 403 |
| [The Whitechapel Mission](https://whitechapel.org.uk/volunteering) | dead | 0 | — | 0 | — | HTTP 403 |
| [West London Mission](https://www.wlm.org.uk/pages/category/volunteer-opportunities) | dead | 0 | — | 0 | — | ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'www.wlm.org.uk'. (_ssl.c:1010) |
| [akt](https://www.akt.org.uk/volunteer/) | dead | 0 | — | 0 | — | HTTP 403 |

## Role sub-pages found

These are the pages extraction would read in addition to the landing page. Worth a skim — if something here is obviously not a role, tighten the filters in `fetchpage._ROLE_LINK_BLOCK`.

**Cardboard Citizens**
- https://cardboardcitizens.org.uk/whats-on-filter/member-workshops-all/
- https://cardboardcitizens.org.uk/whats-on-filter/member-workshops-18-30s/

**Centrepoint**
- https://centrepoint.org.uk/ending-youth-homelessness/real-stories/gills-story-volunteering-has-given-me-another-dimension

**Crisis**
- https://www.crisis.org.uk/get-involved/volunteer/volunteers-week/
- https://www.crisis.org.uk/get-involved/volunteer/volunteer-in-our-shops/
- https://www.crisis.org.uk/get-involved/volunteer/volunteer-in-our-local-services/
- https://www.crisis.org.uk/get-involved/volunteer/volunteer-stories/bulletins/francois-story/
- https://www.crisis.org.uk/get-involved/volunteer/volunteer-stories/bulletins/isabels-story/
- https://www.crisis.org.uk/get-involved/volunteer/volunteer-stories/bulletins/nathaniels-story/

**Emmaus**
- https://emmaus.org.uk/about-us/our-trustees/
- https://emmaus.org.uk/what-we-do/personal-development/
- https://emmaus.org.uk/support-us/volunteering/
- https://emmaus.org.uk/greenwich/volunteer-role/trustee/
- https://emmaus.org.uk/greenwich/volunteer-role/kitchen-volunteer/

**Glass Door Homeless Charity**
- https://www.glassdoor.org.uk/winter-night-shelter-volunteers
- https://www.glassdoor.org.uk/lived-experience-group
- https://www.glassdoor.org.uk/other-volunteer-opportunities

**Groundswell**
- https://groundswell.org.uk/hhpa/
- https://groundswell.org.uk/become-a-volunteer/

**HandsOn London**
- https://www.handsonlondon.org.uk/corporate-volunteering
- https://www.handsonlondon.org.uk/community-volunteering
- https://www.handsonlondon.org.uk/volunteer?1ddbbe1c_page=2

**North London Action for the Homeless**
- https://www.nlah.org.uk/wp-content/uploads/2022/01/NLAH-VolunteerApplicationForm2022.docx

**Shelter**
- https://england.shelter.org.uk/support_us/volunteer/frequently_asked_questions
- http://england.shelter.org.uk/support_us/volunteer/volunteer_stories

**Simon Community**
- https://www.simoncommunity.org.uk/volunteering/

**Single Homeless Project**
- https://www.shp.org.uk/what-we-do/next-steps/lived-experience/peer-mentoring/

**Spires**
- https://www.spires.org.uk/volunteer

**Spitalfields Crypt Trust**
- http://sct.org.uk/shops-cafe/charity-shops/

**St Mungo's**
- https://www.mungos.org/get-involved/volunteer/current-volunteering-opportunities/
- https://www.mungos.org/get-involved/volunteer/volunteering-faqs/

**Thames Reach**
- https://thamesreach.org.uk/2025/06/05/volunteering-dianas-story/

**The Passage**
- https://passage.org.uk/get-involved/volunteering/faqs/

**Women at the Well**
- https://www.watw.org.uk/s/2025-Volunteer-Application-Form.docx

