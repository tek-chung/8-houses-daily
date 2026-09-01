# The 8 Houses Daily — site build

    python site/build.py            # -> dist/
    python site/build.py --serve    # build, then http://localhost:8000

Python rather than Astro, which spec §17 named. The pipeline is already Python, and
one maintainer carrying two toolchains means two dependency trees to rot, two CI
setups and two things to relearn in six months. This is one file, no dependencies,
emitting plain HTML. The output is what Astro would have produced: static files.

## What it emits

| Pattern | From |
|---|---|
| `/` | doors, live counts, five-minute actions |
| `/{commitment}/` | one per door with roles |
| `/{commitment}/{borough}/` | only where roles actually sit in that borough |
| `/{commitment}/{activity}/` | one per activity present |
| `/role/{id}/` | detail + provenance + `VolunteerOpportunity` JSON-LD |
| `/charity/{id}/` | all of one charity's roles |
| `/help/` `/about/` `/data/` `/five-minutes/` | hand-written |
| `sitemap.xml` `robots.txt` `404.html` | generated |

**Only combinations with results are emitted.** Spec §14 said pre-render one- and
two-blank combinations; real data shows that generating empty ones would produce
hundreds of thin pages, which is an SEO liability and a promise the site can't keep.
Empty combinations resolve client-side and carry `noindex`.

## Progressive enhancement, not a SPA

Every page renders its roles server-side. With JavaScript off: all roles visible,
all links work, every pre-rendered URL indexable. JavaScript only makes filtering
instant and adds the borough map. `app.js` reads its starting state from `<body>`
data attributes, so a deep link is correct before it runs and stays correct after.

## Build invariants

`check()` refuses to build — exit 2, nothing written — on any of:

- an organisation that has opted out still appearing in the build
- a role claiming `dbs: "none"` without `screening.dbs` in `verified_fields`
- a role with no URL to link to, which would make the button lie
- a role linking only to a homepage while claiming high confidence

These are the failures that would hurt someone rather than look untidy. A promise
enforced by the build is worth more than one written in a document.

## The design

A newspaper, because volunteering roles *are* classified advertisements — "WANTED:
kitchen volunteer, Southwark, Saturdays, apply within" is the format papers used
for exactly this content for two centuries. Boxed, ruled and dense beats a card
grid, because print hierarchy comes from size, weight, caps and rules rather than
from grey boxes.

**Palette.** Newsprint cream, warm near-black ink, one spot red. Three tiers of ink,
not four — papers have ink and less ink, and hierarchy is typographic. Verified to
WCAG AA on every surface; worst ratio 5.10:1, re-derived from `app.css` by a test.

**Type.** Fraunces for display, Literata for body, Archivo for labels. All three
chosen for legibility at the sizes actually used: Bodoni Moda's hairlines vanished
below 24px, EB Garamond's low x-height made 17px read like 14px, and Oswald's
condensed caps at 9px were the least readable thing on the site. Blackletter is
gone — beautiful at 3em, muddy at 30px, and a masthead is the most-read type there
is. Roman mastheads are entirely orthodox.

**Stamps mark exceptions only.** `TEAMS ONLY`, `CLOSED FOR THE SEASON`, `RECRUITING
NOT STATED`. There is no `RECRUITING NOW` stamp, because that is the default and
stamping it would flatten the signal.

**The engravings.** Hand-drawn SVG line art keyed to each role's activity — a
steaming pot, a guttering lamp, a swaying coat, a lit fanlight. They loop gently and
hold still under `prefers-reduced-motion`. No photography anywhere: §15 forbids
poverty tourism, and stock imagery of people sleeping rough would be exactly that.
A test asserts no `<img>` tag exists on the site at all.

**`/help/` deliberately breaks all of it.** No drop caps, no "Situations Vacant", no
search box, no data payload — a double-ruled public notice with plain type and three
phone numbers. The period voice is charming for a volunteer and would be actively
wrong for someone sleeping rough. A test fails if any of the decoration leaks in.

## Mobile

Mobile-first: base rules target a 360px phone and wider layouts are additive.
Breakpoints at 480, 640, 700 and 900.

| Width | What changes |
|---|---|
| base | coupon as form rows, single column, stamps in the flow |
| 640px | the coupon becomes the prose sentence |
| 700px | three lead columns, stamps struck across the ad, justified type |
| 900px | two columns of classifieds, two-column article prose |

Two real bugs found by measuring rather than assuming:

- **iOS focus-zoom.** Safari zooms the whole viewport when a focused control is
  under 16px. Every control is 16px on touch; denser type is gated behind
  `pointer:fine`, where it cannot happen. Density is a mouse affordance anyway.
- **Stamps over text.** Struck diagonally they look right on a wide ad and cover the
  particulars on a narrow one. Below 700px they sit in the flow. Plus
  `overflow-x:hidden`, because rotated negatively-offset elements scroll a phone
  sideways.

There is also a short-viewport query so the masthead doesn't eat a landscape phone,
a print stylesheet, and `prefers-contrast` support.

## Tests

    python -m pytest site/test_build.py -q

61 tests, grouped by who breaks if they fail: **honesty** (a visitor is misled about
what we know), **reachability** (a visitor can't get to something), **a11y** (a
visitor can't use it), **seo** (the acquisition channel degrades silently),
**responsive** (a phone breaks), **engravings**, **readability**.

Three are worth knowing about:

- **Contrast** parses the palette out of `app.css` and computes WCAG ratios against
  every surface. An earlier build shipped `--paper-3` at 3.51:1 on cards, below the
  4.5:1 floor, while carrying the location line on every card and the whole footer.
- **Engravings** exist because `plate()`, four SVGs, their CSS and the keyframes
  were all written and wired to nothing. Every page built; all 89 tests passed; the
  signature element of the design was absent from the site. A suite that checks
  structure has no opinion on whether a decoration exists.
- **Readability** enforces a floor: nothing under 11px, no tracking above 0.14em on
  small text, body at 18px or more, and no blackletter.

## The district map

Real borough outlines from ONS / Ordnance Survey administrative geography, with
the Thames threaded through them. Generated by `site/tools/build_map.py` into
`data/london-map.json`, which is committed so the site build needs no network.

    python site/tools/build_map.py --fetch   # only when boundaries change

**The Thames comes from the boroughs, not a river dataset.** In the source file the
boroughs meet along the middle of the channel, so the seam between north-bank and
south-bank boroughs *is* the river — 1,869 shared edges — at exactly the precision
of the shapes it has to line up with. A separate river dataset would be a second
set of rounding errors and would not sit on the banks. A test samples the path and
checks every riverside borough against its real bank, because a line putting
Southwark on the north side would mislead rather than decorate.

**Attribution is required, not decorative.** ONS boundary data is OGL plus the OS
OpenData Licence, and both Crown copyright statements must appear wherever it is
shown. They print under the map and a test checks for them.

**Fidelity is measured.** London spans 58.5km across 1000 user units, so one unit
is about 58m and one pixel at full width. Boroughs simplify at 0.0005° (56m,
sub-pixel); the river gets 0.0003° because its sinuosity is its character and it
is one path rather than 33 — worst deviation 20m, a third of a pixel.

**No text inside the SVG.** Counts are HTML badges positioned by percentage over
the shapes. An earlier version put labels inside the viewBox and they rendered at
43px, because font-size in a scaled viewBox resolves in user units. The field is
pinned to `aspect-ratio: 1000 / 773` so the SVG cannot letterbox and drift the
badges off their boroughs.

**Badges are placed, not just positioned.** Borough centroids cluster where
boroughs are small, so an iterative pass separates overlapping badges along
whichever axis needs least movement, draws a leader line where one has been pushed
clear of its shape, and falls back to the count alone when separation cannot
succeed. Widths are estimated from character counts rather than measured, because
measuring forces a layout pass per render and jsdom computes no layout, so a
measured version could not be tested. `site/js/labels.js` pushes it with twenty
badges in one corner and eight against the sheet edge.

**The shapes are decorative; the chips are the control.** The SVG is `aria-hidden`
and the borough chips beneath it are real buttons. Thirty-three focusable paths
would put thirty-three duplicate tab stops in front of a keyboard user for a view
of something the chips already do. On a phone there are only chips — a 360px-wide
London is neither readable nor tappable.

## Browser smoke tests

    npm install          # jsdom
    python -m pytest site/test_build.py -q

The Python suite checks the HTML it generated; it cannot execute the page. That
blind spot hid two serious bugs at once:

1. `toggleBlank()` dereferenced `#b1w`, a wrapper id the prototype markup had and
   the newspaper coupon does not. It threw on every results page — which meant the
   district map never drew, and the page simply looked empty.
2. Behind that exception sat a second copy of the card markup in `app.js`, drifted
   from `build.py`'s: old class names, old copy. Fixing the first bug let it
   overwrite all eleven server-rendered classifieds.

Neither was visible to any test. `site/js/smoke.js` now loads each built page in
jsdom and reports anything the console would show, plus tile counts, classified
counts and filled coupon slots. The tests skip if node or jsdom is unavailable, so
`npm install` matters.

There is now only one card renderer. `app.js` filters the server-rendered
classifieds by `data-id` rather than rebuilding them, and changing the commitment
navigates to the pre-rendered page, because a results page holds only its own
notices.

## Preview

`build.py` also writes `dist/preview.html`: `/all/` with every asset inlined, so it
opens standalone. It exists because a hand-maintained prototype alongside a
generated site is two sources of truth, and they had already drifted.

## Before deploying

1. Set `BASE_URL` in `build.py`. It is `https://example.org` and sitemap plus
   canonicals depend on it.
2. Deploy `dist/` to Cloudflare Pages (or any static host). Build command
   `python site/build.py`, output directory `dist`.
3. Put `https://8houses.co.uk/bot` up before the crawler's first real run.
