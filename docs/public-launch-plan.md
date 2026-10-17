# Public launch plan: LinkedIn and Instagram

Prepared 16 October 2026. Proposed plan, not a launch sign-off.

## Recommendation

Prepare for a small public launch over five working days, with the date conditional on accurate listings and a working mobile journey. Allow longer if the source review uncovers substantial changes. Keep the current newspaper/scrapbook design and minimal homepage. Prioritise trustworthy content and a clear route to a charity enquiry.

## What was checked

- The production homepage, `/find/`, `/all/` and social preview image returned HTTP 200 on 16 October. This establishes availability, not working interactions.
- Live homepage metadata describes 76 posts at 30 charities, uses the correct canonical domain and includes a social sharing image.
- Local data contains 76 roles across 32 organisation records. All roles carry a human-review flag; that is stored metadata, not proof of a current review. Two organisation records have no roles.
- Twenty-six organisation records have last-successful-check dates in August or September; six have dates of 8 October. Source-check dates do not establish that every individual role or application destination was checked.
- Stored role statuses are 55 open, 15 unknown, four closed and two seasonally closed. Do not advertise all 76 as currently available; the generated site also applies freshness rules.
- The saved review report dated 8 October originally contained 25 items. After synchronising its decisions, 19 remain: 15 proposals and four incomplete checks. The source snapshot is still from 8 October, so refresh it before making further decisions.
- A targeted source review of five charities is recorded in [the 16 October catalogue review](catalogue-review-2026-10-16.md). It corrected unsupported detail and checked twelve roles; the other 25 charities with roles still need a current review before claiming the full catalogue is freshly verified.
- Refresh and deployment workflows exist. Their latest successful runs and current production parity were not verified.
- No charity contact records were found in the local organisation files. This does not establish whether emails have been sent elsewhere.
- Local discovery code stores answers and saved roles in the browser and states that it does not track enquiries. No launch measurement system was established by this review.
- Previous notes report a touch-swipe problem without subsequent real-device confirmation. Treat this as a historical risk requiring a fresh check, not a confirmed current defect.

## Before the announcement

| Priority | Work | Done when | Responsibility |
|---|---|---|---|
| Essential | Reconcile the saved review queue and local edits | Each relevant change has a documented decision and the intended release content is clear | Technical/content preparation; founder resolves ambiguous editorial choices |
| Essential | Review the published catalogue against charity sources | Each launch listing has a working destination and accurate role, location, commitment and recruitment wording; uncertainties remain explicit | Content review |
| Essential | Check all roles featured in launch posts again shortly before posting | Every example is currently supported by its source; no unsupported availability or eligibility claims | Content review |
| Essential | Test the complete mobile journey | Homepage → questions/directory → details → save/undo/shortlist → charity link works on real iPhone and Android browsers and from the social apps | Technical fixes plus founder/device testers |
| Essential | Check basic accessibility and resilience | Keyboard access, visible focus, readable text, scrolling, non-swipe actions and reduced motion work; denied storage fails gracefully; directory remains usable without JavaScript | Technical preparation |
| Essential | Verify the launch release | Appropriate automated checks pass, intended changes are released with approval, and the live site is checked afterwards | Technical preparation; founder approves publication |
| Essential | Verify ongoing maintenance | Latest refresh outcome is understood, review items have an owner, failures are visible and approved updates reach production | Technical preparation and founder |
| Essential | Check public promises and correction route | About/data/bot wording matches actual operation; correction mailbox works and someone owns replies | Founder with technical help |
| Before promotion | Reconcile charity outreach | Establish who has already been contacted; follow the project's outreach policy for remaining listed charities; fix the old bot URL in the email template; record corrections and opt-outs | Founder sends approved correspondence |
| Before promotion | Check social landing and previews | LinkedIn preview has the intended image/title; Instagram profile and Story destinations work on the actual account | Founder with prepared assets |

Review catalogue accuracy before investing in promotional assets. If reviewing the full catalogue is too much for the intended date, agree a smaller, freshly reviewed launch selection and clearly handle the remaining records. A smaller reliable release is a viable scope choice.

Keep the existing homepage copy and red primary action. Explain the product more fully in social posts and the About page.

## Launch content pack

Use one consistent positioning sentence: a free guide to volunteering with London homelessness charities, helping people find roles that fit their time and location, with enquiries made directly to each charity.

Avoid claims of charity partnership, vetting, guaranteed placement or volunteer impact without evidence. Check how charity logos are used, particularly before placing them in promotional artwork.

### LinkedIn

- Prepare one founder-led launch post: why you built it, who it helps, how it works and one invitation to find a role.
- Include a direct link to the homepage and one clear screenshot or short captioned demonstration.
- Prepare a follow-up post demonstrating two or three freshly verified roles with different commitments.
- Check the URL using [LinkedIn Post Inspector guidance](https://www.linkedin.com/help/linkedin/answer/a6269011) before publishing; site metadata alone does not confirm the actual platform preview.
- Choose a posting time when you can answer comments. Use your existing audience knowledge; do not delay for an assumed universal best time.

### Instagram

- Prepare one five-slide carousel: the difficulty of finding a suitable role; what 8 Houses does; choosing practical preferences; a verified example; invitation to visit the site.
- Prepare one short vertical screen recording, around 15–25 seconds, showing the actual journey with readable captions.
- Prepare two or three launch Stories with a clear destination. Check that the Link sticker is available and works on your account. Meta describes Story links in its [announcement](https://about.fb.com/ja/news/2021/10/linkaccessstickers/).
- Update the profile description and website destination; pin the introductory post and retain a useful introduction in a Highlight where available.
- Use the existing cream, ink and red identity. Use screenshots, typography and illustrations that explain the service. Include image descriptions where supported and captions for speech.

Suggested pack: two LinkedIn posts, one carousel, one short video and three Story frames. More content is optional.

## Suggested sequence

| When | Focus | Outcome |
|---|---|---|
| Working days 1–2 | Reconcile records and queue; review charity sources; establish outreach status | A trustworthy launch catalogue and a short list of actual defects |
| Working day 3 | Real-device journey and accessibility checks; targeted fixes; release validation | A candidate ready for founder approval |
| Working day 4 | Finalise social pack, profile links, previews and a simple measurement baseline | Everything ready to publish |
| Working day 5 | Final source spot-checks; approved release if needed; public announcement | Launch while someone is available to respond |
| Launch +2–3 days | Publish the practical demonstration; review questions and failures | Address confusion while interest is fresh |
| Launch +7 days | Review usage and feedback; refresh sources and fix the largest issue | Evidence-led priorities for the next week |

Founder user testing was previously deferred in the product roadmap. A small voluntary rehearsal with three to five first-time visitors would be useful: ask them to find a plausible role and explain the next step without coaching. This is recommended, not a newly imposed requirement to resume building or an excuse to postpone indefinitely. Real-device functional checks remain essential.

## Measurement and first-week ownership

- Record platform reach, available link-click counts, useful questions and reported errors in a simple weekly note.
- Decide whether to add minimal site measurement. If so, define visits by channel and charity-link opens, verify actual reporting, and make public privacy wording accurate before enabling it. Tracking parameters alone do not collect data.
- Distinguish a charity-link click from an enquiry, application or placement. Claim outcomes only with evidence.
- Set aside time each day during launch week for comments, corrections and broken links, then establish a sustainable weekly review slot.
- Have the previous working release available and know how to withdraw or correct an inaccurate listing quickly.

## Can wait

Accounts, a native app, paid promotion, advanced travel-time matching, a larger catalogue, extra animation and a newsletter can wait until usage demonstrates a need. A broader design revision is not a prerequisite for this launch.

## Founder decisions and actions

1. Choose a provisional launch week and the accounts to use, with the date conditional on the essential checks.
2. Confirm charity outreach already completed and who will handle corrections after launch.
3. Test the site on your real phone from LinkedIn and Instagram; arrange another device if possible.
4. Approve final wording, assets and any production changes, then publish the posts.
5. Reserve time to respond and review the first week's results.

Confidence: 90% in this prioritisation. Current production interactions, source accuracy, account settings, outreach history and workflow success still require the checks listed above. This planning pass did not modify the application, refresh charity sources, publish content or deploy changes.
