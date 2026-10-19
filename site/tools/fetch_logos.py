"""Download official charity logos listed in site/logo-sources.json.

Run from the repo root:

    py site\tools\fetch_logos.py              # status "use" -> site/static/logos/official/<id>.<ext>
    py site\tools\fetch_logos.py --review     # status "review" -> site/static/logos/candidates/<id>.<ext>
    py site\tools\fetch_logos.py --only crisis shelter

Pure standard library. Files are saved exactly as supplied (no conversion,
recolouring or resizing). Anything that is not a real image is rejected, so an
HTML error page can never be saved as a logo. The build prefers
logos/official/<id>.* over the older files in logos/, so promoting a candidate
is just: move it from candidates/ to official/.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
SOURCES = SITE / "logo-sources.json"
LOGOS = SITE / "static" / "logos"
UA = ("Mozilla/5.0 (compatible; 8HousesDailyLogoFetch/1.0; "
      "+mailto:tek@8houses.co.uk) identifying charity marks for volunteering notices")


def sniff(data):
    """Return a file extension if the bytes are a real image, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:2000].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in data[:4000].lower():
        return "svg"
    return None


def fetch(url, referer=""):
    """Try a few times; the second and third attempts look like a browser, since
    some sites refuse unknown agents (HTTP 403) or are just slow."""
    browser_ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    last = None
    for attempt in range(3):
        headers = {"User-Agent": UA if attempt == 0 else browser_ua,
                   "Accept": "image/*,*/*;q=0.5"}
        if attempt and referer:
            headers["Referer"] = referer
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read(15_000_000)
        except (urllib.error.URLError, OSError) as err:
            last = err
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="fetch 'review' entries into logos/candidates/")
    ap.add_argument("--only", nargs="*", help="limit to these ids")
    args = ap.parse_args()

    wanted = "review" if args.review else "use"
    dest = LOGOS / ("candidates" if args.review else "official")
    dest.mkdir(parents=True, exist_ok=True)

    entries = json.loads(SOURCES.read_text(encoding="utf-8"))["logos"]
    ok, failed = [], []
    for e in entries:
        if args.only and e["id"] not in args.only:
            continue
        if e["status"] != wanted or not e["logo_url"]:
            continue
        url = e["logo_url"]
        try:
            data = fetch(urllib.parse.quote(url, safe=":/?&=%+#@~"), e.get("source_page", ""))
            ext = sniff(data)
            if not ext:
                raise ValueError("response is not an image")
            for old in dest.glob(e["id"] + ".*"):
                old.unlink()
            (dest / f"{e['id']}.{ext}").write_bytes(data)
            ok.append((e["id"], ext, len(data)))
            print(f"ok    {e['id']:42} {ext:5} {len(data)//1024:>6} KB")
        except (urllib.error.URLError, ValueError, OSError) as err:
            failed.append((e["id"], str(err)))
            print(f"FAIL  {e['id']:42} {err}")

    print(f"\n{len(ok)} saved to {dest}, {len(failed)} failed.")
    if failed:
        print("Failed ids:", ", ".join(i for i, _ in failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
