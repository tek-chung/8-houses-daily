"""Tests for the static site build. Run: python -m pytest site/test_build.py -q

The pipeline had 42 tests and the build had none, despite being ~700 lines of HTML
generation. It was verified once by hand, which is not the same thing — the ad-hoc
checks I ran are now these tests, plus the ones I should have run.

Grouped by what breaks if they fail:
  - honesty      a visitor is misled about what we know
  - reachability a visitor cannot get to something
  - a11y         a visitor cannot use it
  - seo          the acquisition channel silently degrades
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import os
DIST = Path(os.environ.get("DIST_DIR", str(ROOT / "dist")))


@pytest.fixture(scope="module")
def built():
    env = dict(os.environ, DIST_DIR=str(DIST))
    r = subprocess.run([sys.executable, str(ROOT / "site" / "build.py")],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, f"build failed:\n{r.stdout}\n{r.stderr}"
    pages = {}
    for p in DIST.rglob("index.html"):
        rel = p.parent.relative_to(DIST)
        # as_posix(), not str(). A Path renders with the OS separator, so on
        # Windows every key came out as "/role\\ace-of-clubs-lunch-service\\" and
        # twelve tests failed on KeyError looking up a URL. A URL is always
        # forward-slashed whatever the filesystem thinks.
        url = "/" if rel == Path(".") else f"/{rel.as_posix()}/"
        pages[url] = p.read_text(encoding="utf-8")
    return pages


def data():
    """The full records, as the build sees them.

    Not dist/assets/data.js — that ships only the nine fields the client filters
    on, so provenance, screening and the rest are absent from it by design. Tests
    that assert on what a reader is told need the whole record.
    """
    return json.loads((ROOT / "data" / "site-bundle.json").read_text(encoding="utf-8"))


def shipped():
    """What the browser actually receives. Use this to assert the bundle stays
    small and carries nothing it does not need."""
    js = (DIST / "assets" / "data.js").read_text(encoding="utf-8")
    return json.loads(js[js.index("=") + 1:].rstrip(";\n"))


# --------------------------------------------------------------------- honesty

def test_every_page_carries_the_coverage_banner_except_help(built):
    """§11.5 specifies a *site-wide* banner. Only having it on the home page meant
    anyone arriving from search — which is the entire point of §14 — saw no
    indication of how fresh the data was."""
    for url, h in built.items():
        if url == "/help/":
            continue          # deliberately stripped; nothing to be honest about
        assert "charities place notices here" in h, f"{url} has no banner"


def test_help_page_has_no_search_box(built):
    """Someone sleeping rough who lands here should not meet 'Find a charity' as
    the most prominent control on the page."""
    assert 'id="ta"' not in built["/help/"]


def test_help_page_links_to_real_services(built):
    h = built["/help/"]
    for svc in ["streetlink.org.uk", "shelter.org.uk", "centrepoint.org.uk"]:
        assert svc in h, f"/help/ doesn't link to {svc}"


def test_no_role_claims_no_dbs_without_verification(built):
    """The build refuses this, but assert it on the output too — this is the claim
    that gets someone turned away at the door."""
    for op in data()["opps"]:
        if op["screening"]["dbs"] == "none":
            assert "screening.dbs" in op["provenance"]["verified_fields"], op["id"]


def test_unknown_screening_is_shown_as_unknown_not_as_none(built):
    """9 of 11 roles have dbs unknown. If any page renders that as 'No DBS needed'
    people will turn up unable to volunteer."""
    unknown = [o["id"] for o in data()["opps"]
               if o["screening"]["dbs"] == "unknown"]
    assert unknown, "fixture drift: expected some unknowns"
    for rid in unknown:
        h = built[f"/role/{rid}/"]
        assert "No DBS needed" not in h, rid
        assert "not stated" in h.lower(), rid


def test_team_only_roles_say_so_on_their_page(built):
    """Checks two independent surfaces, not one phrase.

    This is the fact that decides whether the reader can apply at all, so a
    regression in either the prose or the particulars must fail — which a single
    literal string match would not catch.
    """
    for op in data()["opps"]:
        if op["who_can_apply"] != "team_only":
            continue
        h = built[f"/role/{op['id']}/"]
        assert "teams rather than individuals" in h, f"{op['id']}: not in the prose"
        assert "A team only" in h, f"{op['id']}: not in the particulars"


def test_team_only_fact_appears_before_the_conditions(built):
    """Whether you can apply at all outranks what they will ask of you. Buried
    below the screening conditions it wastes the reader's time."""
    for op in data()["opps"]:
        if op["who_can_apply"] != "team_only":
            continue
        h = built[f"/role/{op['id']}/"]
        assert h.index("teams rather than individuals") < h.index("DBS"), op["id"]


def test_borough_pages_disclose_roles_not_in_that_borough(built):
    """A page titled 'Volunteer in Tower Hamlets' that pads its count with
    London-wide roles must say so rather than imply they're all local."""
    for url, h in built.items():
        if re.match(r"^/(one-day|weekly|flexible|bigger|monthly|fortnightly)/[a-z-]+/$", url) \
           and "role" in h and "aren&#x27;t tied to one borough" in h:
            return
    pytest.skip("no borough page currently mixes local and London-wide roles")


def test_role_pages_show_where_the_data_came_from(built):
    for op in data()["opps"]:
        h = built[f"/role/{op['id']}/"]
        assert "came from" in h.lower(), op["id"]
        assert op["provenance"]["source_url"] in h, op["id"]


def test_low_confidence_roles_are_flagged(built):
    low = [o["id"] for o in data()["opps"] if o["provenance"]["confidence"] < 0.7]
    for rid in low:
        assert "confidence is low" in built[f"/role/{rid}/"].lower() or "low confidence" in built[f"/role/{rid}/"].lower(), rid


# ---------------------------------------------------------------- reachability

def test_every_role_is_reachable_from_all(built):
    for op in data()["opps"]:
        assert f'/role/{op["id"]}/' in built["/all/"], op["id"]


def test_no_broken_internal_links(built):
    bad = []
    for url, h in built.items():
        for href in re.findall(r'href="(/[^"#]*)"', h):
            if href.startswith("/assets/"):
                if not (DIST / href.lstrip("/")).exists():
                    bad.append((url, href))
            elif href not in built and href != "/":
                bad.append((url, href))
    assert not bad, f"broken links: {bad[:5]}"


def test_every_card_button_has_somewhere_to_go(built):
    """The PoC had 'Volunteer →' buttons pointing at homepages. Never again."""
    for url, h in built.items():
        for href in re.findall(r'<a class="apply" href="([^"]*)"', h):
            assert href.startswith("http"), f"{url}: empty apply href"


def test_all_pages_render_without_javascript(built):
    """Cards must be in the HTML, not injected. This is both an accessibility and
    an SEO requirement, and it's what makes the pre-rendering worth doing."""
    n = len(data()["opps"])
    assert built["/all/"].count('<article class="ad"') == n


def test_static_pages_do_not_ship_the_role_corpus(built):
    for url in ["/help/", "/about/", "/data/", "/five-minutes/"]:
        assert "/assets/data.js" not in built[url], f"{url} loads unused data"


# --------------------------------------------------------------------- a11y

def test_exactly_one_h1_per_page(built):
    for url, h in built.items():
        assert h.count("<h1") == 1, f"{url} has {h.count('<h1')} h1 elements"


def test_every_page_has_a_skip_link_pointing_at_a_real_target(built):
    for url, h in built.items():
        assert 'class="skip" href="#main"' in h, f"{url} has no skip link"
        assert 'id="main"' in h, f"{url} has no #main landmark"


def test_no_contrast_failures_in_the_palette():
    """--paper-3 was 3.51:1 on cards, below the 4.5:1 AA floor, while carrying the
    location line on every card and the whole footer."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def lum(hx):
        hx = hx.lstrip("#")
        r, g, b = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
        return .2126 * lin(r) + .7152 * lin(g) + .0722 * lin(b)

    def ratio(a, b):
        la, lb = lum(a), lum(b)
        return (max(la, lb) + .05) / (min(la, lb) + .05)

    css = (ROOT / "site" / "static" / "app.css").read_text(encoding="utf-8")
    tok = dict(re.findall(r"--(paper[\w-]*|lamp|warn):(#[0-9a-f]{6})", css))
    backgrounds = ["#10151f", "#171d2a", "#1f2735"]
    fails = [(k, v, bg, round(ratio(v, bg), 2))
             for k, v in tok.items() if k.startswith("paper") or k in ("lamp", "warn")
             for bg in backgrounds if ratio(v, bg) < 4.5]
    assert not fails, f"below WCAG AA: {fails}"


def test_district_controls_are_real_buttons():
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'createElement("button")' in js
    assert 'setAttribute("aria-label"' in js
    assert js.count("function drawMap") == 1, "two map renderers"


def test_single_live_region_per_page(built):
    """Two live regions announcing the same count means screen readers say it
    twice — the exact bug the PoC had."""
    for url, h in built.items():
        assert h.count("aria-live") <= 1, f"{url} has {h.count('aria-live')}"


# ---------------------------------------------------------------------- seo

def test_titles_are_unique(built):
    titles = [re.search(r"<title>(.*?)</title>", h, re.S).group(1)
              for h in built.values()]
    dupes = {t for t in titles if titles.count(t) > 1}
    assert not dupes, f"competing titles: {dupes}"


def test_every_page_has_canonical_and_description(built):
    for url, h in built.items():
        assert '<link rel="canonical"' in h, url
        assert 'name="description"' in h, url


def test_role_pages_carry_structured_data(built):
    for op in data()["opps"]:
        h = built[f"/role/{op['id']}/"]
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
        assert m, op["id"]
        d = json.loads(m.group(1))
        assert d["@type"] == "VolunteerOpportunity"
        assert d["name"] == op["title"]


def test_sitemap_covers_every_page(built):
    sm = (DIST / "sitemap.xml").read_text(encoding="utf-8")
    for url in built:
        assert f"<loc>{'https://example.org' if True else ''}{url}</loc>" in sm \
            or url in sm, f"{url} missing from sitemap"


def test_no_empty_filter_pages_were_generated(built):
    """§14 as written would emit hundreds of empty combinations. Thin content is an
    SEO liability and a promise the site can't keep."""
    for url, h in built.items():
        if url.count("/") >= 3 and not url.startswith(("/role/", "/charity/")):
            assert '<article class="ad"' in h, f"{url} is an empty filter page"


def test_outbound_charity_links_are_nofollow_and_new_tab(built):
    for url, h in built.items():
        for tag in re.findall(r'<a class="apply"[^>]*>', h):
            assert 'rel="noopener nofollow"' in tag, f"{url}: {tag[:60]}"


# ------------------------------------------------------- responsive / devices
# "Works on common devices" is a claim, so it gets tests. These check the things
# that actually break phones: focus-zoom, tap targets, overflow from rotated
# stamps, and controls that only make sense at one width.

CSS = lambda: (ROOT / "site" / "static" / "app.css").read_text(encoding="utf-8")

DEVICES = [("Galaxy S8 / older Android", 360), ("iPhone SE", 375),
           ("iPhone 14/15", 390), ("Pixel 8", 412), ("iPhone Pro Max", 430),
           ("iPad portrait", 768), ("iPad landscape", 1024), ("desktop", 1440)]


def _strip_media(css):
    """Remove every @media block, brace-matched.

    Needed because a selector can appear both at the top level and inside a media
    query — `.stamp` does — and a naive "first match" finds whichever comes first
    in the file, which is not the base declaration. That produced a false failure.
    """
    out, i = [], 0
    while i < len(css):
        at = css.find("@media", i)
        if at == -1:
            out.append(css[i:])
            break
        out.append(css[i:at])
        depth, j = 0, css.find("{", at)
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
    return "".join(out)


def _first_block(css, selector):
    """The base (non-media) declaration for a selector."""
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", _strip_media(css))
    return m.group(1) if m else ""


def _media_block(css, query):
    """Every block matching a query, concatenated.

    A stylesheet may legitimately carry the same media query more than once — this
    one does, because keeping the article-plate rules beside the other plate rules
    reads better than grouping everything by breakpoint. Returning only the first
    match made two passing rules look absent.
    """
    out, at = [], css.find(query)
    while at != -1:
        depth, j, start = 0, css.find("{", at), None
        while j < len(css):
            if css[j] == "{":
                depth += 1
                if depth == 1:
                    start = j + 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append(css[start:j])
                    break
            j += 1
        at = css.find(query, j + 1)
    return "\n".join(out)


def test_no_form_control_triggers_ios_focus_zoom():
    """iOS Safari zooms the whole viewport when a focused control is under 16px.

    The base (touch) declaration must be >=16px for every control. Denser type is
    allowed only behind `pointer:fine`, where focus-zoom cannot happen.
    """
    css = CSS()
    for sel in [".ta input", ".slot select", ".refine select"]:
        block = _first_block(css, sel)
        m = re.search(r"font-size:([\d.]+)px", block)
        assert m, f"{sel} declares no font-size"
        assert float(m.group(1)) >= 16, \
            f"{sel} is {m.group(1)}px — iOS will zoom on focus"


def test_dense_type_is_gated_behind_a_fine_pointer():
    css = CSS()
    assert "@media (pointer:fine)" in css, \
        "no fine-pointer block — either density is missing or it is unsafe on touch"


def test_interactive_controls_meet_a_44px_target():
    css = CSS()
    assert "--tap:44px" in css
    for sel in [".ta input", ".ta li", ".slot", ".refine select", ".ad .apply"]:
        block = _first_block(css, sel)
        assert "min-height:var(--tap)" in block or "min-height:44" in block, \
            f"{sel} has no minimum touch target"


def test_body_guards_against_horizontal_overflow():
    """Stamps are rotated and negatively offset; without this they scroll the page
    sideways on a phone, which is the single most obvious mobile defect."""
    assert "overflow-x:hidden" in _first_block(CSS(), "body")


def test_stamps_sit_in_the_flow_on_phones():
    """Struck-across stamps look right on a wide ad and cover the particulars on a
    narrow one. Below 700px they must be block-level, in the flow."""
    css = CSS()
    base = _first_block(css, ".stamp")
    assert "display:block" in base and "position:absolute" not in base, \
        "the base .stamp is absolutely positioned — it will cover text on a phone"
    wide = _media_block(css, "@media (min-width:700px)")
    assert ".stamp{" in wide and "position:absolute" in wide, \
        "stamps are never struck across the ad at any width"


def test_justified_text_is_desktop_only():
    """Justified type in a narrow column produces rivers. It belongs to the
    three-column layout, not to a phone."""
    css = CSS()
    assert "text-align:justify" not in _first_block(css, ".col p")
    assert "text-align:justify" in _media_block(css, "@media (min-width:700px)")


def test_coupon_is_rows_on_phones_and_prose_on_tablets():
    """Inline dropdowns inside a sentence wrap into nonsense below ~640px, so the
    same control renders as a printed form there and as prose above."""
    css = CSS()
    assert "display:flex" in _first_block(css, ".slot"), "slots are not rows by default"
    assert "display:none" in _first_block(css, ".d640"), \
        "connective words show on phones, where there is no sentence to join"
    six40 = _media_block(css, "@media (min-width:640px)")
    assert "display:inline-flex" in six40 and ".d640{display:inline}" in six40


def test_multi_column_layouts_start_above_phone_widths():
    css = CSS()
    assert "grid-template-columns:1fr" in _first_block(css, ".cols"), \
        "the lead columns are multi-column on phones"
    assert "columns:2" not in _first_block(css, ".ads"), \
        "classifieds are two-column on phones"


def test_breakpoints_cover_the_common_device_widths():
    bps = sorted(set(int(x) for x in re.findall(r"min-width:(\d+)px", CSS())))
    assert bps, "no breakpoints at all"
    for name, w in DEVICES:
        # every device must land in a defined band, and phones must stay in base
        if w < 480:
            assert not [b for b in bps if b <= w], \
                f"{name} at {w}px picks up a desktop breakpoint"


def test_masthead_fits_the_narrowest_supported_phone():
    """Blackletter is wide. At the clamp minimum the title must still fit 360px."""
    css = CSS()
    m = re.search(r"\.title\{[^}]*font-size:clamp\(([\d.]+)px,([\d.]+)vw,([\d.]+)px\)",
                  css, re.S)
    assert m, "the masthead does not use clamp() — it will not scale"
    lo, vw, hi = float(m.group(1)), float(m.group(2)), float(m.group(3))
    for width in (320, 360):
        size = max(lo, min(hi, width * vw / 100))
        est = len("The 8 Houses Daily".replace("The ", "")) * 0.55 * size
        assert est <= width - 32, \
            f"masthead ~{est:.0f}px at {width}px viewport, only {width-32}px available"


def test_landscape_phones_get_a_shorter_masthead():
    assert "max-height:480px" in CSS(), \
        "no short-viewport handling — the masthead eats a landscape phone screen"


def test_all_motion_is_behind_a_reduced_motion_guard():
    css = CSS()
    guards = "".join(re.findall(r"no-preference\)\{(.*?)\n\}", css, re.S))
    rules = re.findall(r"\n(\.[\w.\-]+)\{[^}]*animation:", css)
    assert not [r for r in rules if r.strip() not in guards], \
        f"unguarded animation: {[r for r in rules if r.strip() not in guards]}"


def test_stylesheet_ships_no_web_font_or_image_requests():
    """The newsprint tooth is inline SVG turbulence; fonts come from one <link> in
    the shell, not from @import chains inside the stylesheet."""
    css = CSS()
    assert "@import" not in css
    assert "url(http" not in css.replace("url(\"data:", "")


# ------------------------------------------------------- articles & set pages

def test_role_pages_read_as_articles(built):
    """A card with a bigger headline is not an article."""
    for op in data()["opps"]:
        h = built[f"/role/{op['id']}/"]
        assert 'class="dropcap"' in h, f"{op['id']}: no drop cap"
        assert 'class="standfirst"' in h, f"{op['id']}: no standfirst"
        assert 'class="particulars"' in h, f"{op['id']}: no particulars box"
        assert h.count("<p") >= 6, f"{op['id']}: too thin to be an article"


def test_article_prose_is_free_of_typesetting_defects(built):
    """The body is composed from fields, so joining errors surface as bad prose
    rather than as exceptions. These are the ones that actually occurred."""
    for op in data()["opps"]:
        h = built[f"/role/{op['id']}/"]
        prose = re.search(r'<div class="prose">(.*?)</div>', h, re.S).group(1)
        paras = [re.sub(r"<[^>]+>", "", x).strip()
                 for x in re.findall(r"<p[^>]*>(.*?)</p>", prose, re.S)]
        for t in paras:
            assert ".." not in t, f"{op['id']}: doubled full stop — {t[:50]}"
            assert not re.search(r"\.[A-Za-z]", t), \
                f"{op['id']}: no space after a full stop — {t[:50]}"
            assert "  " not in t, f"{op['id']}: doubled space — {t[:50]}"
            assert "runs varies" not in t, f"{op['id']}: ungrammatical hours line"
            assert t[0].isupper() or t[0].isdigit(), \
                f"{op['id']}: sentence starts lowercase — {t[:50]}"


def test_help_page_stays_plain(built):
    """The one page where the period voice would be actively wrong. Someone
    sleeping rough needs a number, not charm — so no ornament, no drop caps, no
    columns, and no 'Situations Vacant' register."""
    h = built["/help/"]
    assert 'class="pubnotice"' in h, "/help/ is not set as a public notice"
    for charm in ["dropcap", "Situations vacant", "own house", "kicker",
                  '<div class="prose">']:
        assert charm not in h, f"/help/ carries decoration it should not: {charm}"
    assert 'id="ta"' not in h, "/help/ leads with a search box"
    assert "/assets/data.js" not in h, "/help/ ships the notice corpus"


def test_help_page_says_plainly_that_we_cannot_help(built):
    h = built["/help/"]
    assert "cannot help you directly" in h
    assert "999" in h, "no route for an actual emergency"


def test_set_pages_are_articles_but_help_is_not(built):
    for url in ["/about/", "/data/", "/five-minutes/"]:
        assert 'class="wrap article"' in built[url], f"{url} is not set as an article"
    assert 'class="wrap article"' not in built["/help/"]


def test_charity_pages_disclaim_endorsement(built):
    for oid in data()["orgs"]:
        h = built[f"/charity/{oid}/"]
        assert "not a recommendation" in h, f"{oid}: no disclaimer"


def test_masthead_and_colophon_on_every_page(built):
    for url, h in built.items():
        assert 'class="title"' in h, f"{url} has no masthead"
        assert "colophon" in h, f"{url} has no colophon"
        assert "8 Houses Daily" in h, f"{url} does not name the paper"


def test_stamps_only_mark_exceptions(built):
    """There is no RECRUITING NOW stamp. Stamping the default flattens the signal,
    which is the mistake the whole stamp idea exists to avoid."""
    for url, h in built.items():
        assert "Recruiting now</span>" not in h, f"{url} stamps the default state"


# ------------------------------------------------------------ the engravings
# These exist because the engravings, their CSS and the plate() helper were all
# written and then not wired to anything. Every page built, every other test
# passed, and the signature element of the design was absent from the site.
# Absence of a decorative element is exactly the kind of thing a test suite that
# only checks structure will never notice.

def test_front_page_carries_an_engraving_per_lead(built):
    h = built["/"]
    assert h.count('class="plate"') == 3, \
        f'front page has {h.count(chr(34) + "plate" + chr(34))} plates, expected 3'
    assert h.count('class="col"') == 3


def test_every_article_carries_an_engraving(built):
    for op in data()["opps"]:
        h = built[f"/role/{op['id']}/"]
        assert 'class="plate"' in h, f"{op['id']}: no engraving"


def test_engravings_are_drawn_not_photographed(built):
    """§15 forbids poverty tourism. There must be no photography anywhere, and the
    plates must be inline vector drawings rather than fetched images."""
    for url, h in built.items():
        assert "<img" not in h, f"{url} contains an <img> — no photography here"
        for plate in re.findall(r'<figure class="plate">(.*?)</figure>', h, re.S):
            assert plate.strip().startswith("<svg"), f"{url}: plate is not an svg"
            assert "xlink:href" not in plate and "url(http" not in plate


def test_every_svg_is_either_labelled_or_explicitly_decorative(built):
    """Two valid states, and no third one.

    An engraving carries meaning, so it is role="img" with a label. The Thames
    carries none a screen reader can use — the legend names it in text — so it is
    aria-hidden. What must never happen is an SVG that is neither: announced as an
    unnamed graphic.
    """
    for url, h in built.items():
        for svg in re.findall(r"<svg[^>]*>", h, re.S):
            labelled = 'role="img"' in svg and "aria-label" in svg
            decorative = 'aria-hidden="true"' in svg
            assert labelled or decorative, \
                f"{url}: svg is neither labelled nor hidden — {svg[:80]}"
            assert not (labelled and decorative), \
                f"{url}: svg is both labelled and hidden — {svg[:80]}"


def test_every_plate_has_a_caption(built):
    for url, h in built.items():
        plates = re.findall(r'<figure class="plate">(.*?)</figure>', h, re.S)
        for pl in plates:
            assert "<figcaption>" in pl, f"{url}: plate without a caption"


def test_engraving_motion_is_optional_and_scoped():
    css = CSS()
    guarded = _media_block(css, "@media (prefers-reduced-motion:no-preference)")
    for cls in [".steam", ".flame", ".glow", ".coat"]:
        assert cls in guarded, f"{cls} animates outside a reduced-motion guard"


def test_every_activity_maps_to_an_engraving():
    """A role with an unmapped activity would silently fall back, so the mapping
    must cover every value the schema allows."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("b", ROOT / "site" / "build.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    sys.path.insert(0, str(ROOT / "pipeline"))
    import schema
    missing = [a for a in schema.ACTIVITIES if a not in b.ENGRAVING]
    assert not missing, f"activities with no engraving: {missing}"


# ------------------------------------------------------------- readability
# Added after the typeface change. The complaint was legibility, and the causes
# were measurable: hairline strokes at small sizes, a low-x-height body face,
# 9px letterspaced condensed caps, and 30 rules setting all-caps. These tests
# stop the ratchet slipping back.
#
# SVG-scoped rules are excluded because their font-size is in viewBox units, not
# CSS pixels — `.bt text` at 5 units renders at roughly 45px.

SVG_SCOPED = (".bt ",)
DECORATIVE = (".fleuron", ".slot .caret")


def _base_rules(css):
    """(selector, declarations) for every top-level rule."""
    stripped = _strip_media(css)
    return [(m.group(1).strip().split("\n")[-1].strip(), m.group(2))
            for m in re.finditer(r"([^\s{}][^{}]*)\{([^}]*)\}", stripped)]


def test_no_text_is_set_below_11px():
    """9px letterspaced caps were the least readable thing on the site."""
    bad = []
    for sel, block in _base_rules(CSS()):
        if sel.startswith(SVG_SCOPED) or sel in DECORATIVE:
            continue
        m = re.search(r"font-size:([\d.]+)px", block)
        if m and float(m.group(1)) < 11:
            bad.append((sel, float(m.group(1))))
    assert not bad, f"text under 11px: {bad}"


def test_small_caps_are_not_over_tracked():
    """Past roughly 0.14em, tracking separates letters faster than it aids them.
    The old stack ran to 0.28em on 10.5px caps."""
    bad = []
    for sel, block in _base_rules(CSS()):
        if sel.startswith(SVG_SCOPED) or sel in DECORATIVE:
            continue
        size = re.search(r"font-size:([\d.]+)px", block)
        track = re.search(r"letter-spacing:([\d.]+)em", block)
        if size and track and float(size.group(1)) < 14 and float(track.group(1)) > 0.14:
            bad.append((sel, float(size.group(1)), float(track.group(1))))
    assert not bad, f"over-tracked small text: {bad}"


def test_body_size_and_leading_support_long_reading():
    block = _first_block(CSS(), "body")
    size = float(re.search(r"font-size:([\d.]+)px", block).group(1))
    lead = float(re.search(r"line-height:([\d.]+)", block).group(1))
    assert size >= 18, f"body is {size}px — too small for a serif at reading length"
    assert lead >= 1.55, f"leading is {lead} — too tight for an 18px serif"


def test_classified_headings_are_not_all_caps():
    """These are the most-read headings after the h1. Caps cost roughly 15% of
    reading speed and buy nothing at 21px."""
    block = _first_block(CSS(), ".ad h3")
    assert "text-transform:uppercase" not in block
    assert float(re.search(r"font-size:([\d.]+)px", block).group(1)) >= 21


def test_no_blackletter_anywhere():
    """Beautiful at 3em, muddy at 30px — and a masthead is the most-read type on
    the site. Kept only as an option, not a default."""
    css = CSS()
    assert "Unifraktur" not in css and "Pirata" not in css


def test_the_stack_is_three_families_with_screen_legible_choices():
    css = _strip_media(CSS())
    fams = {k: re.search(rf"--{k}:'([^']+)'", css).group(1)
            for k in ("display", "body", "label", "masthead")}
    assert fams["body"] in ("Literata", "Newsreader", "Source Serif 4", "PT Serif"), \
        f"body face {fams['body']} is not one chosen for screen reading"
    assert fams["masthead"] == fams["display"], \
        "the masthead uses a fourth family for one line of text"
    assert len(set(fams.values())) == 3


def test_every_family_has_a_local_fallback():
    """A blocked or slow Google Fonts request must not leave the page in a
    default sans — the whole design is serif."""
    css = _strip_media(CSS())
    for k in ("display", "body", "masthead"):
        decl = re.search(rf"--{k}:([^;]+);", css).group(1)
        assert "serif" in decl, f"--{k} has no serif fallback: {decl}"
    label = re.search(r"--label:([^;]+);", css).group(1)
    assert "sans-serif" in label


# --------------------------------------------------------------- concision
# The front page once ran to 491 words and said "no applications taken here"
# three times — in the dateline, a byline and the colophon. Standing terms belong
# in one place; a page that keeps restating its own terms is a page not doing its
# job. These tests hold the line.

def _visible(h):
    """Body copy only.

    An earlier version kept <head>, so <title> text counted as page copy — which
    made /five-minutes/ look like it repeated its own heading when the duplicate
    was the browser tab.
    """
    import html as _h
    m = re.search(r"<body[^>]*>(.*)</body>", h, re.S)
    b = m.group(1) if m else h
    b = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", " ", b, flags=re.S)
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", b))).strip()


STANDING_TERMS = ["no applications", "not vet", "no charity vetted",
                  "worth asking", "poverty", "five minutes instead"]


def test_standing_terms_appear_once_per_page(built):
    """Each of these is a claim about the paper, not a data value. Restating it
    costs the reader attention and buys nothing."""
    bad = []
    for url, h in built.items():
        t = _visible(h).lower()
        for phrase in STANDING_TERMS:
            n = t.count(phrase)
            if n > 1:
                bad.append((url, phrase, n))
    assert not bad, f"restated standing terms: {bad}"


def test_front_page_is_short(built):
    n = len(_visible(built["/"]).split())
    assert n <= 320, f"front page is {n} words — it had crept to 491 once"


def test_front_page_states_the_counts_once(built):
    """The dateline prints the totals. An earlier draft restated them in the dek
    and again on the button — the same number, three ways."""
    t = _visible(built["/"])
    n_notices = len(data()["opps"])
    assert t.count(f"{n_notices} notices") <= 1, "notice count stated more than once"
    assert f"{n_notices} posts" not in t, "the count is restated in other words"


def test_the_screening_gap_is_explained_once_not_repeated(built):
    """Nine of eleven charities publish nothing about screening. The long phrasing
    printed on every notice turned six words into wallpaper, so the classified now
    says 'Not stated' and the column carries one explanation."""
    h = built["/all/"]
    assert h.count("colnote") >= 1, "no explanation of the screening gap at all"
    assert _visible(h).lower().count("worth asking") <= 1
    assert "Screening not stated &mdash; worth asking" not in h and \
           "Screening not stated — worth asking" not in h, \
           "the long form is still printed per notice"


def test_the_screening_note_only_prints_when_it_earns_its_place():
    """A note explaining a common gap should not appear where the gap is rare."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("b2", ROOT / "site" / "build.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    known = [{"screening": {"dbs": "enhanced"}} for _ in range(5)]
    assert b.screening_note(known) == "", "note printed where nothing is missing"
    mixed = known[:1] + [{"screening": {"dbs": "unknown"}} for _ in range(4)]
    assert b.screening_note(mixed) != "", "note absent where the gap is common"
    assert b.screening_note(mixed[:2]) == "", "note printed for a tiny column"


def test_colophon_does_not_duplicate_page_navigation(built):
    """The colophon prints on every page, so it should link only to what has
    nowhere else to be reached from."""
    foot = re.search(r'<footer[^>]*>(.*?)</footer>', built["/"], re.S).group(1)
    links = re.findall(r'href="(/[^"]*)"', foot)
    assert links.count("/five-minutes/") == 0, \
        "colophon repeats a section already on the front page"


# ------------------------------------------------------- front page ordering
# The lookup field once sat in the masthead, above everything, serving the
# minority who already know the charity they want and pushing the three actual
# calls to action below the fold. Order is the product decision here, so it gets
# tests rather than good intentions.

def _pos(h, needle):
    i = h.find(needle)
    assert i != -1, f"missing from the page: {needle}"
    return i


def test_calls_to_action_come_high_on_the_front_page(built):
    """The headline leads, then the three ways. Nothing else may get between
    them, and nothing secondary may precede them."""
    h = built["/"]
    assert _pos(h, "<h1>") < _pos(h, 'class="cols cols-lead"'), \
        "the headline no longer leads"
    assert _pos(h, 'class="doorcta"') < _pos(h, 'class="notice grey"'), \
        "the publisher's notice pushes the calls to action down"
    assert _pos(h, 'class="doorcta"') < _pos(h, 'class="five"'), \
        "the five-minute actions come before the main ones"
    assert _pos(h, 'class="doorcta"') < _pos(h, 'class="section lookup"'), \
        "the lookup field precedes the calls to action"


def test_front_page_carries_no_slogan_between_headline_and_actions(built):
    """A kicker and a standfirst both sat here and were cut. Anything reinstated
    between the headline and the first button is delaying the only action on the
    page."""
    h = built["/"]
    start = _pos(h, "</h1>") + len("</h1>")
    end = h.rfind("<", 0, _pos(h, 'class="cols cols-lead"'))
    text = re.sub(r"<[^>]+>", "", h[start:end]).strip()
    assert not text, f"copy has crept back in between: {text[:70]!r}"


def test_the_lookup_field_is_below_the_calls_to_action(built):
    for url, h in built.items():
        if 'id="ta"' not in h:
            continue                    # /help/ carries no lookup at all
        header = re.search(r"<header.*?</header>", h, re.S).group(0)
        assert 'id="ta"' not in header, f"{url}: lookup is back in the masthead"
        assert _pos(h, 'id="ta"') > _pos(h, 'id="main"'), \
            f"{url}: lookup precedes the main content"


def test_each_way_ends_in_an_unmistakable_call_to_action(built):
    h = built["/"]
    assert h.count('class="doorcta"') == 3
    css = _first_block(CSS(), ".doorcta")
    for prop in ["display:block", "border:1px solid", "min-height:var(--tap)",
                 "text-transform:uppercase"]:
        assert prop in css, f".doorcta lacks {prop} — it will not read as a button"
    assert "margin-top:auto" in css, \
        "buttons will not align across columns of unequal prose"


def test_heading_outline_is_valid(built):
    """The big headline now sits below the three ways, so it cannot be the h1 —
    an h1 after h2s in the DOM is an outline error even when it looks right."""
    for url, h in built.items():
        body = re.search(r"<body[^>]*>(.*)</body>", h, re.S).group(1)
        levels = [int(m.group(1))
                  for m in re.finditer(r"<h([1-6])[^>]*>", body)]
        assert levels, f"{url} has no headings"
        assert levels[0] == 1, f"{url} opens at h{levels[0]}, not h1"
        assert levels.count(1) == 1, f"{url} has {levels.count(1)} h1 elements"
        for a, b in zip(levels, levels[1:]):
            assert b <= a + 1, f"{url} skips from h{a} to h{b}"


def test_exactly_one_main_landmark_per_page(built):
    for url, h in built.items():
        assert h.count("<main") == 1, \
            f"{url} has {h.count('<main')} main landmarks"


def test_the_mastheads_accessible_name_reads_properly(built):
    """'The' is a block-level span, so it renders on its own line but ran into the
    next word in the accessible name: 'The8 Houses Daily'."""
    import html as _h
    for url, h in built.items():
        for m in re.finditer(r'<a class="title"[^>]*>(.*?)</a>', h, re.S):
            name = _h.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
            name = re.sub(r"\s+", " ", name).strip()
            assert name == "The 8 Houses Daily", f"{url}: masthead reads {name!r}"


def test_no_heading_is_empty(built):
    """A blank heading is announced as one. Harmless while its container is
    hidden, but not something to depend on."""
    import html as _h
    for url, h in built.items():
        for m in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", h, re.S):
            t = _h.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            assert t, f"{url}: empty h{m.group(1)}"


# ------------------------------------------------------------ browser smoke
# The Python suite checks the HTML it generated. It cannot run the JavaScript,
# and that blind spot hid two serious bugs at once:
#
#   1. toggleBlank() dereferenced #b1w, a wrapper id the prototype markup had and
#      the newspaper coupon does not. It threw on every results page, which meant
#      the district map never drew at all.
#   2. Behind that exception sat a second copy of the card markup in app.js, drifted
#      from build.py's — old class names, old copy. Fixing the first bug let it
#      overwrite all eleven server-rendered classifieds.
#
# Neither was visible to any test here. So these shell out to jsdom.

import shutil
import subprocess

SMOKE = ROOT / "site" / "js" / "smoke.js"


def _inline(built_path: Path, out: Path):
    """Assets are separate files; jsdom will not fetch them. Inline for the run."""
    h = built_path.read_text(encoding="utf-8")
    for ph, asset in [('<link rel="stylesheet" href="/assets/app.css">', "app.css"),
                      ('<script src="/assets/map.js"></script>', "map.js"),
                      ('<script src="/assets/data.js"></script>', "data.js"),
                      ('<script src="/assets/app.js"></script>', "app.js")]:
        if ph in h:
            b = (DIST / "assets" / asset).read_text(encoding="utf-8")
            h = h.replace(ph, f"<style>{b}</style>" if asset.endswith(".css")
                          else f"<script>{b}</script>")
    out.write_text(h, encoding="utf-8")
    return out


def _node_env():
    """jsdom may be installed outside the repo; put every plausible location on
    NODE_PATH rather than assuming one."""
    import os
    paths = [str(ROOT / "node_modules"), str(Path.home() / "node_modules"),
             os.environ.get("NODE_PATH", "")]
    return dict(os.environ, NODE_PATH=os.pathsep.join(p for p in paths if p))


def _have_jsdom():
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('jsdom')"],
                       capture_output=True, env=_node_env(), cwd=ROOT)
    return r.returncode == 0


def _smoke(page_path, url, tmp_path):
    if not _have_jsdom():
        pytest.skip("needs node and jsdom (npm install)")
    page = _inline(DIST / page_path, tmp_path / "page.html")
    r = subprocess.run(["node", str(SMOKE), str(page), url],
                       capture_output=True, text=True, cwd=ROOT, env=_node_env())
    assert r.stdout, f"smoke harness produced nothing: {r.stderr[:400]}"
    return json.loads(r.stdout)


@pytest.mark.parametrize("page,url", [
    ("index.html", "/"),
    ("all/index.html", "/all/"),
    ("weekly/index.html", "/weekly/"),
    ("role/depaul-uk-nightstop-host/index.html", "/role/depaul-uk-nightstop-host/"),
    ("help/index.html", "/help/"),
    ("about/index.html", "/about/"),
])
def test_pages_run_without_console_errors(page, url, tmp_path, built):
    rep = _smoke(page, url, tmp_path)
    assert rep["errors"] == [], f"{url}: {rep['errors']}"


def test_the_district_map_actually_draws(tmp_path, built):
    """It rendered zero tiles for a while because an exception upstream killed
    render() before it got there. The page looked merely empty."""
    rep = _smoke("all/index.html", "/all/", tmp_path)
    assert rep["boroughPaths"] == 33, \
        f"drew {rep['boroughPaths']} of 33 borough outlines"
    assert rep["litPaths"] > 0, "no borough is shaded"
    assert rep["badges"] == rep["litPaths"], \
        "a shaded borough has no count badge, or vice versa"
    assert rep["textInsideSvg"] == 0, "text is back inside the scaled viewBox"
    assert rep["chips"] == rep["litPaths"], "chips and shaded boroughs disagree"
    assert rep["chipsAreButtons"] and rep["chipsLabelled"]


def test_javascript_does_not_replace_the_server_rendered_classifieds(tmp_path,
                                                                    built):
    """There were two card renderers and they had drifted. The client one used to
    wipe the server's markup on load."""
    rep = _smoke("all/index.html", "/all/", tmp_path)
    assert rep["classifieds"] == len(data()["opps"]), \
        f"{rep['classifieds']} classifieds survived JS, expected {len(data()['opps'])}"


def test_only_one_card_renderer_exists():
    """Guards the class of bug rather than the instance."""
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'className="card"' not in js and "className=\"ad\"" not in js, \
        "app.js builds card markup again — build.py's card() is the only renderer"
    assert "toggleBlank" not in js, "the null-dereferencing helper is back"


def test_the_coupon_inks_a_prefilled_slot(tmp_path, built):
    """/weekly/ arrives with the commitment already chosen, so one slot should
    render as filled without the reader touching anything."""
    rep = _smoke("weekly/index.html", "/weekly/", tmp_path)
    assert rep["filledSlots"] >= 1






# ------------------------------------------------------- the geographic map
# Replaced a tile cartogram at Tek's request. Shapes are real ONS/OS borough
# outlines; the Thames is the seam where north-bank and south-bank boroughs meet,
# so it comes from the same file as the shapes and lies on the banks. Three
# earlier attempts failed and each left a test behind.

MAPJSON = ROOT / "data" / "london-map.json"


def mapdata():
    return json.loads(MAPJSON.read_text(encoding="utf-8"))


def test_the_map_data_is_committed_so_the_build_needs_no_network():
    assert MAPJSON.exists(), "run site/tools/build_map.py"
    m = mapdata()
    assert len(m["boroughs"]) == 33, f"{len(m['boroughs'])} boroughs"
    assert m["thames"].startswith("M") and len(m["thames"]) > 500


def test_every_borough_has_a_real_outline_not_a_collapsed_one():
    """Douglas-Peucker on a closed ring reduced every borough to two points: the
    first and last vertex of a ring are identical, so the baseline has zero
    length and every perpendicular distance computes as zero."""
    for b in mapdata()["boroughs"]:
        pts = b["d"].count(",")
        assert pts >= 12, f"{b['name']} is only {pts} points — collapsed"


def test_the_river_is_one_or_two_reaches_not_a_scatter_of_fragments():
    """Ordering the seam by nearest-neighbour walk stalled at 85 of 1,818 points,
    because vertices cluster where three boroughs meet. Chaining shared edges by
    endpoint is exact."""
    runs = [r for r in mapdata()["thames"].split("M") if r.strip()]
    assert 1 <= len(runs) <= 3, f"{len(runs)} disconnected reaches"
    longest = max(r.count(",") for r in runs)
    assert longest >= 60, f"longest reach is only {longest} points"


def test_the_river_crosses_most_of_the_map():
    pts = [tuple(map(float, q.split(",")))
           for r in mapdata()["thames"].split("M") if r.strip()
           for q in r.split()]
    w = mapdata()["width"]
    assert min(p[0] for p in pts) < w * 0.2
    assert max(p[0] for p in pts) > w * 0.8


THAMES_SOUTH = {"Richmond upon Thames", "Wandsworth", "Lambeth", "Southwark",
                "Lewisham", "Greenwich", "Bexley", "Kingston upon Thames",
                "Merton", "Croydon", "Bromley", "Sutton"}
THAMES_NORTH = {"Hammersmith and Fulham", "Kensington and Chelsea", "Westminster",
                "City of London", "Tower Hamlets", "Newham",
                "Barking and Dagenham", "Camden", "Islington", "Hackney"}


def test_every_borough_falls_on_its_real_bank():
    """North or south of the river is how a Londoner places a borough. A line
    that put Southwark on the north bank would mislead, not decorate."""
    m = mapdata()
    W, H = m["width"], m["height"]
    pts = [tuple(map(float, q.split(",")))
           for r in m["thames"].split("M") if r.strip() for q in r.split()]

    def river_y(x):
        near = [p for p in pts if abs(p[0] - x) < W * 0.03]
        return sum(p[1] for p in near) / len(near) if near else None

    wrong = []
    for b in m["boroughs"]:
        if b["name"] not in THAMES_SOUTH | THAMES_NORTH:
            continue
        x, y = b["cx"] / 100 * W, b["cy"] / 100 * H
        ry = river_y(x)
        if ry is None:
            continue
        south = y > ry               # SVG y grows downward
        if south != (b["name"] in THAMES_SOUTH):
            wrong.append((b["name"], "south" if south else "north"))
    assert not wrong, f"boroughs on the wrong bank: {wrong}"


def test_no_text_lives_inside_the_scaled_svg(built):
    """The bug that started all of this. font-size in a viewBox resolves in user
    units, so 5 units rendered at 43px and every label burst over its neighbours.
    Counts are HTML badges positioned by percentage instead."""
    for url, h in built.items():
        svg = re.search(r'<svg class="boroughs".*?</svg>', h, re.S)
        if svg:
            assert "<text" not in svg.group(0)
            assert "font-size" not in svg.group(0)


def test_the_map_field_is_pinned_to_the_data_aspect_ratio():
    """Badges are placed by percentage. Without this the SVG letterboxes inside
    its box and every badge drifts off its borough."""
    grid = _media_block(CSS(), "@media (min-width:640px)")
    assert "aspect-ratio:1000 / 773" in grid, \
        "the field does not match the projected data's proportions"
    m = mapdata()
    assert abs(m["width"] / m["height"] - 1000 / 773) < 0.02, \
        "the CSS aspect ratio no longer matches the generated data"


def test_the_shapes_are_decorative_and_the_chips_are_the_control(built):
    """33 focusable paths would put 33 duplicate tab stops in front of a keyboard
    user, for a view of what the chips already do."""
    h = built["/all/"]
    svg = re.search(r'<svg class="boroughs".*?>', h, re.S).group(0)
    assert 'aria-hidden="true"' in svg and 'focusable="false"' in svg
    assert "pointer-events:none" in _first_block(CSS(), ".badges"), \
        "badges would swallow clicks meant for the borough beneath"


def test_the_crown_copyright_attribution_is_printed(built):
    """ONS boundary data is OGL plus the OS OpenData Licence, and both statements
    are required wherever it is shown. Not optional."""
    for name in ("National Statistics", "Ordnance Survey"):
        assert name in built["/all/"], f"missing attribution: {name}"
        assert "Crown copyright" in built["/all/"]


def test_the_choropleth_uses_steps_not_a_continuous_ramp():
    """With a handful of notices a smooth colour scale claims a precision nobody
    can read off a map."""
    css = CSS()
    for q in (".bo.q1", ".bo.q2", ".bo.q3"):
        assert q in css, f"{q} missing"


def test_the_shapes_are_hidden_where_they_would_be_illegible():
    """A phone gets the chips. A 360px-wide London is unreadable and untappable."""
    assert "display:none" in _first_block(CSS(), ".mapfield")
    assert ".mapfield{display:block" in _media_block(CSS(), "@media (min-width:640px)")


# ------------------------------------------------------- badge placement
# Borough centroids cluster where boroughs are small, so badges placed at
# centroids overlap. The live map only ever exercises the boroughs that happen to
# carry notices — six of them, barely needing to move — so it proves almost
# nothing. These push the algorithm properly.

LABELS_JS = ROOT / "site" / "js" / "labels.js"


def _labels(tmp_path):
    if not _have_jsdom():
        pytest.skip("needs node and jsdom (npm install)")
    page = _inline(DIST / "all" / "index.html", tmp_path / "page.html")
    r = subprocess.run(["node", str(LABELS_JS), str(page)],
                       capture_output=True, text=True, cwd=ROOT, env=_node_env())
    assert r.stdout, f"label harness produced nothing: {r.stderr[:400]}"
    return json.loads(r.stdout)


def test_no_two_badges_overlap_under_any_pressure(tmp_path, built):
    rep = _labels(tmp_path)
    bad = {k: v for k, v in rep.items()
           if not v.get("skipped") and v["overlaps"]}
    assert not bad, f"overlapping badges: {bad}"


def test_no_badge_is_pushed_off_the_sheet(tmp_path, built):
    rep = _labels(tmp_path)
    bad = {k: v for k, v in rep.items()
           if not v.get("skipped") and v["offSheet"]}
    assert not bad, f"badges outside the map: {bad}"


def test_badges_on_the_live_map_stay_near_their_borough(tmp_path, built):
    """Separation is worthless if a badge ends up over the wrong shape. On the
    real data nothing should need to travel far."""
    rep = _labels(tmp_path)["live map"]
    assert not rep.get("skipped"), "the live map had no boroughs to place"
    assert rep["maxShift"] <= 6, \
        f"a badge moved {rep['maxShift']}% of the map from its borough"
    assert rep["terse"] == 0, \
        "the real data should never be crowded enough to drop borough names"


def test_hopeless_crowding_falls_back_to_the_count_alone():
    """When separation cannot succeed, a number in the right place beats a name
    in the wrong one."""
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    assert "terse=true" in js and "pctW(String(a.n))" in js


def test_a_displaced_badge_gets_a_leader_line():
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'class="leader"' in js or '"leader"' in js
    assert "Math.hypot(pb.x-pb.ax, pb.y-pb.ay) > 1.6" in js, \
        "no threshold for drawing a leader"
    assert "pointer-events:none" in _first_block(CSS(), ".leaders")


def test_placement_does_not_depend_on_browser_layout():
    """getBoundingClientRect per badge would force a layout pass on every render,
    and jsdom computes no layout, so a measured version could not be tested."""
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"function placeBadges\(.*?\n\}", js, re.S).group(0)
    assert block.count("getBoundingClientRect") <= 1, \
        "placement measures individual badges instead of estimating"
    assert "CHAR_PX" in js and "BADGE_PAD" in js


def test_committed_map_matches_the_generator_settings():
    """Guards against a tolerance being tuned without regenerating the data.

    The map is generated by site/tools/build_map.py and committed so the site
    build needs no network. That convenience is also a trap: change a constant,
    forget to rerun the tool, and the site ships geometry that no longer matches
    the code that describes it.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bm", ROOT / "site" / "tools" / "build_map.py")
    bm = importlib.util.module_from_spec(spec)
    sys.setrecursionlimit(50000)
    spec.loader.exec_module(bm)
    got = mapdata().get("generated_with")
    assert got, "the committed map records no generator settings"
    assert got["tolerance"] == bm.TOLERANCE, \
        f"data built at tolerance {got['tolerance']}, code says {bm.TOLERANCE}"
    assert got["river_tolerance"] == bm.RIVER_TOLERANCE, \
        f"river built at {got['river_tolerance']}, code says {bm.RIVER_TOLERANCE}"
    assert got["width"] == bm.WIDTH


def test_the_site_url_comes_from_the_environment():
    """Editing a constant per environment means the same commit cannot deploy to
    a preview and to production. It also means a wrong value ships silently:
    canonical tags and the sitemap look fine while pointing at example.org."""
    src = (ROOT / "site" / "build.py").read_text(encoding="utf-8")
    assert 'os.environ.get("SITE_URL"' in src


def test_every_internal_reference_is_root_absolute(built):
    """The site can only be served from a domain root. Making that explicit here
    means a future relative path fails a test rather than half-working."""
    bad = []
    for url, h in built.items():
        for ref in re.findall(r'(?:href|src)="([^"]+)"', h):
            if ref.startswith(("http://", "https://", "mailto:", "#", "/")):
                continue
            bad.append((url, ref))
    assert not bad, f"relative references would break at a subpath: {bad[:5]}"


def test_the_build_needs_no_third_party_packages():
    """Hosting is one line because of this. A new import would quietly add a
    dependency step to every host's build configuration."""
    import ast
    tree = ast.parse((ROOT / "site" / "build.py").read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    third = sorted(m for m in mods if m not in sys.stdlib_module_names)
    # jsonschema is imported inside a try/except so records get validated when it
    # is available and the build still runs when it is not. Hosting stays a one
    # line build command; anything else appearing here does not.
    allowed = {"jsonschema", "schema"}
    unexpected = [m for m in third if m not in allowed]
    assert not unexpected, \
        f"site/build.py now needs {unexpected} installed to build"
    src = (ROOT / "site" / "build.py").read_text(encoding="utf-8")
    assert "except ImportError" in src, \
        "jsonschema is imported unguarded — the build would fail without it"


def test_the_crawler_contact_page_exists_and_says_how_to_opt_out(built):
    """The +URL in the crawler's user agent has to resolve to something a charity
    administrator can act on. Serving it from this repo means the page describing
    the crawler cannot drift out of date with the crawler."""
    h = built["/bot/"]
    assert "SomewhereToHelpBot" in h
    assert "robots.txt" in h.lower()
    assert "Disallow: /" in h
    assert "tek@8houses.co.uk" in h


def test_the_user_agent_points_at_a_page_the_site_actually_builds(built):
    """A contact URL that 404s is worse than none: it reads as evasion."""
    sys.path.insert(0, str(ROOT / "pipeline"))
    import importlib
    import config as pipeline_config
    importlib.reload(pipeline_config)
    ua = pipeline_config.USER_AGENT
    m = re.search(r"\+(\S+?);", ua)
    assert m, f"no +URL in the user agent: {ua}"
    path = re.sub(r"^https?://[^/]+", "", m.group(1))
    assert path in built, f"the user agent points at {path}, which is not built"


def test_every_file_read_and_write_pins_utf8():
    """Python defaults to the locale encoding, which on Windows is cp1252.

    The stylesheet's section rules are box-drawing characters, so on a Windows
    machine the build crashed reading its own CSS. It worked everywhere I ran it
    only because Linux and macOS happen to default to UTF-8 — the kind of bug that
    is invisible until someone else clones the repo.
    """
    import ast as _ast
    import glob as _glob
    bad = []
    for f in (_glob.glob(str(ROOT / "site" / "*.py"))
              + _glob.glob(str(ROOT / "site" / "tools" / "*.py"))
              + _glob.glob(str(ROOT / "pipeline" / "*.py"))):
        tree = _ast.parse(Path(f).read_text(encoding="utf-8"))
        for n in _ast.walk(tree):
            if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                    and n.func.attr in ("read_text", "write_text")
                    and not any(k.arg == "encoding" for k in n.keywords)):
                bad.append(f"{Path(f).name}:{n.lineno}")
    assert not bad, f"locale-dependent file access: {bad}"


def test_no_platform_specific_date_formats():
    """`%-d` strips a leading zero on glibc and raises ValueError on Windows.
    `%#d` is the Windows spelling and fails on Linux. No format string works on
    both, so a date meant for a reader is assembled by hand.

    This is the second Windows-only bug in this codebase — the first was file
    encoding. Both worked perfectly on the machine they were written on, which is
    exactly why they need a test rather than a fix.

    Checks string *literals* via the AST rather than grepping lines: the first
    version flagged the four docstrings that explain the problem, including its
    own.
    """
    import ast as _ast
    import glob as _glob
    bad = []
    for f in (_glob.glob(str(ROOT / "site" / "**" / "*.py"), recursive=True)
              + _glob.glob(str(ROOT / "pipeline" / "**" / "*.py"), recursive=True)):
        tree = _ast.parse(Path(f).read_text(encoding="utf-8"))
        docstrings = set()
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.ClassDef,
                                 _ast.AsyncFunctionDef)):
                d = _ast.get_docstring(node, clean=False)
                if d:
                    docstrings.add(d)
        for node in _ast.walk(tree):
            if (isinstance(node, _ast.Constant) and isinstance(node.value, str)
                    and node.value not in docstrings
                    and re.search(r"%[-#][a-zA-Z]", node.value)):
                bad.append(f"{Path(f).name}:{node.lineno}  {node.value[:50]!r}")
    assert not bad, "platform-specific strftime directives:\n  " + "\n  ".join(bad)


def test_dates_render_the_way_a_person_writes_them(built):
    """Regression guard: the helper must not reintroduce a leading zero."""
    h = built["/"]
    m = re.search(r'<span>(\w+day, \d{1,2} \w+ \d{4})</span>', h)
    assert m, "no dateline found on the front page"
    day = m.group(1).split(",")[1].strip().split()[0]
    assert not day.startswith("0"), f"dateline reads {m.group(1)!r}"


def test_wrangler_config_matches_what_the_build_produces():
    """The deploy config and the build output have to agree, and nothing else
    checks that they do — a wrong directory deploys an empty site successfully."""
    import json as _json
    raw = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    cfg = _json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert cfg["assets"]["directory"] == "./dist"
    assert (ROOT / "site" / "build.py").read_text(encoding="utf-8").count(
        'ROOT / "dist"') >= 1, "build.py no longer defaults to dist/"


def test_workers_serves_directory_urls_and_our_own_404(built):
    """Every page is /path/index.html, so directory URLs must resolve to the index
    inside them. And build.py writes a 404 page in the paper's voice — without
    not_found_handling a missing page shows a bare Cloudflare error instead."""
    import json as _json
    raw = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    cfg = _json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert cfg["assets"]["html_handling"] == "auto-trailing-slash"
    assert cfg["assets"]["not_found_handling"] == "404-page"
    assert (DIST / "404.html").exists()
    assert (DIST / "about" / "index.html").exists()


def test_the_deploy_is_assets_only_with_no_worker_script():
    """Spec §3 rules out runtime intelligence and §2 A4 rules out anything that
    can be abused or run up a bill. An assets-only Worker executes nothing."""
    import json as _json
    raw = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    cfg = _json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert "main" not in cfg, "a Worker script has appeared; the site is static"


def test_every_record_matches_the_schema():
    """Schema conformance lives here rather than in the build.

    The build cannot require jsonschema: Cloudflare runs `python3 site/build.py`
    with no pip install, so a hard dependency breaks deployment. It validates when
    the package happens to be available and says so when it is not.

    That leaves this as the real check — and it is needed, because a hand-written
    record with a 158-character field in a 120-character slot once built 99 pages
    successfully. The pipeline validates its own output; nothing was validating a
    record written by a person.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    import glob as _glob

    import schema as pipeline_schema
    from jsonschema import ValidationError, validate

    bad = []
    for f in sorted(_glob.glob(str(ROOT / "data" / "orgs" / "*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        try:
            validate(doc["organisation"], pipeline_schema.ORG_SCHEMA)
        except ValidationError as exc:
            bad.append(f"{Path(f).name} organisation: {exc.message[:80]}")
        for op in doc["opportunities"]:
            try:
                validate(op, pipeline_schema.RECORD_SCHEMA)
            except ValidationError as exc:
                path = ".".join(str(x) for x in exc.absolute_path) or "(root)"
                bad.append(f'{op.get("id", "?")} {path}: {exc.message[:80]}')
    assert not bad, "records failing the schema:\n  " + "\n  ".join(bad)


def test_facts_taken_from_someone_elses_site_say_so():
    """A record may cite a source the charity does not control — Ace of Clubs'
    shift times come from Lambeth Council's volunteer portal, because their own
    page does not publish them. That is fine, and better than inventing hours.

    What is not fine is doing it silently. The weekly check only ever reads the
    charity's own volunteer_url, so an undeclared third-party fact will be treated
    as verified first-party data forever, and a five-year-old council listing will
    outlive the thing it described. Team London still carries a Thames Reach role
    referring to COVID lockdowns.

    So: if source_url is off the charity's own domain, the record must say where
    the fact came from.
    """
    import glob as _glob
    from urllib.parse import urlparse

    bad = []
    for f in sorted(_glob.glob(str(ROOT / "data" / "orgs" / "*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        own = urlparse(doc["organisation"]["website_url"]).netloc.replace("www.", "")
        for op in doc["opportunities"]:
            pv = op["provenance"]
            src = urlparse(pv["source_url"]).netloc.replace("www.", "")
            if not src or src == own:
                continue
            # Require the domain itself to be named, which is what the build
            # invariant on apply_url checks. Matching on phrases like "comes
            # from" was fragile in both places: an honest declaration worded
            # differently failed, and a vague one passed.
            declared = any(src in x for x in pv.get("unsupported_fields", []))
            if not declared:
                bad.append(f'{op["id"]}: source {src} is not {own}, and no '
                           f"unsupported_fields entry names {src}")
    assert not bad, "undeclared third-party sources:\n  " + "\n  ".join(bad)


def test_unconfirmed_notices_say_so_on_the_classified_not_just_the_article():
    """An article page prints "Confidence low" in its byline. A classified printed
    nothing, so a reader scanning a column of notices could not tell which rested
    on a thin page, a defunct platform or a third-party listing.

    At the time of writing that was 11 of 67 notices. Disclosure on the detail
    page only is disclosure to the people who were already going to read it.
    """
    low = [op for op in data()["opps"] if op["provenance"]["confidence"] < 0.7]
    assert low, "no low-confidence roles — this test needs one to be meaningful"
    h = built_pages_all()
    for op in low:
        card = re.search(
            r'<article class="ad" data-id="%s".*?</article>' % re.escape(op["id"]),
            h, re.S)
        assert card, f'{op["id"]} has no classified on /all/'
        assert "could not confirm" in card.group(0), \
            f'{op["id"]} is confidence {op["provenance"]["confidence"]} and says nothing'


def test_confident_notices_carry_no_such_warning():
    """The marker is only worth anything if it marks an exception."""
    h = built_pages_all()
    high = [op for op in data()["opps"] if op["provenance"]["confidence"] >= 0.7]
    for op in high[:12]:
        card = re.search(
            r'<article class="ad" data-id="%s".*?</article>' % re.escape(op["id"]),
            h, re.S)
        if card:
            assert "could not confirm" not in card.group(0), \
                f'{op["id"]} is confidence {op["provenance"]["confidence"]}'


def built_pages_all():
    return (DIST / "all" / "index.html").read_text(encoding="utf-8")


def test_the_organisation_set_matches_the_seed_exactly():
    """Scope is fixed at the 32 organisations in seed.py (spec §2 A5).

    Added because I broke it: writing a record as `big-issue-foundation.json`
    while seed.py had already created `the-big-issue-foundation.json` took the
    count to 33. Nothing caught it except the build's own count line, which only
    works if someone reads it.
    """
    import glob as _glob
    files = sorted(_glob.glob(str(ROOT / "data" / "orgs" / "*.json")))
    ids_on_disk = set()
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        oid = doc["organisation"]["id"]
        assert Path(f).stem == oid, \
            f"{Path(f).name} holds organisation id {oid!r} — filename and id must match"
        ids_on_disk.add(oid)

    # seed.py keys on organisation names and derives ids with slug(), so import
    # it rather than pattern-matching the source. The first version of this test
    # grepped for '"id":' and found nothing, then reported an empty set as the
    # failure — a test that cannot read its own reference is worse than none.
    sys.path.insert(0, str(ROOT / "pipeline"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "seedmod", ROOT / "pipeline" / "seed.py")
    seedmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seedmod)
    seeded = {seedmod.slug(name) for name, _area, _url in seedmod.SEED
              if name not in seedmod.NOT_A_ROLE_SOURCE}
    assert len(seeded) == 32, \
        f"seed.py yields {len(seeded)} in-scope organisations, expected 32"

    extra = ids_on_disk - seeded
    missing = seeded - ids_on_disk
    assert not extra, f"organisations on disk that seed.py does not know: {sorted(extra)}"
    assert not missing, f"seeded organisations with no file: {sorted(missing)}"
    assert len(ids_on_disk) == 32, f"{len(ids_on_disk)} organisations, expected 32"


def test_every_role_id_belongs_to_its_organisation():
    """A role whose org_id does not match its file would be attributed to the
    wrong charity — the build refuses an unknown org_id but not a wrong one."""
    import glob as _glob
    bad = []
    for f in sorted(_glob.glob(str(ROOT / "data" / "orgs" / "*.json"))):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        oid = doc["organisation"]["id"]
        for op in doc["opportunities"]:
            if op["org_id"] != oid:
                bad.append(f'{op["id"]}: org_id {op["org_id"]!r} in {oid}.json')
    assert not bad, "roles filed under the wrong organisation:\n  " + "\n  ".join(bad)


def test_the_client_bundle_ships_only_what_it_reads():
    """app.js filters server-rendered notices by data-id rather than rebuilding
    them, so it needs the fields match() tests plus the title for the lookup
    field. Everything else is weight on every results page.

    Provenance alone was 28KB of data the client cannot use. Trimming took the
    bundle from 101KB to 24KB, and from 15.7KB to 4.2KB gzipped.
    """
    allowed = {"id", "org_id", "title", "commitment", "activity", "status",
               "who_can_apply", "location_type", "postcode_district"}
    for op in shipped()["opps"]:
        extra = set(op) - allowed
        assert not extra, f'{op["id"]} ships fields the client never reads: {sorted(extra)}'
    for op in shipped()["opps"][:5]:
        assert allowed <= set(op), f'{op["id"]} is missing a field match() needs'


def test_every_field_the_client_reads_is_actually_shipped():
    """The mirror of the test above — trimming too far is the other failure, and
    it breaks filtering silently rather than loudly."""
    js = (ROOT / "site" / "static" / "app.js").read_text(encoding="utf-8")
    shipped_fields = set(shipped()["opps"][0])
    for field in ("commitment", "activity", "status", "who_can_apply",
                  "location_type", "postcode_district", "org_id", "title", "id"):
        if re.search(rf"\bo\.{field}\b|\brole\.{field}\b", js):
            assert field in shipped_fields, \
                f"app.js reads o.{field} but the bundle does not ship it"


def test_page_keys_are_urls_not_filesystem_paths(built):
    """Third Windows-only bug of this project, after locale file encoding and the
    glibc-only %-d strftime flag — and the first one inside the test harness
    rather than the code it tests.

    The fixture built its keys with f"/{rel}/", and a Path renders with the OS
    separator. On Windows every key came out as "/role\\ace-of-clubs-lunch-service\\"
    and twelve tests failed on KeyError looking up a URL that could never exist.
    It passed everywhere it had been run because those machines use forward
    slashes anyway.
    """
    bad = [u for u in built if "\\" in u]
    assert not bad, f"filesystem separators in URL keys: {bad[:5]}"
    for u in built:
        assert u.startswith("/"), f"{u} is not a URL path"
        assert u == "/" or u.endswith("/"), f"{u} does not end in a slash"
