"""Static site build. Spec §8 (IA), §9 (screens), §14 (pre-render policy).

    python site/build.py            # build into dist/
    python site/build.py --serve    # build, then serve it locally

Deliberately Python rather than Astro, which the spec named. The pipeline is
already Python, and a one-maintainer side project carrying two toolchains means two
dependency trees to rot, two CI setups and two things to relearn in six months.
This is ~500 lines with no dependencies, emitting plain HTML. That is a better fit
for A4 than a framework, and the output is identical: static files on a CDN.

Every page is fully rendered server-side. JavaScript only makes filtering faster —
with it off, every page still shows its roles, every link still works, and every
pre-rendered URL is still indexable.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
import pathlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATIC = ROOT / "site" / "static"
import os
DIST = pathlib.Path(os.environ.get("DIST_DIR", str(ROOT / "dist")))

SITE_NAME = "The 8 Houses Daily"
# Set SITE_URL in the host's environment rather than editing this file, so the
# same commit deploys to a preview and to production without a diff.
BASE_URL = os.environ.get("SITE_URL", "https://example.org").rstrip("/")
CONTACT = "tek@8houses.co.uk"

DOOR = {"one_off": "one-day", "flexible": "flexible", "weekly": "weekly",
        "fortnightly": "fortnightly", "monthly": "monthly", "long_term": "bigger"}
def in_door(op, door):
    """Which notices belong behind a door.

    Not an equality test on `commitment`, which is how this started and which left
    25 of 75 notices unreachable from the front page. The three doors lead to
    one_off, weekly and long_term; flexible, fortnightly and monthly had pages of
    their own that nothing linked to.

    The labels already promise ranges. "Every week or so" plainly covers
    fortnightly and monthly — the "or so" is doing that work. And `flexible` means
    the volunteer chooses, so it belongs behind every door: someone who wants a
    single day can do a flexible role once, and someone who wants it weekly can do
    it weekly. Same reasoning as `activity: "varies"` appearing whenever no
    activity is chosen.
    """
    c = op["commitment"]
    if c == "unknown":
        # An absence, not a promise. Shown on /all/, behind no door — the same
        # treatment as activity: "varies", and for the same reason: we never
        # offer a match we cannot support.
        return False
    if c == "flexible":
        # A promise: the volunteer picks, so every frequency is available.
        return True
    return c in DOOR_MEMBERS[door]


DOOR_MEMBERS = {
    "one_off":   {"one_off"},
    "weekly":    {"weekly", "fortnightly", "monthly"},
    "long_term": {"long_term"},
    # The three orphan values keep their own pages, each holding exactly itself,
    # so an existing URL does not break. They are simply not front-page doors.
    "flexible":    {"flexible"},
    "fortnightly": {"fortnightly"},
    "monthly":     {"monthly"},
}


DOOR_LABEL = {"one_off": "One day", "flexible": "A few odd hours",
              "weekly": "Every week or so", "fortnightly": "Every fortnight",
              "monthly": "A few hours a month", "long_term": "Something bigger"}
COMMIT_PHRASE = {"one_off": "one day", "flexible": "a few odd hours",
                 "weekly": "a slot each week", "fortnightly": "a slot fortnightly",
                 "monthly": "a few hours a month",
                 "long_term": "a serious commitment",
                 "unknown": "a commitment their page does not state"}
ACT_LABEL = {"cooking_serving": "cook and serve", "befriending": "welcome and befriend",
             "outreach": "do outreach", "advice": "give advice or casework",
             "mentoring": "mentor someone", "teaching": "teach a skill",
             "shop_warehouse": "work a shop or warehouse",
             "practical": "garden, decorate or mend",
             "admin": "do admin or back office",
             "fundraising": "fundraise or run events", "campaigning": "campaign",
             "hosting": "host someone", "governance": "join a board",
             "varies": "anything — varies by day"}
STATUS_LABEL = {"open": "Recruiting now", "seasonal_closed": "Closed for the season",
                "oversubscribed": "Oversubscribed", "closed": "Not recruiting",
                "unknown": "Their page doesn't say if they're recruiting"}
DBS_LABEL = {"none": "No DBS needed", "basic": "Basic DBS", "enhanced": "Enhanced DBS",
             "required_unspecified": "DBS check required — level not stated",
             "unknown": "Screening not stated — worth asking"}
MONTH = [None, "January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]

def long_date(d):
    """A date as a person writes it: "Wednesday, 3 September 2026".

    Not strftime("%A, %-d %B %Y"). The %-d flag — day of month without a leading
    zero — is a glibc extension. Windows' C library rejects it outright with
    ValueError, and the Windows equivalent %#d fails on Linux, so there is no
    format string that works on both. Build the string instead.
    """
    return f"{d:%A}, {d.day} {d:%B %Y}"


def short_date(d):
    """"3 September 2026". Same reasoning."""
    return f"{d.day} {d:%B %Y}"


e = html.escape
TOTAL = [0]     # orgs in scope; banner() needs it on every page
COUNTS = [0, 0]  # notices, charities — printed in the dateline
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ------------------------------------------------------------------ data

def load():
    orgs, opps = {}, []
    for f in sorted((DATA / "orgs").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        o = d["organisation"]
        if not d["opportunities"]:
            continue                       # a charity page with no roles is a dead end
        orgs[o["id"]] = o
        opps += d["opportunities"]
    fresh = {}
    if (DATA / "freshness.json").exists():
        fresh = json.loads((DATA / "freshness.json").read_text(encoding="utf-8"))
    total = len(list((DATA / "orgs").glob("*.json")))
    return orgs, opps, fresh, total


def areas_of(op, orgs):
    if op["location_type"] in ("remote", "own_home"):
        return []
    return [op["postcode_district"]] if op["postcode_district"] \
        else orgs[op["org_id"]].get("boroughs", [])


DISTRICT_BOROUGH = {
    "SE1": "Southwark", "SE11": "Lambeth", "SE27": "Lambeth",
    "E1": "Tower Hamlets", "E2": "Tower Hamlets", "E8": "Hackney",
    "N1": "Islington", "N16": "Hackney",
    "NW1": "Camden", "WC1": "Camden", "WC1H": "Camden",
    "SW1": "Westminster", "SW1P": "Westminster",
    "SW4": "Lambeth", "SW9": "Lambeth", "SW16": "Lambeth", "SW17": "Wandsworth",
    "EC1": "Islington", "W10": "Kensington and Chelsea",
}


def boroughs_of(op, orgs):
    return sorted({DISTRICT_BOROUGH.get(a, a) for a in areas_of(op, orgs)})


def suppressed(op, fresh):
    """Spec §11.5 — stale records stop asserting what we can't stand behind."""
    return bool(fresh.get("orgs", {}).get(op["org_id"], {}).get("suppress_assertive"))


# ------------------------------------------------------------------ engravings
# Hand-drawn line art rather than photography. §15 forbids poverty tourism, and
# stock imagery of people sleeping rough would be exactly that. These are the
# Daily Prophet's moving pictures done honestly: they loop gently, and hold
# perfectly still if the reader's system asks them to.

_POT = """<svg viewBox="0 0 120 78" role="img" aria-label="Engraving of a cooking pot, steam rising">
  <path class="steam" d="M44 30 C40 24 48 20 44 14 C41 9 47 6 45 2"/>
  <path class="steam" d="M60 29 C56 22 64 18 60 12 C57 7 63 4 61 0"/>
  <path class="steam" d="M76 30 C72 25 80 21 76 15 C73 10 79 7 77 3"/>
  <path class="eng" d="M28 36 h64 l-5 30 a6 6 0 0 1 -6 5 H39 a6 6 0 0 1 -6 -5 z"/>
  <path class="eng" d="M24 36 h72"/>
  <path class="eng" d="M28 42 a7 6 0 0 1 -7 6"/><path class="eng" d="M92 42 a7 6 0 0 0 7 6"/>
  <g class="hatch"><path d="M38 46 v20"/><path d="M43 46 v21"/><path d="M48 47 v21"/>
    <path d="M78 46 v20"/><path d="M83 46 v19"/></g>
  <path class="eng" d="M18 71 h84"/>
  <g class="hatch"><path d="M22 74 h76"/><path d="M26 77 h68"/></g></svg>"""

_LAMP = """<svg viewBox="0 0 120 78" role="img" aria-label="Engraving of a street lamp, its flame guttering">
  <circle class="glow eng-fill" cx="60" cy="26" r="19"/>
  <path class="eng" d="M60 70 v-30"/><path class="eng" d="M50 40 h20 l-3 -6 h-14 z"/>
  <path class="eng" d="M52 34 l3 -12 h10 l3 12"/>
  <path class="eng" d="M55 22 h10"/><path class="eng" d="M58 18 h4"/>
  <g class="flame"><path class="eng" d="M60 32 c-3 -3 -1 -6 0 -8 c1 2 3 5 0 8"
     style="stroke-width:1.3"/></g>
  <path class="eng" d="M48 70 h24"/>
  <g class="hatch"><path d="M44 73 h32"/><path d="M40 76 h40"/>
    <path d="M57 44 v24"/><path d="M63 44 v24"/></g></svg>"""

_COAT = """<svg viewBox="0 0 120 78" role="img" aria-label="Engraving of a coat on a hook, swaying">
  <path class="eng" d="M8 8 h104"/><g class="hatch"><path d="M8 11 h104"/></g>
  <path class="eng" d="M60 8 v6"/>
  <g class="coat">
    <path class="eng" d="M60 14 l-16 8 -6 26 h8 l2 22 h24 l2 -22 h8 l-6 -26 z"/>
    <path class="eng" d="M52 22 l8 7 8 -7"/><path class="eng" d="M60 29 v41"/>
    <g class="hatch"><path d="M45 34 v30"/><path d="M50 36 v28"/>
      <path d="M70 34 v30"/><path d="M75 36 v26"/></g></g></svg>"""

_DOOR = """<svg viewBox="0 0 120 78" role="img" aria-label="Engraving of a doorway with a lit fanlight">
  <path class="eng" d="M30 74 V16 a30 14 0 0 1 60 0 v58"/>
  <path class="eng" d="M36 74 V26 h48 v48"/>
  <path class="eng" d="M36 26 a24 11 0 0 1 48 0"/>
  <circle class="glow eng-fill" cx="60" cy="21" r="13"/>
  <path class="eng" d="M60 26 V16"/><path class="eng" d="M48 20 h24"/>
  <circle class="eng" cx="76" cy="50" r="2.4"/>
  <g class="hatch"><path d="M42 32 v40"/><path d="M48 32 v40"/>
    <path d="M72 32 v40"/><path d="M78 32 v40"/></g>
  <path class="eng" d="M18 74 h84"/>
  <g class="hatch"><path d="M22 77 h76"/></g></svg>"""

ENGRAVING = {
    "cooking_serving": (_POT, "A single shift, then home"),
    "shop_warehouse": (_COAT, "Sorting what has been given"),
    "practical": (_DOOR, "Work that shows when it's done"),
    "befriending": (_LAMP, "The same evening, every week"),
    "advice": (_DOOR, "A door, and someone behind it"),
    "hosting": (_DOOR, "A spare room, a name, a year"),
    "mentoring": (_LAMP, "One person, walked alongside"),
    "teaching": (_DOOR, "What you know, passed on"),
    "fundraising": (_COAT, "Collected on a cold concourse"),
    "outreach": (_LAMP, "Out before the city wakes"),
    "governance": (_DOOR, "The room where it is decided"),
    "campaigning": (_LAMP, "Making a noise about it"),
    "admin": (_DOOR, "The quiet, necessary work"),
    "varies": (_COAT, "Whatever the day asks for"),
}


def plate(activity):
    svg, caption = ENGRAVING.get(activity, ENGRAVING["advice"])
    return (f'<figure class="plate">{svg}'
            f'<figcaption>{e(caption)}</figcaption></figure>')


# ------------------------------------------------------------------ narration

def narrate(op, orgs, fresh):
    """Compose the article body out of the record's own fields.

    A card with a larger headline is not an article, but I will not write prose a
    charity did not publish. Every sentence below restates a field we actually
    hold, and where a field is empty the sentence says so rather than being quietly
    dropped. That is the difference between reporting and inventing, and it is the
    basis on which this paper asks to be believed.

    Order matters as much as wording. A team-only notice puts that fact second,
    directly after the lead, because it decides whether the reader can apply at
    all — burying it below the screening conditions wastes their time.
    """
    org = orgs[op["org_id"]]
    sup = suppressed(op, fresh)
    overnight = "overnight" in (op.get("when") or []) \
        or op["location_type"] == "own_home"

    def sentence(text):
        """One clean sentence: no doubled stops, no stranded space."""
        t = " ".join(text.split()).rstrip(" .;,")
        return t + "." if t else ""

    def serial(items):
        """Join a list. Borough names contain 'and', so commas alone read as one
        long name — use semicolons once any item has an 'and' in it."""
        items = list(items)
        if len(items) == 1:
            return items[0]
        sep = "; " if any(" and " in i for i in items) else ", "
        return sep.join(items[:-1]) + (";" if sep == "; " else "") + \
            " and " + items[-1]

    paras = []

    # 1 — what you would actually be doing. Drop cap sits here.
    paras.append(sentence(op["what_youd_do"]))

    # 2 — can you even apply? Eligibility first, because it is absolute.
    if op.get("eligibility"):
        # Lower-case the opening word so it reads as part of the sentence — but
        # not proper nouns. "open only to londoners" is simply wrong.
        PROPER = {"Londoners", "London"}
        def lead(t):
            # The sentence already supplies "only", so drop a duplicate.
            t = re.sub(r"^(\w+)\s+only\b", r"\1", t, count=1)
            t = re.sub(r"^only\s+", "", t, count=1, flags=re.I)
            first = t.split(" ", 1)[0].rstrip(",")
            return t if first in PROPER else t[0].lower() + t[1:]
        paras.append("This one is open only to "
                     + serial([lead(e) for e in op["eligibility"]]) + ".")
    if op["who_can_apply"] == "team_only":
        paras.append("This house takes volunteer teams rather than individuals, so "
                     "if you are on your own this is not one to sign up to. A "
                     "workplace or community group can book a date.")

    # 3 — when, and for how long
    when_bits = []
    if op.get("specific_times") and not sup:
        t = op["specific_times"]
        if t.lower().startswith("varies"):
            # the field is a statement about variability, not a set of times
            when_bits.append("The hours vary" + t[len("varies"):])
        else:
            when_bits.append(f'It runs {t[0].lower()}{t[1:]}')
    else:
        when_bits.append("Their page does not set out the hours")
    if op.get("typical_shift_hours"):
        h = op["typical_shift_hours"]
        known = bool(op.get("specific_times")) and not sup
        if overnight:
            when_bits.append("and covers a whole night")
        elif known:
            when_bits.append(f'and takes about {h:g} '
                             f'hour{"" if h == 1 else "s"} at a time')
        else:
            # No clock time published, but the length is known.
            when_bits[0] = ("Their page does not set the time of day, though a "
                            f'shift is about {h:g} hour{"" if h == 1 else "s"}')
    para = sentence(", ".join(when_bits) if len(when_bits) > 1 else when_bits[0])
    if op["commitment"] == "unknown":
        # Two negatives in a row read badly — "Their page does not set out the
        # hours. Their page does not say how often they need you." Merge them.
        if para.startswith("Their page does not set out the hours"):
            para = sentence("Their page sets out neither the hours nor how often "
                            "they need you")
        else:
            para += " " + sentence("Their page does not say how often they need you")
    else:
        term = COMMIT_PHRASE[op["commitment"]]
        if op.get("min_term_months"):
            para += " " + sentence(f'They ask for {term}, for at least '
                                   f'{op["min_term_months"]} months')
        else:
            para += " " + sentence(f'They ask for {term}')
    paras.append(para)

    # 4 — what they will ask of you before you start
    if sup:
        paras.append("We have not managed to check this notice recently, so the "
                     "conditions are not printed here. Read them on their own page "
                     "before you travel.")
    else:
        sc = op["screening"]
        say = {
            "none": "Their page states that no DBS check is needed",
            "basic": "A basic DBS check is required",
            "enhanced": "An enhanced DBS check is required",
            "required_unspecified": "A DBS check is required, though their page does "
                                    "not say which level",
            "unknown": "Their page does not say whether a DBS check is needed, which "
                       "is worth asking before you commit",
        }[sc["dbs"]]
        extra = []
        if sc.get("min_age"):
            extra.append(f'you must be {sc["min_age"]} or over')
        if sc.get("interview"):
            extra.append("there is an interview")
        if sc.get("references"):
            extra.append("they ask for references")
        if extra:
            say += ", and " + serial(extra)
        para = sentence(say)
        if sc.get("induction"):
            para += " " + sentence(sc["induction"])
        paras.append(para)

    # 5 — where
    bs = boroughs_of(op, orgs)
    if op["location_type"] == "own_home":
        paras.append("This one happens at your own address rather than theirs, so "
                     "there is no journey to make.")
    elif op["location_type"] == "remote":
        paras.append("It is done remotely, from wherever you are.")
    elif bs:
        pc = op.get("postcode_district")
        d = f" ({pc})" if pc and pc not in bs else ""
        tail = ", and some of it is remote" if op["location_type"] == "hybrid" else ""
        paras.append(sentence(f'It is in {serial(bs)}{d}{tail}'))
    else:
        paras.append("Their page does not say where in London it takes place.")

    if op["who_can_apply"] == "either":
        paras.append("You may come on your own or bring a group.")

    # 6 — whether they are recruiting
    if not sup:
        w = op.get("seasonal_window")
        season = (f' The season runs from {MONTH[w["start_month"]]} to '
                  f'{MONTH[w["end_month"]]}.' if w else "")
        paras.append({
            "open": "They were recruiting when we last read the page." + season,
            "seasonal_closed": "It is out of season and closed at present." + season
                               + " Register your interest now and they will be in "
                                 "touch when it opens again.",
            "closed": "They were not recruiting when we last read the page.",
            "oversubscribed": "They had more offers than places when we last "
                              "read the page, and put new volunteers on a "
                              "waiting list. Apply anyway if it suits you.",
            "unknown": "Their page does not say whether they are recruiting at the "
                       "moment, so ask before you set your heart on it.",
        }[op["status"]])

    return [x for x in paras if x]


# ------------------------------------------------------------------ shell

def shell(*, title, desc, path, body, state=None, extra_head="", noindex=False,
          search=True, needs_data=True, banner_html=""):
    st = state or {}
    attrs = " ".join(f'data-{k}="{e(v)}"' for k, v in st.items() if v)
    canonical = BASE_URL.rstrip("/") + path
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f2ede1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
{robots}
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;0,9..144,900;1,9..144,400&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&family=Archivo:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/app.css">
{extra_head}
</head>
<body {attrs}>
<a class="skip" href="#main">Skip to content</a>
{header(search=search)}
{banner_html}
{body}
{lookup_block() if search else ""}
{footer()}
{'<script src="/assets/map.js"></script>' if needs_data else ''}
{'<script src="/assets/data.js"></script>' if needs_data else ''}
{'<script src="/assets/app.js"></script>' if needs_data else ''}
</body>
</html>
"""


def header(search=True):
    """The masthead. No search box — that moved below the fold.

    Someone arriving has not decided where to volunteer yet; a lookup field is for
    the minority who already know the charity they want, and giving it the most
    prominent slot on the page pushed the three actual calls to action down.

    """
    today = datetime.now(timezone.utc)
    title = (f'<a class="title" href="/"><span class="the">The</span> '
             f'8 Houses Daily</a>')
    return f"""<header class="wrap">
  <div class="masthead">
    <div class="doublerule"></div>
    <div class="earpiece">
      <span>Vol. I &middot; No. {today.strftime('%j').lstrip('0')}</span>
      <span class="mid">Printed in London</span>
      <span>Price &mdash; Nothing</span>
    </div>
    <div class="r-hair"></div>
    {title}
    <div class="doublerule"></div>
    <div class="dateline">
      <span>{long_date(today)}</span><i>&#9670;</i>
      <span><b>{COUNTS[0]}</b> notices</span><i>&#9670;</i>
      <span><b>{COUNTS[1]}</b> charities</span>
      <i class="drop">&#9670;</i><span class="drop">Checked this week</span>
    </div>
    <div class="r-thin"></div>
  </div>
</header>"""


def lookup_block():
    """The back-of-paper index. Low, because it serves the reader who already knows
    what they are after rather than the one deciding."""
    return """<div class="wrap"><div class="section lookup">
  <div class="section-bar"><h2>Look something up</h2></div>
  <p class="lookup-note">If you already know the charity, the district or the
    post you want.</p>
  <div class="ta">
    <label class="sr" for="ta">Find a charity, a borough or a notice</label>
    <input id="ta" type="text" role="combobox" aria-expanded="false"
      aria-autocomplete="list" aria-controls="talist" autocomplete="off"
      placeholder="Manna Society, Southwark, kitchen&hellip;">
    <ul id="talist" role="listbox" aria-label="Matches" hidden></ul>
  </div>
</div></div>"""


def footer():
    return f"""<footer class="wrap colophon">
  <p><a href="/about/">About this paper</a></p>
  <p>We print notices &mdash; no applications taken, no charity vetted.
     Corrections to <a href="mailto:{CONTACT}">{CONTACT}</a></p>
  <p>If you need help rather than a post &mdash;
     <a href="/help/">start here</a></p>
</footer>"""


def _w(inner, wrap):
    """banner() is used both between landmarks and inside a .wrap already."""
    return f'<div class="wrap">{inner}</div>' if wrap else inner


def banner(fresh, orgs_listed, orgs_total, wrap=True):
    """Coverage honesty, plus §11.5's decay notice when it fires."""
    out = []
    if fresh.get("site_banner"):
        out.append(_w(f'<div class="notice"><b>Publication suspended</b>'
                      f'{e(fresh.get("site_banner_copy") or "")}</div>', wrap))
    out.append(_w(
        f'<div class="notice grey"><b>Notice from the publisher</b>{orgs_listed} of '
        f'{orgs_total} charities place notices here, every word from their own '
        f'page. <a href="/data/">How the notices are checked &rarr;</a></div>',
        wrap))
    return "\n".join(out)


# ------------------------------------------------------------------ cards

def card(op, orgs, fresh):
    """A classified advertisement.

    Roles *are* small ads — "WANTED: kitchen volunteer, Southwark, Saturdays,
    apply within" is the format newspapers used for exactly this content for two
    centuries. Particulars go in a definition list because that is what they are:
    labelled facts, not prose.

    Stamps mark exceptions only. There is no RECRUITING NOW stamp, because that is
    the default and stamping it would flatten the signal.
    """
    org = orgs[op["org_id"]]
    sup = suppressed(op, fresh)
    bs = boroughs_of(op, orgs)

    where = ("At your own home" if op["location_type"] == "own_home"
             else "Anywhere &mdash; remote" if op["location_type"] == "remote"
             else (", ".join(bs) + (" &middot; part remote" if op["location_type"] == "hybrid" else ""))
             if bs else "Across London")

    # Particulars: only what the page actually stated.
    rows = []
    hours = " &middot; ".join(x for x in [
        op.get("specific_times") if not sup else None,
        f'{op["typical_shift_hours"]:g} hours' if op.get("typical_shift_hours") else None,
    ] if x)
    if hours:
        rows.append(("Hours", hours))
    term = COMMIT_PHRASE[op["commitment"]].capitalize()
    if op.get("min_term_months"):
        term += f', {op["min_term_months"]} months at least'
    rows.append(("Term", term))
    # First row after the hours, because it decides whether the rest is worth
    # reading at all.
    if op.get("eligibility"):
        rows.append(("Only for", " \u00b7 ".join(op["eligibility"])))
    if sup:
        rows.append(("Asked of you", "Not checked recently"))
    else:
        sc = op["screening"]
        # Nine of eleven charities publish nothing about screening, so the long
        # form ("Screening not stated — worth asking") printed nine times on one
        # page. Two words here; the explanation sits once above the column.
        ask = ("Not stated" if sc["dbs"] == "unknown" else DBS_LABEL[sc["dbs"]])
        if sc.get("min_age"):
            ask += f', aged {sc["min_age"]} and over'
        rows.append(("Asked of you", ask))
        if sc.get("induction"):
            rows.append(("Note", sc["induction"]))
    if op.get("seasonal_window") and not sup:
        w = op["seasonal_window"]
        rows.append(("Season", f'{MONTH[w["start_month"]]} to {MONTH[w["end_month"]]}'))

    dl = "".join(f"<dt>{e(k)}</dt><dd>{v}</dd>" for k, v in rows)

    # Stamps — exceptions only, and never more than two.
    stamps = []
    if sup:
        stamps.append(("Not checked<br>recently", "grey"))
    elif op["status"] == "seasonal_closed":
        stamps.append(("Closed for<br>the season", ""))
    elif op["status"] == "closed":
        stamps.append(("Not<br>recruiting", ""))
    elif op["status"] == "oversubscribed":
        stamps.append(("Over<br>subscribed", ""))
    elif op["status"] == "unknown":
        stamps.append(("Recruiting<br>not stated", "grey"))
    if op["who_can_apply"] == "team_only":
        stamps.append(("Teams only", "low"))
    stamp_html = "".join(
        f'<span class="stamp {c}">{t}</span>' for t, c in stamps[:2])

    btn = {"role": "Read the notice at their own house",
           "org_volunteer_page": "Apply at their own house"}.get(
        op["url_specificity"], "Their own house")
    href = op.get("apply_url") or org["volunteer_url"]

    # An article page says "Confidence low" in its byline; a classified said
    # nothing at all. With 11 of 67 notices resting on a thin page or a
    # third-party listing, a reader scanning a column had no way to tell which.
    # Printed at the foot of the particulars, where it qualifies them.
    unconfirmed_html = (
        '<p class="unconfirmed">We could not confirm these particulars &mdash; '
        'read their own page before you go.</p>'
        if op["provenance"]["confidence"] < 0.7 and not sup else "")

    return f"""<article class="ad" data-id="{e(op['id'])}">
  <div class="ad-org">
    <span><a href="/charity/{e(org['id'])}/">{e(org['name'])}</a></span>
    <span>{where}</span>
  </div>
  <h3><a href="/role/{e(op['id'])}/">{e(op['title'])}</a></h3>
  {stamp_html}
  <p class="what">{e(op['what_youd_do'])}</p>
  <dl>{dl}</dl>
  {unconfirmed_html}
  <a class="apply" href="{e(href)}" target="_blank" rel="noopener nofollow">{e(btn)} &rarr;</a>
</article>"""


def jsonld(op, orgs):
    """schema.org VolunteerOpportunity. Only assert what the record actually holds."""
    org = orgs[op["org_id"]]
    d = {"@context": "https://schema.org", "@type": "VolunteerOpportunity",
         "name": op["title"], "description": op["what_youd_do"],
         "url": f"{BASE_URL}/role/{op['id']}/",
         "organizer": {"@type": "NGO", "name": org["name"], "url": org["website_url"]}}
    if org.get("charity_number"):
        d["organizer"]["identifier"] = org["charity_number"]
    bs = boroughs_of(op, orgs)
    if bs:
        d["locationCreated"] = [{"@type": "Place",
                                 "address": {"@type": "PostalAddress",
                                             "addressLocality": b,
                                             "addressRegion": "London",
                                             "addressCountry": "GB"}} for b in bs]
    if op["location_type"] in ("remote", "hybrid"):
        d["availableLanguage"] = "en-GB"
    return ('<script type="application/ld+json">'
            + json.dumps(d, separators=(",", ":")) + "</script>")


# ------------------------------------------------------------------ controls

def sentence(state, orgs, opps):
    """The §7.3 sentence builder as a printed form of enquiry.

    Below 640px it is a coupon: labelled rows with a dotted rule to fill in, which
    is what a phone can actually render. Above that the rows collapse into the
    prose sentence, which is the same control in the format the spec described.
    Server-rendered either way, so it works with JavaScript off.
    """
    def opts(items, sel, placeholder):
        o = [f'<option value=""{"" if sel else " selected"}>'
             f'&hellip; {e(placeholder)} &hellip;</option>']
        for v, l in items:
            o.append(f'<option value="{e(v)}"'
                     f'{" selected" if v == sel else ""}>{e(l)}</option>')
        return "".join(o)

    boroughs = sorted({b for op in opps for b in boroughs_of(op, orgs)})
    acts = sorted({op["activity"] for op in opps})
    c = state.get("commitment", "")
    b = state.get("borough", "")
    a = state.get("activity", "")

    def slot(sid, label, lead, items, sel, placeholder):
        return (f'<span class="slot{" filled" if sel else ""}">'
                f'<span class="lbl">{lead}</span>'
                f'<label class="sr" for="{sid}">{e(label)}</label>'
                f'<select id="{sid}">{opts(items, sel, placeholder)}</select>'
                f'<span class="caret" aria-hidden="true">&#9660;</span></span>')

    s1 = slot("b1", "How much time you can give", "I have",
              [(k, COMMIT_PHRASE[k]) for k in DOOR], c, "any amount of time")
    s2 = slot("b2", "Which borough", "I am in",
              [(x, x) for x in boroughs], b, "any borough")
    s3 = slot("b3", "What you would like to do", "I should like to",
              [(x, ACT_LABEL[x]) for x in acts], a, "anything at all")
    n = state["n"]

    return f"""<div class="coupon">
  <h2 class="coupon-head">Form of enquiry</h2>
  <div class="fillin">
    <span class="d640">I have </span>{s1}<span class="d640"> to give, </span>
    <span class="d640">I am in </span>{s2}<span class="d640">, </span>
    <span class="d640">and I should like to </span>{s3}<span class="d640">.</span>
  </div>
  <div class="coupon-foot">
    <b id="cnum" aria-live="polite">{n} notice{'' if n == 1 else 's'}</b>
    <span class="stoppress" id="cdelta"></span>
    <button class="rst" id="rstall">Begin again</button>
  </div>
</div>"""


REFINE = """<div class="refine">
  <label class="sr" for="rWho">Applying as</label>
  <select id="rWho"><option value="">Alone or with a team</option>
    <option value="individual">On my own</option>
    <option value="team_only">With a team</option></select>
  <label class="sr" for="rOpen">Whether recruiting</label>
  <select id="rOpen"><option value="">Any notice</option>
    <option value="open">Recruiting now</option></select>
  <label class="sr" for="rRemote">Where</label>
  <select id="rRemote"><option value="">In person or remote</option>
    <option value="remote">Remote only</option></select>
  <label class="sr" for="rSort">Arranged by</label>
  <select id="rSort"><option value="soonest">Recruiting first</option>
    <option value="least">Least asked of you</option>
    <option value="az">Alphabetical</option></select>
</div>
<p class="linkline">This page &mdash; <span id="urlout"></span>
  <button id="copy">copy the address</button></p>"""

MAP_JSON = DATA / "london-map.json"


def map_data():
    return json.loads(MAP_JSON.read_text(encoding="utf-8")) if MAP_JSON.exists() else None


def map_panel():
    """The district map.

    Real borough outlines from ONS/OS administrative geography, with the Thames
    taken from the seam where the north-bank and south-bank boroughs meet — the
    same source as the shapes, so it sits exactly on the banks.

    Two deliberate choices. The SVG carries no text: font-size inside a scaled
    viewBox resolves in user units, which is what made an earlier version render
    its labels at 43px. Counts are HTML positioned by percentage over the top.
    And the SVG is aria-hidden with the chips below it as the real control, so a
    keyboard user is not made to walk 33 duplicate tab stops to reach a view of
    something the chips already do.
    """
    m = map_data()
    if not m:
        return ""
    shapes = "".join(
        f'<path class="bo" data-name="{e(b["name"])}" d="{b["d"]}"/>'
        for b in m["boroughs"])
    attr = " &middot; ".join(e(a) for a in m["attribution"])
    return f"""<div class="mapwrap" id="mapwrap">
  <div class="maphead"><h2>Index of districts</h2><span id="mapsub"></span>
    <button id="mapclear" hidden>Clear the district</button></div>
  <div class="mapfield" id="mapfield">
    <svg class="boroughs" id="boroughs" viewBox="0 0 {m['width']} {m['height']}"
         aria-hidden="true" focusable="false">
      <g class="bo-layer">{shapes}</g>
      <path class="thames-w" d="{m['thames']}"/>
      <path class="thames-l" d="{m['thames']}"/>
    </svg>
    <svg class="leaders" id="leaders" viewBox="0 0 100 100"
         preserveAspectRatio="none" aria-hidden="true" focusable="false"></svg>
    <div class="badges" id="badges" aria-hidden="true"></div>
  </div>
  <div class="tilemap" id="tilemap" role="group"
       aria-label="Districts with notices"></div>
  <div class="maplegend">
    <span><i class="sw-lit"></i>notices here</span>
    <span class="sw-river-row"><i class="sw-river"></i>the Thames</span>
  </div>
  <p class="mapnote" id="mapnote"></p>
  <p class="mapattr">{attr}</p>
</div>"""


# ------------------------------------------------------------------ pages

def write(path: str, content: str) -> None:
    p = DIST / path.strip("/") / "index.html" if path != "/" else DIST / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def screening_note(rows):
    """Printed once above a column of classifieds, and only when it earns its place.

    Most charities publish nothing about DBS checks or minimum ages. Repeating that
    on every notice turned six words into background noise; explaining the pattern
    once tells the reader something the individual notices cannot.
    """
    unknown = [o for o in rows if o["screening"]["dbs"] == "unknown"]
    if len(rows) < 3 or len(unknown) < len(rows) / 2:
        return ""
    return ('<p class="colnote">Most of these charities publish nothing about what '
            'they ask of volunteers &mdash; no check, no minimum age, no references '
            'policy. Where a notice reads <b>not stated</b>, that is their page '
            'being silent rather than us not looking. Ask before you commit.</p>')


def results_page(*, path, title, desc, heading, intro, rows, orgs, fresh,
                 state, opps, noindex=False, orgs_total=0):
    cards = "\n".join(card(o, orgs, fresh) for o in rows)
    empty = "" if rows else """<div class="empty">
      <h3>No notices answer this</h3>
      <p>Nothing in this edition matches that combination. The paper is young &mdash;
        there are more houses still to read.</p>
      <div class="opts"><a href="/all/">Read every notice</a>
        <a href="/">Front page</a></div></div>"""
    st = dict(state)
    st["n"] = len(rows)
    body = f"""<main class="wrap" id="main">
  <a class="back" href="/">&larr; Front page</a>
  <p class="kicker">Situations vacant</p>
  <h1 style="font-family:var(--display);font-weight:900;
     font-size:clamp(26px,7vw,46px);line-height:.96;letter-spacing:-.022em;
     text-transform:uppercase">{e(heading)}</h1>
  {f'<p class="standfirst">{e(intro)}</p>' if intro else ''}
  <div class="r-thin" style="margin:14px 0 0"></div>
  {sentence(st, orgs, opps)}
  {REFINE}
  {map_panel()}
  <div class="section-bar" style="margin-top:26px"><h2>The notices</h2></div>
  {screening_note(rows)}
  <div class="list" id="list">{cards}</div>
  {empty}
  <div class="empty" id="empty" hidden><h3 id="ehead">No notices answer this</h3>
    <p id="ebody"></p>
    <div class="opts" id="eopts"></div></div>
</main>"""
    body = f'<section id="results">{body}</section>'
    write(path, shell(title=title, desc=desc, path=path, body=body,
                      state={k: v for k, v in state.items()}, noindex=noindex,
                      banner_html=banner(fresh, len(orgs), orgs_total)))


def sort_roles(rows):
    rank = {"open": 0, "seasonal_closed": 1}
    w = {"one_off": 1, "flexible": 2, "monthly": 3, "weekly": 4,
         "fortnightly": 4, "long_term": 6}
    return sorted(rows, key=lambda o: (rank.get(o["status"], 2),
                                       w.get(o["commitment"], 9),
                                       o["typical_shift_hours"] or 99))


# One engraving per door. Not keyed to activity here — a door spans several — so
# each gets the image that best carries its character.
DOOR_PLATE = {"one_off": "cooking_serving",   # the pot, steam rising
              "weekly": "befriending",         # the lamp, lit again each week
              "long_term": "hosting"}          # the doorway, fanlight burning

DOOR_VIDEO = {"one_off": ("soup-kitchen", "Soup kitchen"),
              "weekly": ("coffee-chat", "Coffee chat"),
              "long_term": ("hosting", "Hosting")}


def moving_plate(key):
    name, label = DOOR_VIDEO[key]
    caption = ENGRAVING[DOOR_PLATE[key]][1]
    # Delay loading the film until motion preferences have been checked.
    # The poster also works without JavaScript or when autoplay is unavailable.
    return (f'<figure class="plate">'
            f'<video class="door-film" muted loop playsinline preload="none" '
            f'poster="/assets/videos/{name}.webp" '
            f'data-src="/assets/videos/{name}.mp4" '
            f'aria-label="{e(label)} illustration"></video>'
            f'<figcaption>{e(caption)}</figcaption>'
            f'<button class="film-toggle" type="button" data-state="paused" hidden '
            f'aria-label="Play {e(label.lower())} animation"></button>'
            '</figure>')


def build_home(orgs, opps, fresh, total):
    """The front page.

    Order is deliberate: the three ways are the only things on this page a reader
    can act on, so they come first, immediately under the masthead. The headline
    and the paper's purpose follow, because explanation is worth less than action
    and costs the fold to put above it. The lookup field is lower still — it serves
    the reader who already knows the charity they want, who is a minority.

    An earlier draft ran to 491 words and said "no applications taken here" three
    times over. Standing terms live in the colophon, which prints on every page.
    """
    counts = {k: len([o for o in opps if o["commitment"] == k]) for k in DOOR}

    ways = [
        ("one_off",
         "A morning in a kitchen, an evening on a station concourse. Turn up, be "
         "useful, go home."),
        ("weekly",
         "A regular slot in a kitchen, day centre or drop-in. The people you sit "
         "with come to know your face."),
        ("long_term",
         "Mentoring, a seat on a board, or a spare room for a young person with "
         "nowhere else. These ask for references and a check."),
    ]

    cols = []
    for key, blurb in ways:
        n = counts[key]
        cols.append(f"""    <div class="col">
      {moving_plate(key)}
      <h2><a href="/{DOOR[key]}/">{e(DOOR_LABEL[key])}</a></h2>
      <p>{blurb}</p>
      <a class="doorcta" href="/{DOOR[key]}/">
        Read the {n} notice{'' if n == 1 else 's'} &rarr;</a>
    </div>""")

    body = f"""<main class="wrap" id="main"><section id="home">
  <div class="lead"><h1>How Much<br>Can You Spare?</h1></div>
  <div class="cols cols-lead">
{chr(10).join(cols)}
  </div>
  <p><a class="applybig" href="/all/">Or read every notice &rarr;</a></p>
</section>

  {banner(fresh, len(orgs), total, wrap=False)}

  <div class="section">
    <div class="section-bar"><h2>Five minutes instead</h2></div>
    <div class="five">
      <a href="https://www.streetlink.org.uk" rel="nofollow">
        <b>Report someone sleeping rough</b>
        <p>StreetLink sends the location to a local outreach team. Call 999 in an
          emergency.</p></a>
      <a href="/five-minutes/"><b>Give what they are short of</b>
        <p>Most charities publish a list. Read it before you gather anything.</p></a>
      <a href="/five-minutes/"><b>Set a reminder for autumn</b>
        <p>Winter shelters recruit from October and fill quickly.</p></a>
    </div>
  </div>
</main>"""
    write("/", shell(banner_html="",   # printed inline, after the calls to action
                     title=f"{SITE_NAME} — volunteering with London homelessness charities",
                     desc=f"{len(opps)} volunteering posts at {len(orgs)} London "
                          "homelessness charities, set out by how much time you "
                          "have, where you are and what you would be doing.",
                     path="/", body=body))


def build_filters(orgs, opps, fresh, total):
    """§14 pre-render policy: one- and two-blank combinations that have results.

    Only combinations with results are emitted. A pre-rendered page with nothing on
    it is thin content — an SEO liability rather than an asset — and it is also a
    promise the site can't keep. Empty combinations resolve client-side instead.
    """
    made = []
    b = banner(fresh, len(orgs), total)

    # /all/
    rows = sort_roles(opps)
    results_page(path="/all/", title=f"All volunteering roles — {SITE_NAME}",
                 desc=f"All {len(rows)} volunteering roles we've researched at "
                      "London homelessness charities.",
                 heading="Every notice in this edition",
                 intro=None, rows=rows, orgs=orgs, fresh=fresh,
                 state={}, opps=opps)
    made.append("/all/")

    for c in DOOR:
        crows = sort_roles([o for o in opps if in_door(o, c)])
        if not crows:
            continue
        p = f"/{DOOR[c]}/"
        results_page(path=p, title=f"{DOOR_LABEL[c]} — volunteering in London",
                     desc=f"{len(crows)} volunteering roles in London for people "
                          f"who can give {COMMIT_PHRASE[c]}.",
                     heading=f"{DOOR_LABEL[c]}", intro=(
                         f"{len(crows)} notice{'' if len(crows) == 1 else 's'} for "
                         f"readers who can give {COMMIT_PHRASE[c]}."), rows=crows,
                     orgs=orgs, fresh=fresh, state={"commitment": c}, opps=opps)
        made.append(p)

        for bo in sorted({x for o in crows for x in boroughs_of(o, orgs)}):
            here = [o for o in crows if bo in boroughs_of(o, orgs)]
            anywhere = [o for o in crows if not boroughs_of(o, orgs)]
            brows = sort_roles(here + anywhere)
            if not here:
                continue          # a borough page with only placeless roles is padding
            p2 = f"/{DOOR[c]}/{slug(bo)}/"
            # Say plainly that some of these aren't tied to the borough. The cards
            # already say "Across London"; the page shouldn't imply otherwise.
            intro = (f"{len(here)} role{'' if len(here) == 1 else 's'} in {bo}"
                     + (f", plus {len(anywhere)} that aren't tied to one borough — "
                        "remote, at your own home, or their page doesn't say."
                        if anywhere else "."))
            results_page(path=p2,
                         title=f"Volunteer in {bo} — {DOOR_LABEL[c].lower()}",
                         desc=f"{len(here)} volunteering roles in {bo} for people "
                              f"who can give {COMMIT_PHRASE[c]}.",
                         heading=f"{DOOR_LABEL[c]}, in {bo}", intro=intro,
                         rows=brows, orgs=orgs, fresh=fresh,
                         state={"commitment": c, "borough": bo}, opps=opps)
            made.append(p2)

        for act in sorted({o["activity"] for o in crows}):
            arows = sort_roles([o for o in crows if o["activity"] == act])
            if not arows:
                continue
            p3 = f"/{DOOR[c]}/{slug(act)}/"
            results_page(path=p3,
                         title=f"{ACT_LABEL[act].capitalize()} — {DOOR_LABEL[c].lower()}",
                         desc=f"{len(arows)} London volunteering roles where you'd "
                              f"{ACT_LABEL[act]}, for {COMMIT_PHRASE[c]}.",
                         heading=f"{DOOR_LABEL[c]}, to {ACT_LABEL[act]}",
                         intro=(f"{len(arows)} notice"
                                f"{'' if len(arows) == 1 else 's'} where you would "
                                f"{ACT_LABEL[act]}."),
                         rows=arows, orgs=orgs, fresh=fresh,
                         state={"commitment": c, "activity": act}, opps=opps)
            made.append(p3)
    return made


def build_roles(orgs, opps, fresh):
    made = []
    for op in opps:
        org = orgs[op["org_id"]]
        sup = suppressed(op, fresh)
        pv = op["provenance"]
        bs = boroughs_of(op, orgs)
        checked = org.get("check", {}).get("last_success")
        checked_txt = (short_date(datetime.fromisoformat(checked))
                       if checked else "not yet checked")

        # An unknown commitment sits behind no door, so its article goes back
        # to the full list rather than to a page it does not appear on.
        back_to = DOOR.get(op["commitment"], "all")
        back_label = DOOR_LABEL.get(op["commitment"], "All notices")

        paras = narrate(op, orgs, fresh)
        prose = "".join(
            f'<p{" class=\"dropcap\"" if i == 0 else ""}>{e(t)}</p>'
            for i, t in enumerate(paras))

        # Particulars: the same labelled facts as the classified, set as a table.
        rows = []
        if op.get("specific_times") and not sup:
            rows.append(("Hours", op["specific_times"]))
        if op.get("typical_shift_hours"):
            rows.append(("Each time", f'About {op["typical_shift_hours"]:g} hours'))
        term = COMMIT_PHRASE[op["commitment"]].capitalize()
        if op.get("min_term_months"):
            term += f', {op["min_term_months"]} months at least'
        rows.append(("Term", term))
        rows.append(("Where", "Your own home" if op["location_type"] == "own_home"
                     else "Remote" if op["location_type"] == "remote"
                     else ", ".join(bs) if bs else "Not stated"))
        if not sup:
            rows.append(("Check", "Not stated"
                         if op["screening"]["dbs"] == "unknown"
                         else DBS_LABEL[op["screening"]["dbs"]]))
            if op["screening"].get("min_age"):
                rows.append(("Age", f'{op["screening"]["min_age"]} and over'))
            if op["screening"].get("induction"):
                rows.append(("Before you start", op["screening"]["induction"]))
        if op.get("eligibility"):
            rows.append(("Only for", "; ".join(op["eligibility"])))
        rows.append(("Apply as", {"individual": "On your own",
                                 "team_only": "A team only",
                                 "either": "On your own or as a team"}.get(
            op["who_can_apply"], "Not stated")))
        parts = "".join(f"<dt>{e(k)}</dt><dd>{e(str(v))}</dd>" for k, v in rows)

        others = [o for o in opps
                  if o["org_id"] == op["org_id"] and o["id"] != op["id"]]
        other_html = "".join(
            f'<li><a href="/role/{e(o["id"])}/">{e(o["title"])}</a> &mdash; '
            f'{e(COMMIT_PHRASE[o["commitment"]])}</li>' for o in others)

        btn = {"role": "Read the notice at their own house",
               "org_volunteer_page": "Apply at their own house"}.get(
            op["url_specificity"], "Their own house")
        href = op.get("apply_url") or org["volunteer_url"]

        kicker = " &middot; ".join(x for x in [
            "Situations vacant",
            (", ".join(bs).upper() if bs else
             "AT YOUR OWN HOME" if op["location_type"] == "own_home" else "LONDON"),
        ] if x)

        body = f"""<main class="wrap article" id="main">
  <a class="back" href="/{back_to}/">&larr; {e(back_label)}</a>
  <p class="kicker">{kicker}</p>
  <h1>{e(op['title'])}</h1>
  <p class="standfirst">At {e(org['name'])}{', ' + e(org['summary'].rstrip('.').lower()) if org.get('summary') else ''}</p>
  <p class="byline">Checked {e(checked_txt)}
    {'&middot; Confidence low' if pv['confidence'] < 0.7 else ''}</p>
  <div class="r-thin" style="margin:14px 0 0"></div>

  {plate(op["activity"])}
  <div class="prose">{prose}</div>

  <div class="particulars">
    <h2>Particulars</h2>
    <dl>{parts}</dl>
  </div>

  <p><a class="applybig" href="{e(href)}" target="_blank"
     rel="noopener nofollow">{e(btn)} &rarr;</a></p>

  {'<div class="section"><div class="section-bar"><h2>Also at this house</h2></div><ul class="alsolist">' + other_html + '</ul></div>' if others else ''}

  <div class="footnote">
    <b>Where this came from</b>
    <p>Read from <a href="{e(pv['source_url'])}" rel="nofollow">their own page</a>,
      last checked {e(checked_txt)}.
      {'Set by a person.' if pv['reviewed_by_human'] else 'Set by machine, awaiting a reader.'}
      {'Confidence is low, so treat the particulars as indicative.' if pv['confidence'] < 0.7 else ''}</p>
    {'<p>Their page is silent on: ' + e(', '.join(pv['unsupported_fields'])) + '.</p>' if pv.get('unsupported_fields') else ''}
    <p>Something wrong? <a href="mailto:{CONTACT}?subject=Correction: {e(op['id'])}">Write
      to the editor</a>.</p>
  </div>
</main>"""
        write(f"/role/{op['id']}/",
              shell(title=f"{op['title']} at {org['name']} — {SITE_NAME}",
                    desc=op["what_youd_do"][:155],
                    path=f"/role/{op['id']}/", body=body,
                    extra_head="" if sup else jsonld(op, orgs),
                    banner_html=banner(fresh, len(orgs), TOTAL[0])))
        made.append(f"/role/{op['id']}/")
    return made


def build_charities(orgs, opps, fresh):
    made = []
    for oid, org in orgs.items():
        rows = sort_roles([o for o in opps if o["org_id"] == oid])
        cards = "\n".join(card(o, orgs, fresh) for o in rows)
        cn = (f'Registered charity no. {e(org["charity_number"])} &mdash; '
              f'<a href="https://register-of-charities.charitycommission.gov.uk/"'
              f' rel="nofollow">check the register yourself</a>'
              if org.get("charity_number")
              else "We do not have their charity number yet.")
        bs = ", ".join(org.get("boroughs", [])) or (
            "Across London" if org.get("coverage") == "london_wide" else "London")
        body = f"""<main class="wrap article" id="main">
  <a class="back" href="/all/">&larr; All notices</a>
  <p class="kicker">The house of</p>
  <h1>{e(org['name'])}</h1>
  {f'<p class="standfirst">{e(org["summary"])}</p>' if org.get('summary') else ''}
  <p class="byline">{bs} &middot; {cn}</p>
  <div class="r-thin" style="margin:14px 0 16px"></div>
  <p><a class="applybig" href="{e(org['volunteer_url'])}" target="_blank"
     rel="noopener nofollow">Their own volunteering page &rarr;</a></p>
  <div class="section">
    <div class="section-bar"><h2>{len(rows)} notice{'' if len(rows) == 1 else 's'}</h2>
      <span class="n">As we last read them</span></div>
    <div class="ads">{cards}</div>
  </div>
  <p class="footnote"><b>A word on listing</b>
    Printing a notice is not a recommendation. We set out what their page says; we
    do not assess how a house is run.</p>
</main>"""
        write(f"/charity/{oid}/",
              shell(title=f"Volunteer with {org['name']} — {SITE_NAME}",
                    desc=(org.get("summary")
                          or f"Volunteering notices at {org['name']}.")[:155],
                    path=f"/charity/{oid}/", body=body,
                    banner_html=banner(fresh, len(orgs), TOTAL[0])))
        made.append(f"/charity/{oid}/")
    return made


STATIC_PAGES = {
    # /help/ is the one page where the period voice would be actively wrong.
    # Someone sleeping rough needs plain words and a number, not charm. It keeps
    # the paper's frame — same masthead, same rules — and drops everything else.
    "/help/": ("Public notice: where to get help", False,
               "Where to get help if you are sleeping rough or at risk of it in London.", """
<div class="pubnotice">
  <h1>If you need help, not a post</h1>
  <p class="plain">This paper prints volunteering notices, so you are in the wrong
    place &mdash; but not the wrong place to be sent somewhere better. Everything
    below is free.</p>

  <div class="helpitem">
    <h2>Sleeping rough tonight</h2>
    <p>StreetLink passes your location, or the location of someone you are worried
      about, to a local outreach team. If someone is in immediate danger, call 999
      instead.</p>
    <a class="big" href="https://www.streetlink.org.uk" rel="nofollow">Go to StreetLink</a>
  </div>

  <div class="helpitem">
    <h2>Advice about housing or homelessness</h2>
    <p>Shelter's helpline is free and open every day of the week. They can tell you
      what your council must do for you and how to make them do it.</p>
    <a class="big" href="https://england.shelter.org.uk/get_help" rel="nofollow">Shelter's helpline</a>
  </div>

  <div class="helpitem">
    <h2>If you are under 25</h2>
    <p>Centrepoint runs a free helpline for young people who are homeless or about
      to be.</p>
    <a class="big" href="https://centrepoint.org.uk/helpline" rel="nofollow">Centrepoint helpline</a>
  </div>

  <div class="helpitem">
    <h2>We cannot help you directly</h2>
    <p>We are not a service and hold no beds, no funds and no caseworkers. The
      three above can actually do something. Please use them rather than us.</p>
  </div>
</div>"""),

    "/about/": ("About this paper", True,
                "What The 8 Houses Daily is, who sets it, and what it deliberately does not do.", """
<p class="kicker">From the editor</p>
<h1>About this paper</h1>
<p class="standfirst">A free sheet of volunteering notices from London homelessness
  charities. Set by one person, printed on nothing, carrying no advertising.</p>
<div class="r-thin" style="margin:14px 0 16px"></div>

<div class="prose">
<p class="dropcap">Most volunteering directories list organisations. You cannot
  volunteer for an organisation &mdash; you volunteer for a post, on a particular
  morning, in a particular building, having satisfied whatever the charity asks
  first. So this paper lists posts, and prints the four things that actually decide
  whether you can take one: when it runs, how long they want you for, where it is,
  and what they will ask of you.</p>
<p>Every word comes from the charity's own page. Where a page is silent, this paper
  says so rather than guessing &mdash; and most are silent on whether a check is
  needed, which is why so many notices carry the line about asking first.</p>
</div>

<div class="particulars">
  <h2>What this paper does not do</h2>
  <dl>
    <dt>Applications</dt><dd>None taken here. Every notice links to the charity.</dd>
    <dt>Vetting</dt><dd>None. Printing a notice is not a recommendation.</dd>
    <dt>Accounts</dt><dd>None. No cookies, no address collected, nothing to log in to.</dd>
    <dt>Scope</dt><dd>London only.</dd>
  </dl>
</div>

<div class="section">
  <div class="section-bar"><h2>Other papers worth reading</h2></div>
  <p style="margin-top:12px">We do not print everything.
    <a href="https://reachvolunteering.org.uk" rel="nofollow">Reach Volunteering</a>
    carries skills-based posts nationally, and
    <a href="https://jobs.homeless.org.uk/volunteer-jobs/" rel="nofollow">Homeless
    Link</a> gathers posts from across the sector.</p>
</div>

<p class="footnote"><b>Corrections</b>
  If you work at a charity printed here and something is wrong &mdash; or you would
  rather not appear at all &mdash; write to
  <a href="mailto:tek@8houses.co.uk">tek@8houses.co.uk</a> and it will be corrected
  or removed. There is nothing to argue about.</p>"""),

    "/data/": ("How the notices are checked", True,
               "How notices are gathered, checked each week, and what happens when they go stale.", """
<p class="kicker">A note on method</p>
<h1>How the notices are checked</h1>
<p class="standfirst">The one thing a paper can do that a search engine cannot is
  stay current. Here is exactly how that works, including how it fails.</p>
<div class="r-thin" style="margin:14px 0 16px"></div>

<div class="prose">
<p class="dropcap">Once a week, early on a Sunday, an automated reader visits each
  charity's public volunteering page and notes what has changed since last time. It
  says who it is, honours whatever the site's robots file asks of it, and makes one
  request a second &mdash; about the load of one person reading a couple of pages.</p>
<p>Anything that matters is read by a person before it is printed. Changes to what a
  charity asks of you, whether a post is open, or when the next intake falls never
  go in automatically. Those are the facts that waste your day if they are wrong.</p>
<p>Silence is set as silence. Most charity pages do not say whether a check is
  needed, and where a page does not say, the notice says exactly that. It is less
  satisfying than a clean answer and rather more honest.</p>
</div>

<div class="particulars">
  <h2>If this paper stops being set</h2>
  <dl>
    <dt>After 3 weeks</dt><dd>Notices stop printing anything we can no longer stand
      behind, and keep only the link.</dd>
    <dt>After 2 months</dt><dd>A notice on every page says the paper is no longer
      being kept up, and points you elsewhere.</dd>
  </dl>
</div>
<p class="footnote"><b>Why bother</b>
  A stale sheet that admits it is worth more than a fresh-looking one that misleads.
  The decay above is built in rather than hoped for.</p>"""),

    # Read by a charity's web administrator, not by a volunteer. Plain, factual,
    # and it exists because the crawler's user agent has to point somewhere a
    # person can act on. Served by the same repository that runs the crawler,
    # which means it cannot drift out of date with the thing it describes.
    "/bot/": ("About our crawler", True,
              "What SomewhereToHelpBot does, how often, and how to stop it.", """
<p class="kicker">For charity web administrators</p>
<h1>About our crawler</h1>
<p class="standfirst">If you have seen <code>SomewhereToHelpBot</code> in your
  server logs, this page explains what it is and how to make it stop.</p>
<div class="r-thin" style="margin:14px 0 16px"></div>

<div class="prose">
<p class="dropcap">The 8 Houses Daily prints volunteering notices from London
  homelessness charities and links every one of them to the charity's own page. To
  keep those notices accurate, an automated reader visits each charity's public
  volunteering page once a week and notes what has changed.</p>
<p>It reads one page and, at most, six pages linked from it. It does not submit
  forms, follow apply links, create accounts, or look at anything behind a login.
  It stores what a role involves, when it runs and what you ask of volunteers — as
  our own summary, not as a copy of your text.</p>
</div>

<div class="particulars">
  <h2>The particulars</h2>
  <dl>
    <dt>Identifies as</dt><dd><code>SomewhereToHelpBot/1.0</code></dd>
    <dt>Frequency</dt><dd>Once a week, early on a Sunday</dd>
    <dt>Rate</dt><dd>One request per second, single-threaded &mdash; about the
      load of one person reading a couple of pages</dd>
    <dt>robots.txt</dt><dd>Honoured. Disallow us and we stop, and the listing
      keeps only a link to you</dd>
    <dt>Conditional requests</dt><dd>Yes &mdash; an unchanged page costs you a 304
      and nothing else</dd>
  </dl>
</div>

<div class="section">
  <div class="section-bar"><h2>How to stop it</h2></div>
  <div class="prose" style="margin-top:12px">
  <p>Any one of these works, and none of them needs a conversation:</p>
  <p><b>Email us.</b> Write to <a href="mailto:tek@8houses.co.uk">tek@8houses.co.uk</a>
    and say so. We remove the organisation entirely &mdash; not hidden, removed
    from the build &mdash; and stop reading your site. There is nothing to argue
    about and we will not ask why.</p>
  <p><b>Or use robots.txt.</b> Add this to yours and the crawler will not return:</p>
  <pre><code>User-agent: SomewhereToHelpBot
Disallow: /</code></pre>
  <p><b>Or correct us instead.</b> If the problem is that a notice is wrong rather
    than that it exists, tell us what it should say and it will be fixed within a
    few days.</p>
  </div>
</div>

<p class="footnote"><b>What we are not</b>
  We are not a charity, and we do not vet or rank the organisations we list. We
  print notices and send people to you. There is no advertising, and nothing here
  is paid for or sponsored.</p>"""),

    "/five-minutes/": ("Five minutes instead", True,
                       "Useful things you can do about homelessness in London in five minutes.", """
<p class="kicker">For readers in a hurry</p>
<h1>Five minutes instead</h1>
<p class="standfirst">Most people who read a sheet like this will not end up
  volunteering, and that is perfectly all right. These take five minutes and are
  worth doing.</p>
<div class="r-thin" style="margin:14px 0 16px"></div>

<div class="five">
  <a href="https://www.streetlink.org.uk" rel="nofollow">
    <b>Report someone sleeping rough</b>
    <p>StreetLink sends the location to a local outreach team and tells you what came
      of it. Not for an emergency &mdash; call 999 for that.</p></a>
  <div><b>Give the thing they are short of</b>
    <p>A charity would usually rather have what it needs than a bag of assorted
      clothes. Most publish a list. Read it before you gather anything.</p></div>
  <div><b>Set a reminder for the autumn</b>
    <p>Winter shelters recruit from about October and fill quickly. A note in your
      calendar now beats finding out in January.</p></div>
</div>
<p class="footnote" style="margin-top:24px"><b>Or</b>
  <a href="/">Read the notices</a> after all.</p>"""),
}


def build_static_pages(fresh, n_orgs, total):
    """/help/ carries neither the search box nor the role corpus.

    Someone who lands there needs a service, not a charity finder, and the most
    prominent interactive element on that page should not be a search input. The
    others simply don't use the data, so there's no reason to ship 40KB of it.
    """
    for path, (title, article, desc, inner) in STATIC_PAGES.items():
        cls = "wrap article" if article else "wrap"
        body = f'<main class="{cls}" id="main">{inner}</main>'
        write(path, shell(title=f"{title} — {SITE_NAME}", desc=desc,
                          path=path, body=body,
                          search=(path != "/help/"),
                          needs_data=False,
                          banner_html="" if path == "/help/"
                                      else banner(fresh, n_orgs, total)))
    return list(STATIC_PAGES)


def build_assets(orgs, opps, fresh):
    (DIST / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy(STATIC / "app.css", DIST / "assets" / "app.css")
    shutil.copy(STATIC / "app.js", DIST / "assets" / "app.js")
    # Publish only the prepared web copies; keep the large source films intact.
    video_out = DIST / "assets" / "videos"
    video_out.mkdir(parents=True, exist_ok=True)
    for name, _ in DOOR_VIDEO.values():
        for suffix in ("mp4", "webp"):
            shutil.copy(STATIC / "videos" / "web" / f"{name}.{suffix}",
                        video_out / f"{name}.{suffix}")
    bundle = {"orgs": {k: {"n": v["name"], "u": v["volunteer_url"],
                           "w": v["website_url"], "cn": v.get("charity_number"),
                           "a": v.get("aliases", []), "b": v.get("boroughs", [])}
                       for k, v in orgs.items()},
              "opps": opps,
              "meta": {"orgs_listed": len(orgs), "roles": len(opps),
                       "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d")}}
    # Ship only what the client reads. app.js filters server-rendered notices by
    # data-id rather than rebuilding them, so it needs the fields match() tests
    # plus the title for the lookup field — nine of twenty-three. Provenance
    # alone was 28KB of data nothing on the client can use, on every results page.
    CLIENT_FIELDS = ("id", "org_id", "title", "commitment", "activity", "status",
                     "who_can_apply", "location_type", "postcode_district")
    slim = dict(bundle)
    slim["opps"] = [{k: o[k] for k in CLIENT_FIELDS} for o in bundle["opps"]]
    (DIST / "assets" / "data.js").write_text(
        "window.__DATA__=" + json.dumps(slim, separators=(",", ":")) + ";\n", encoding="utf-8")
    # A separate asset, not inlined: 43KB of borough geometry across 45 pages
    # would be 2MB of duplicated bytes. One file, cached once.
    m = map_data()
    if m:
        (DIST / "assets" / "map.js").write_text(
            "window.__MAP__=" + json.dumps(m, separators=(",", ":")) + ";\n", encoding="utf-8")


def build_meta(paths):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{BASE_URL}{p}</loc><lastmod>{now}</lastmod></url>"
                   for p in sorted(set(paths)))
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>\n", encoding="utf-8")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    (DIST / "404.html").write_text(shell(
        title=f"Not found — {SITE_NAME}", desc="Page not found.", path="/404",
        noindex=True,
        body='<main class="wrap" id="main"><h1>That page isn\'t here</h1>'
             '<p class="lede">It may have been a filter combination that no longer '
             'has results. <a href="/all/">See everything</a>.</p></main>'), encoding="utf-8")


# ------------------------------------------------------------------ invariants

def check(orgs, opps, fresh) -> list[str]:
    """Build-time invariants. A promise enforced by code beats one in a document.

    These are the failure modes that would hurt someone rather than merely look
    untidy, so the build refuses to produce output when any of them trips.
    """
    errs = []

    # Validate every record against the schema before anything else.
    #
    # This was missing, and it let a hand-written record with an over-long field
    # build 99 pages successfully. The pipeline validates its own output, so the
    # gap only ever showed up for records written by a person — which is exactly
    # the path with no other machine checking it.
    try:
        sys.path.insert(0, str(ROOT / "pipeline"))
        import schema as _schema
        from jsonschema import ValidationError as _VE, validate as _validate
        for op in opps:
            try:
                _validate(op, _schema.RECORD_SCHEMA)
            except _VE as exc:
                path = ".".join(str(x) for x in exc.absolute_path) or "(root)"
                errs.append(f'{op.get("id", "?")}: {path} — {exc.message}')
        for org in orgs.values():
            try:
                _validate(org, _schema.ORG_SCHEMA)
            except _VE as exc:
                path = ".".join(str(x) for x in exc.absolute_path) or "(root)"
                errs.append(f'{org.get("id", "?")}: {path} — {exc.message}')
    except ImportError:
        # Not an error. Cloudflare's build command is `python3 site/build.py`
        # with no pip install, so making jsonschema a hard requirement would
        # break deployment outright — which the first version of this did.
        #
        # Schema conformance is a data-hygiene question, and the right place for
        # it is a test (see test_every_record_matches_the_schema) plus the
        # pipeline, which validates its own output. The ten invariants below are
        # the ones that stop a reader being misled, and they are pure stdlib.
        print("  (jsonschema not installed — records not schema-checked here)")

    seen_ids = {}
    for op in opps:
        # A duplicate id silently overwrites a page, so one role vanishes and the
        # other appears twice in listings.
        if op["id"] in seen_ids:
            errs.append(f'{op["id"]}: duplicate role id (also in '
                        f'{seen_ids[op["id"]]})')
        seen_ids[op["id"]] = op["org_id"]
        oid = op["id"]
        org = orgs.get(op["org_id"])
        if not org:
            errs.append(f"{oid}: org {op['org_id']} missing")
            continue
        # An opt-out must remove the organisation, not merely hide the card.
        if org.get("contact", {}).get("consent") == "opt_out":
            errs.append(f"{oid}: {org['name']} has opted out but is in the build")
        if not (op.get("apply_url") or org.get("volunteer_url")):
            errs.append(f"{oid}: nothing to link to — the button would lie")
        # "No DBS needed" is a claim that gets people turned away if wrong.
        s = op["screening"]
        if s["dbs"] == "none" and "screening.dbs" not in op["provenance"].get(
                "verified_fields", []):
            errs.append(f"{oid}: claims no DBS needed without a verified source")
        if op["status"] == "open" and suppressed(op, fresh):
            pass  # rendering already downgrades this; not an error
        if op["url_specificity"] == "org_homepage" and op["provenance"]["confidence"] > 0.5:
            errs.append(f"{oid}: only a homepage to link to, but high confidence — "
                        "check the URL is right")
        # "Closed for the season" without saying which season is a dead end: the
        # visitor learns they can't do it now and nothing about when they could.
        if op["status"] == "seasonal_closed" and not op.get("seasonal_window"):
            errs.append(f"{oid}: seasonal_closed but no seasonal_window — the card "
                        "would say 'closed for the season' and not say which")
        # A minimum term only means something for an ongoing commitment.
        if op.get("min_term_months") and op["commitment"] in ("one_off", "flexible"):
            errs.append(f'{oid}: {op["min_term_months"]}-month minimum on a '
                        f'{op["commitment"]} role — contradictory')
        # A link that leaves the charity's own domain is either a third-party
        # platform (fine, but the freshness check is then watching the wrong site)
        # or a stale URL. Either way a human should look.
        import urllib.parse as _u
        if op.get("apply_url"):
            ad = _u.urlparse(op["apply_url"]).netloc.replace("www.", "")
            od = _u.urlparse(org["website_url"]).netloc.replace("www.", "")
            # A subdomain of the charity's own domain is still the charity.
            # Crisis run their volunteering board at volunteer.crisis.org.uk and
            # this refused it, which was the invariant being wrong rather than
            # the data. Note the leading dot: evil-crisis.org.uk does not match.
            same = ad == od or ad.endswith("." + od)
            # Plenty of charities run their volunteering on a hosted platform —
            # Shelter on Better Impact, others on Reach or Assemble — so a
            # foreign apply_url is not automatically wrong. What must not happen
            # is an *unreviewed* one: that is where a model inventing a URL, or a
            # link going stale, would slip through.
            #
            # So the bar is acknowledgement rather than prohibition: a person has
            # looked at it, and the record names the platform. Machine-extracted
            # records cannot satisfy either condition, which is the point.
            # The declaration must name the actual foreign domain. Looking for
            # the word "platform" was too loose and also too narrow: Big Issue
            # run their volunteering on bigissue.com while the Foundation's site
            # is bigissue.org.uk — the same organisation on two domains, which is
            # not a platform at all. Naming the domain is unambiguous and leaves
            # an auditable trail.
            pv = op.get("provenance", {})
            declared = any(ad in x for x in pv.get("unsupported_fields", []))
            waived = bool(pv.get("reviewed_by_human")) and declared
            if ad and od and not same and not waived:
                errs.append(f"{oid}: apply_url is on {ad} but the charity is {od} — "
                            "third-party platform or stale link. If it is their "
                            "own platform, review the record and name the "
                            "platform in provenance.unsupported_fields")
        # An unverified status claim rendered as fact.
        if op["status"] == "open" and "status" in op["provenance"].get(
                "unsupported_fields", []):
            errs.append(f"{oid}: status 'open' but provenance says status is "
                        "unsupported by the source page")
    return errs


def build_preview():
    """One self-contained file with the assets inlined.

    Exists because a hand-maintained prototype alongside a generated site is two
    sources of truth, and they had already drifted. This is generated from the same
    build, so it cannot.
    """
    # /all/ rather than the home page: the home page's doors are links to other
    # pages, which don't resolve in a standalone file, whereas /all/ carries the
    # sentence builder, the map and every role — all of which work client-side.
    h = (DIST / "all" / "index.html").read_text(encoding="utf-8")
    for placeholder, asset in [
            ('<link rel="stylesheet" href="/assets/app.css">', "app.css"),
            ('<script src="/assets/data.js"></script>', "data.js"),
            ('<script src="/assets/app.js"></script>', "app.js")]:
        body = (DIST / "assets" / asset).read_text(encoding="utf-8")
        tag = f"<style>{body}</style>" if asset.endswith(".css") \
            else f"<script>{body}</script>"
        h = h.replace(placeholder, tag)
    (DIST / "preview.html").write_text(h, encoding="utf-8")
    return h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    orgs, opps, fresh, total = load()
    TOTAL[0] = total
    COUNTS[0], COUNTS[1] = len(opps), len(orgs)
    if not opps:
        print("No roles in data/orgs/*.json. Run the pipeline first.")
        return 2

    errs = check(orgs, opps, fresh)
    if errs:
        print("Build refused — invariants failed:\n")
        for x in errs:
            print("  !", x)
        return 2

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    build_home(orgs, opps, fresh, total)
    paths = ["/"]
    paths += build_filters(orgs, opps, fresh, total)
    paths += build_roles(orgs, opps, fresh)
    paths += build_charities(orgs, opps, fresh)
    paths += build_static_pages(fresh, len(orgs), total)
    build_assets(orgs, opps, fresh)
    build_meta(paths)
    build_preview()

    n = len(list(DIST.rglob("index.html")))
    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"Built {n} pages · {size / 1024:.0f} KB total")
    print(f"  {len(orgs)} charities · {len(opps)} roles · {total} orgs in scope")
    print(f"  filters {len([p for p in paths if p.count('/') <= 3 and not p.startswith(('/role', '/charity'))])}"
          f" · roles {len([p for p in paths if p.startswith('/role')])}"
          f" · charities {len([p for p in paths if p.startswith('/charity')])}")
    if fresh.get("site_banner"):
        print("  ! decay banner is ACTIVE")

    if args.serve:
        import http.server, os, socketserver
        os.chdir(DIST)
        print(f"\nhttp://localhost:{args.port}")
        socketserver.TCPServer(("", args.port),
                               http.server.SimpleHTTPRequestHandler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
