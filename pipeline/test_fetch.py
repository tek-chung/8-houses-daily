"""Tests for content isolation. Run: python -m pytest pipeline/test_fetch.py -q

These exist because of a specific failure found during Phase 0 reconnaissance: a
charity CMS page whose "Latest" and "Most read" sidebar rotates weekly would change
its content hash every run, so all 34 pages would look changed every week, and the
review queue would be permanently full.

The load-bearing test is test_hash_stable_when_only_sidebar_changes.
"""
import hashlib

import pytest

from fetchpage import (find_role_links, full_text, looks_client_rendered,
                       main_content)

ROLE_BODY = """
<h1>Winter Night Shelter volunteers</h1>
<p><strong>Our night shelters are currently closed.</strong></p>
<h2>Why we need you</h2>
<p>Volunteers help set up the venue, prepare and serve food and drinks, and welcome
guests. They are a key part of creating a warm atmosphere that guests tell us makes
them feel valued and respected as people.</p>
<h2>When and where?</h2>
<p>We have 21 venues across south and south west London, each with a team
responsible for the same weekly evening from early November until April. Volunteers
help from around 6pm to 9pm each week through the winter season.</p>
<h2>What experience do I need?</h2>
<p>No specific experience is needed, though having worked with vulnerable people
before is beneficial and cooking for large numbers helps.</p>
"""


def page(sidebar_items, body=ROLE_BODY):
    """A page shaped like the real charity CMSes: tiny body, enormous chrome.

    Chrome volume here is calibrated against a real measurement — Glass Door's
    volunteer page was roughly 95% boilerplate. A fixture with token chrome would
    make test_most_of_the_page_is_stripped pass without proving anything.
    """
    sidebar = "".join(
        f"<li><a href='/news/{i}'>{i}</a>"
        f"<p>Our latest report reflects on a year of insights, expertise and key "
        f"milestones, highlighting the services and spaces we provide and the "
        f"difference supporters like you make possible across London.</p></li>"
        for i in sidebar_items)
    langs = "".join(f"<a href='#'>{l}</a>" for l in
                    ["English", "Arabic", "Bulgarian", "Chinese", "Croatian",
                     "Czech", "Danish", "Dutch", "Finnish", "French", "German",
                     "Greek", "Hindi", "Italian", "Japanese", "Polish",
                     "Portuguese", "Romanian", "Russian", "Spanish", "Swedish",
                     "Hebrew", "Indonesian", "Latvian", "Serbian", "Slovak",
                     "Ukrainian", "Albanian", "Turkish", "Armenian", "Urdu"])
    tags = "".join(f"<a href='/tag/{t}'>{t}</a>" for t in
                   ["challenge events", "community fundraising", "Fundraiser",
                    "Fundraising activity", "going green", "London to Brighton",
                    "Royal Parks Half Marathon", "shelter", "Sleep Out", "stats",
                    "vitality 10k", "Windsor and Eton half"])
    return f"""<!doctype html><html><head><title>Volunteer</title></head><body>
      <div class="gtranslate">{langs}</div>
      <header><a href="/login">Log in</a><a href="/checkout">Basket: (0 items)</a>
        <a href="/get-help">GET HELP</a><a href="/donate">DONATE</a></header>
      <nav class="main-nav">
        <a href="/homelessness-information">Homelessness Information</a>
        <a href="/guest-stories">Guest stories</a>
        <a href="/donate">Donate</a><a href="/things-we-need">Things we need</a>
        <a href="/gifts-in-wills">Gifts in wills</a>
        <a href="/trusts-and-foundations">Trusts and foundations</a>
        <a href="/sleep-out">Sleep Out</a>
        <a href="/2027-london-marathon">2027 London Marathon</a>
        <a href="/challenge-events">Challenge Events</a>
        <a href="/corporate-support">Corporate support</a>
        <a href="/our-impact">Our impact</a><a href="/team">Meet our team</a>
        <a href="/jobs">Jobs at the charity</a><a href="/blog">Blog</a>
      </nav>
      <main>{body}
        <p><a href="/forms/express-interest">Apply to volunteer</a></p>
      </main>
      <aside class="latest"><h2>Latest</h2><ul>{sidebar}</ul></aside>
      <aside class="most-read"><h2>Most read</h2><ul>{sidebar}</ul></aside>
      <div class="tag-cloud">{tags}</div>
      <div class="newsletter"><h2>Sign up to receive our e-newsletter</h2>
        <p>For more information on how your data is stored and used, please see
        our privacy policy.</p></div>
      <footer><a href="/privacy">Privacy policy</a><a href="/cookies">Cookies</a>
        <a href="/sitemap">Sitemap</a><a href="/complaints">Complaints</a>
        <p>Registered Charity No. 1083203 (England and Wales)</p></footer>
      </body></html>"""


def digest(html):
    return hashlib.sha256(main_content(html).encode()).hexdigest()


# ------------------------------------------------------------------ the key test

def test_hash_stable_when_only_sidebar_changes():
    """The whole cost model of the pipeline depends on this being true.

    Two fetches a week apart. Role content identical, news sidebar rotated. The
    hash must not move, or every page looks changed every week.
    """
    week1 = page(["womens-report", "impact-report", "marathon"])
    week2 = page(["new-shelter-opens", "christmas-appeal", "trustee-recruitment"])
    assert digest(week1) == digest(week2)


def test_hash_moves_when_role_content_changes():
    """The converse: a real change must still be detected."""
    before = page(["a", "b"], ROLE_BODY)
    after = page(["a", "b"], ROLE_BODY.replace("6pm to 9pm", "5pm to 8pm"))
    assert digest(before) != digest(after)


def test_hash_moves_when_a_role_closes():
    before = page(["a", "b"], ROLE_BODY)
    after = page(["a", "b"], ROLE_BODY.replace(
        "currently closed", "now recruiting for the coming winter"))
    assert digest(before) != digest(after)


# ------------------------------------------------------------------ boilerplate

def test_most_of_the_page_is_stripped():
    html = page(["a", "b", "c", "d", "e"])
    ratio = 1 - len(main_content(html)) / len(full_text(html))
    assert ratio > 0.80, f"only stripped {ratio:.0%} — chrome is getting through"


def test_navigation_bait_is_not_in_the_extraction_payload():
    """These sit in the nav of real charity sites and are not volunteering roles.

    If they reach the model, it can invent roles from them.
    """
    got = main_content(page(["a", "b"])).lower()
    for bait in ["sleep out", "london marathon", "challenge events",
                 "basket", "privacy policy", "sitemap", "jobs at the charity"]:
        assert bait not in got, f"{bait!r} survived stripping"


def test_role_content_survives():
    got = main_content(page(["a", "b"]))
    for keep in ["Winter Night Shelter", "currently closed", "6pm to 9pm",
                 "21 venues", "November until April"]:
        assert keep in got, f"{keep!r} was stripped — that's real role detail"


def test_client_rendered_page_yields_almost_nothing():
    """An empty React shell must be reported, not extracted from."""
    shell = ('<!doctype html><html><body><div id="root"></div>'
             '<script src="/app.js"></script></body></html>')
    assert len(main_content(shell)) < 400


# ------------------------------------------------------------------ role links

def test_role_links_found_and_junk_excluded():
    html = """<html><body><main>
      <a href="/winter-night-shelter-volunteers">Winter Night Shelter volunteers</a>
      <a href="/lived-experience-group">Lived Experience Group</a>
      <a href="/befriending">Become a befriender</a>
      <a href="/donate">Donate now</a>
      <a href="/2027-london-marathon">2027 London Marathon</a>
      <a href="/sleep-out">Sleep Out 2026</a>
      <a href="/jobs">Jobs</a>
      <a href="/privacy">Privacy policy</a>
      <a href="https://facebook.com/x">Volunteer on Facebook</a>
      </main></body></html>"""
    links = find_role_links(html, "https://example.org/volunteer")
    paths = [l.replace("https://example.org", "") for l in links]
    assert "/winter-night-shelter-volunteers" in paths
    assert "/lived-experience-group" in paths
    assert "/befriending" in paths
    for junk in ["/donate", "/2027-london-marathon", "/sleep-out", "/jobs",
                 "/privacy"]:
        assert junk not in paths, f"{junk} should have been excluded"
    assert not any("facebook.com" in l for l in links), "left the site"


def test_role_links_capped():
    from config import MAX_ROLE_SUBPAGES
    many = "".join(
        f'<a href="/volunteer-role-{i}">Volunteer role {i}</a>' for i in range(30))
    links = find_role_links(f"<html><body><main>{many}</main></body></html>",
                            "https://example.org/v")
    assert len(links) <= MAX_ROLE_SUBPAGES


def test_nav_links_are_not_followed_as_roles():
    """Role discovery must ignore the site-wide nav, or every page follows itself."""
    html = """<html><body>
      <nav><a href="/volunteer-with-us">Volunteer</a>
           <a href="/mentoring">Mentoring</a></nav>
      <main><a href="/kitchen-volunteer">Kitchen volunteer</a></main>
      </body></html>"""
    paths = [l.replace("https://example.org", "")
             for l in find_role_links(html, "https://example.org/v")]
    assert paths == ["/kitchen-volunteer"]


# ------------------------------------------------- thin vs client-rendered

def test_react_shell_is_client_rendered():
    html = ('<!doctype html><html><body><div id="root"></div>'
            '<script src="/app.js"></script></body></html>')
    assert looks_client_rendered(html)


def test_next_and_vue_markers_detected():
    for html in ['<html><body><div id="__next"></div><script src=a.js></script></body></html>',
                 '<html><body><div data-server-rendered="true"></div><script src=a.js></script></body></html>',
                 '<html><body><div id="app"></div><script>window.__INITIAL_STATE__={}</script></body></html>']:
        assert looks_client_rendered(html), html[:60]


def test_genuinely_thin_page_is_not_called_client_rendered():
    """A real two-sentence "get in touch" page. Calling this client-rendered would
    send the maintainer chasing a headless browser for no reason."""
    html = ("<html><body><main><h1>Volunteer</h1><p>We would love to hear from you. "
            "Please get in touch using the contact form and we will reply as soon "
            "as we can about helping out.</p></main>"
            "<script src='/analytics.js'></script></body></html>")
    assert not looks_client_rendered(html)


def test_full_content_page_is_not_client_rendered():
    assert not looks_client_rendered(page(["a", "b"]))
