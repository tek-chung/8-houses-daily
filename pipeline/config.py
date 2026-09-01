"""Pipeline configuration. Spec §11.

Every threshold that affects whether a claim reaches a visitor lives here, in one
place, so it can be audited without reading the pipeline.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ORGS_DIR = DATA / "orgs"
STATE = Path(__file__).resolve().parent / "state"
HTTP_CACHE = STATE / "http_cache.json"
FRESHNESS_OUT = DATA / "freshness.json"

# ---------------------------------------------------------------- politeness
# The +URL must resolve to a page a charity's administrator can act on. It points
# at the paper's own /bot/ page, which is built from this same repository — so the
# page describing the crawler cannot drift out of date with the crawler.
BOT_PAGE = os.environ.get("SITE_URL", "https://daily.8houses.co.uk").rstrip("/") + "/bot/"
USER_AGENT = (
    f"SomewhereToHelpBot/1.0 "
    f"(+{BOT_PAGE}; contact tek@8houses.co.uk; "
    f"weekly freshness check for a London volunteering signpost)"
)
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20
MAX_PAGE_CHARS = 60_000          # truncate before sending to the model

# Phase 0 reconnaissance findings (see docs/scrapability.md).
# Charity CMS pages are typically 90%+ navigation, tag clouds and rotating news
# sidebars. Those sidebars change weekly regardless of role content, so hashing a
# whole page makes every page look changed every run. We isolate main content
# before hashing, and follow role links one level down because most landing pages
# carry no role detail themselves.
MIN_MAIN_CONTENT_CHARS = 400     # below this, treat the page as client-rendered
MAX_ROLE_SUBPAGES = 6            # role links followed per organisation

# ---------------------------------------------------------------- model
MODEL_PRIMARY = "claude-haiku-4-5-20251001"
MODEL_ESCALATE = "claude-sonnet-5"   # used only when primary output fails validation
MAX_TOKENS = 4000

# ---------------------------------------------------------------- the gate
# Fields where being wrong wastes someone's day or misstates a safeguarding
# requirement. A change to any of these NEVER auto-publishes. Spec §10.2, §11.3.
CRITICAL_FIELDS = frozenset({
    "screening.dbs",
    "screening.references",
    "screening.interview",
    "screening.min_age",
    "screening.induction",
    "status",
    "next_intake",
})

# Confidence below this routes to human review even for non-critical fields.
CONFIDENCE_THRESHOLD = 0.85

# Two consecutive fetch failures marks a link dead.
DEAD_LINK_AFTER_FAILURES = 2

# ---------------------------------------------------------------- decay §11.5
SUPPRESS_ASSERTIVE_AFTER_DAYS = 21
SITE_BANNER_AFTER_DAYS = 60

# ---------------------------------------------------------------- copyright
# Any verbatim run of this many words shared with the source page is treated as
# reproduction rather than paraphrase. Deliberately stricter than the 15-word
# quote ceiling, because we are not quoting at all — we are restating.
MAX_VERBATIM_SHINGLE = 8

ROUTE_AUTO = "auto"
ROUTE_REVIEW = "review"
