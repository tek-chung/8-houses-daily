# The 8 Houses Daily: product plan

## Purpose

Help a first-time volunteer find a suitable London homelessness volunteering role,
understand what it asks of them, and make an enquiry through the charity's website.
Build trust in 8 Houses through the usefulness and integrity of that experience.

The product promise: **Find a way to help that fits your life.**

## Experience

Homepage → explore two or three examples → three practical questions → ranked
notices → optional shortlist → compare → visit the charity's enquiry page.

The directory remains a prominent alternative. Questions, saving and comparing
are optional: a visitor who finds a suitable role can act immediately.

## 1. Make the foundations trustworthy

- Resolve the mismatch between generated commitment groups and browser filtering.
- Make freshness suppression work from a clean build; remove unsupported claims
  such as "Checked this week" when the underlying records do not support them.
- Fix extraction verification field names and the handling of disappeared roles.
- Review source links, recruitment status and requirements for launch candidates.
- Keep content updates behind human review until live dry runs are inspected.
- Show real source-check dates and provide a simple correction route.

Acceptance: the site cannot imply a role is open, eligible, recent or suitable
without evidence; directory and guided discovery agree about the same records.

## 2. Make each notice easy for a beginner to understand

Start with role, charity, one concrete description, location, schedule and actual
commitment. Keep age, eligibility restrictions, onboarding requirements and
uncertainty visible when they can affect a decision. Expand secondary detail.

Distinguish hours per shift, frequency, minimum duration and onboarding effort.
Flexible frequency does not establish that a role can be tried once. A flexible
hosting role can still require training, checks and an ongoing commitment.

Preserve the moving-newspaper identity with restrained illustration, generous
spacing and quiet motion. Make the main next step stronger than decorative detail.

Acceptance: a new volunteer can explain what they would do, what time it takes,
what is required and how to enquire after reading a notice.

## 3. Refine discovery and matching

- Offer Skip, Save and View details alongside swipe gestures.
- Add undo, clear save feedback and a direct route to the three questions.
- Ask availability, commitment and preferred area; support "not sure" throughout.
- Show the visitor's answers and allow quick edits.
- Separate requirements from preferences. Explicitly incompatible roles should
  not appear as good matches; unknowns must remain labelled as unknowns.
- Explain the two or three relevant reasons for each suggestion without percentages
  or claims that a placement is guaranteed.
- Use borough matching first. Add travel estimates only after role locations are
  supported by evidence; remote and own-home roles need distinct treatment.
- When suitable results run out, explain the limitation and offer a specific
  preference adjustment. Do not silently weaken a visitor's requirements.

Acceptance: known fit ranks ahead of uncertainty, conflicts are explained, saved
roles are not repeatedly recommended, and every action works without swiping.

## 4. Turn the shortlist into an enquiry

At three saves, invite a comparison and allow continued exploration. No minimum
shortlist size is needed to enquire. Compare roles on the same dimensions: activity,
place, schedule, duration, requirements, recruitment and source-check date.

Provide a clear next step for each record: view the role, open the application
form or register interest, according to the verified destination. Describe what
the visitor will find where known. Keep enquiry handling on charity websites.

Optional help can include questions to ask when the charity's page is silent.
Describe unfamiliar terms such as induction and DBS in plain language. Add
expenses, training and beginner suitability only when the source supports them.

Acceptance: visitors understand that Save is private, opening a link is not an
enquiry, and the charity decides eligibility and placement.

## 5. Test with people, then polish for launch

Begin with five first-time volunteers as a qualitative research round, not a
statistical conversion experiment. Compare the guided route with the directory,
vary the order, and avoid coaching participants through the interface.

Ask them to find a role they could realistically enquire about. Observe confusion,
unsuitable choices, unmet information needs and the hand-off to the charity. Do
not require a real enquiry merely to complete a usability test.

Revise the largest recurring problems, then test another small round. Check real
mobile swipe behaviour, keyboard and screen-reader use, reduced motion, blocked
storage, no JavaScript, slow connections and returning visitors.

Launch gate: no critical journey defects; all launched candidates have reviewed
links and truthful status; visitors can find a plausible role and understand the
next step without help. This is a proposed gate, not an observed result.

## 6. Learn whether the product helps

Distinguish discovery started, questions answered, role saved, shortlist viewed,
charity page opened and self-reported enquiry. These are different events.

Use a small, privacy-conscious measurement plan. Avoid collecting detailed
preferences or personal information by default. Determine how to measure actual
enquiries with optional user follow-up or charity collaboration before claiming
impact. Self-reports should be labelled and their response bias acknowledged.

Publish evidence-backed outcomes if and when they exist. Do not imply charity
endorsement or partnership without agreement. Put a modest "An 8 Houses project"
credit behind a clear account of the project's purpose.

## Build order

First release: trustworthy records and consistent filtering; concise beginner
notices; reliable discovery, undo and shortlist; accurate outbound next steps;
mobile and accessibility checks; usability testing and launch readiness.

After evidence of use: better geographic matching, additional useful preferences,
and modest improvements to returning visitors' saved roles. Keep accounts, native
apps, notifications and automated personalisation out of the first release unless
research demonstrates a specific need.

## Confirmed product direction

- Initial visitors will come from LinkedIn and Instagram.
- The intended audience is first-time volunteers who do not know what is available
  or whether the requirements fit their lifestyle. This is the founder's stated
  audience need; independent user research has not yet established it.
- User testing is deferred at the founder's request. It remains a proposed launch
  check, rather than a blocker to building locally.

## Current implementation

The guided route, compact beginner notices, one-at-a-time questions, explicit
matching explanations, exclusion of known preference conflicts, undo, local saved
roles and the comparison prompt are implemented. Save and skip remain reachable
while reading on phones. Enquiry links lead directly to charity websites.

Directory filtering now agrees with the generated commitment groups, and shift
lengths are available to the browser's sorting controls. Every build recalculates
freshness from source-check dates. This does not refresh the underlying sources:
the existing charity records still need a current review before launch.

Location discovery now uses seven broad London areas, with multiple selections
and remote volunteering. Stated postcodes rank ahead of charity coverage, and
individual notices retain their postcode. The directory uses the same mapping;
its borough map remains available. TfL links support a personal journey check.
Automatic travel-time or direct-connection ranking still requires better venue
data and a travel origin.

Validation on 5 October 2026: 171 Python tests passed, all three JavaScript behaviour
suites passed, and the mobile question, save, undo and comparison flows were checked
in the browser. These checks do not establish real-world enquiry conversion or
replace testing with first-time volunteers.

## Supporting research

NCVO's 2023 Time Well Spent research reports time commitment, lack of suitable
roles and insufficient flexibility among reasons people did not proceed with an
enquiry. It supports a focus on practical fit, not a conclusion that swiping is
the best interface. This is national research, not a study of this product.

https://www.ncvo.org.uk/news-and-insights/news-index/time-well-spent-2023/volunteering-barriers-enablers/
