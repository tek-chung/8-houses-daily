# Guided volunteering discovery

The homepage links to `/find/` for first-time volunteers and `/all/` for the
existing directory. The newspaper design and homepage films remain in place.

The journey shows three examples, asks one question at a time about availability, commitment and reachable areas,
then orders the remaining roles using those explicit answers. Visitors can skip
or save with buttons or horizontal swipes, compare their saved roles at any time,
and visit a charity's website immediately. Three saves prompt a comparison without
ending browsing. Visitors can undo their last save or skip. On phones, save and
skip stay within reach while reading a notice. No applications or enquiries are handled by 8 Houses.

Saved role IDs and answers are stored only in this browser's localStorage under
`8houses-volunteer-discovery-v1`. If storage is blocked, the journey still works for
that visit and tells the visitor. Skips are temporary and do not train the ranking.

## Ranking and information limits

- Stated commitment, timing and reachable-area matches increase a role's position.
- Unknown particulars receive no match credit. Known contradictions are excluded
  until the visitor explicitly explores beyond their preferences; differences are
  disclosed. An unknown location is never called nearby.
- Flexible frequency does not establish that a single visit is possible. Roles
  involving a minimum term or hosting cannot match “Try it once”. Regular includes weekly,
  fortnightly, monthly and long-term; the notice shows the actual minimum term.
- Open roles get a small preference. Seasonal, oversubscribed and unconfirmed roles
  remain available with caveats. Closed and team-only roles remain in the directory.
- Eligibility, screening, source uncertainty and the original charity link are
  preserved in the notice. Preferences do not establish that someone is eligible.
- Location uses seven broad browsing areas, distinct from TfL fare zones. Visitors
  can select several reachable areas and/or remote volunteering. Stated postcodes
  outrank inferred charity coverage, which is labelled as requiring venue confirmation.
  Unknown districts never inherit an organisation's potentially unrelated venues.
  TfL journey-planner links let visitors check their usual route. Journey times,
  direct connections and walking distances are not calculated.
- Freshness is recalculated from source-check dates on every build, even if the
  saved freshness report is missing or outdated. Where suppression is active, timing is unknown and recruitment is
  unconfirmed in ranking, consistent with the notice's suppressed particulars.

The prototype measures no enquiries. Opening an external link is neither an
application nor evidence that someone contacted the charity.

## Validation

Build with `python site/build.py`. Run the existing Python suite and
`node site/js/discovery-test.js` and `node site/js/directory-test.js` after building.
These exercise undo, comparison prompts, persistence, removal, questions, ranking,
conflicts, unknown information, blocked storage, and directory filtering parity.
Browser checks cover the real journey and mobile layouts.

Test with first-time volunteers before replacing the directory: can they identify
a suitable role, understand what it asks of them, and reach the charity's enquiry
page? Follow-up is needed to establish whether an enquiry actually happened.

## Concise layout and sharing

The discovery masthead is smaller. Cards show place, timing and commitment, with
requirements and source dates behind a disclosure. Match explanations are also
expandable; known conflicts remain expanded when exploring beyond preferences.
Coverage information is behind “About these notices”, while a publication
suspension remains visible.

Visitors can share a single `/role/<id>/` link from each role using the device share
menu, with copying or a selectable link as fallbacks. No saved IDs or preferences
are included. Cancellation does not copy a link. Local preview links are explicitly
labelled as working only on the current device.

“Save image” creates a 1080 × 1350 portrait PNG with the role, charity, summary,
commitment and location. The preview offers a normal download link and can also be
saved from the image itself. Availability and requirements still need confirming.
Local exports are marked as previews. This does not publish anything to social media.

All pages have a 1200 × 630 branded preview image and absolute social metadata.
Set `SITE_URL` to the real public HTTPS address when building for deployment.
The default example address is a placeholder, and external platform previews
cannot be checked against localhost.

Run `node site/js/sharing-test.js` alongside the other checks. It covers native
sharing, cancellation, copying, clipboard rejection, local preview disclosure and
exclusion of private state. The portrait image was rendered in the browser and
its 1080 × 1350 dimensions and download-link content checked. The in-app browser's
download-event observer timed out; successful file saving through that observer
was not established.

API references: [device sharing](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share)
and [canvas image export](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toDataURL).

## London areas

Central; North; North-west; East; South-east; South & south-west; West.
`site/locations.py` is the single mapping used by discovery and the directory.
Central includes EC/WC, W1, SW1 and SE1 districts plus Westminster/City borough
coverage. These are approximate product areas, not station-level boundaries.
Other held districts use their borough grouping. All 33 boroughs have a grouping.
The stored borough answer migrates to its broad area without changing saved IDs.

The directory's area filter can be shared via `/all/?area=central` (and equivalent
commitment routes). Existing borough pages and the precise borough map remain.
Unknown in-person locations are excluded by a directory area filter; remote and
home-hosting roles remain available. Discovery may offer unknown locations with
an explicit caveat, ranked behind stated venues. Remote-only excludes known
in-person roles, and hybrid roles explain that attendance may be needed.

The grouping is an editorial choice, informed by the network's cross-London
connections; it does not imply an easy commute from every point in an area.
Transport reference: [TfL's official Tube and rail map](https://content.tfl.gov.uk/standard-tube-map.pdf).
