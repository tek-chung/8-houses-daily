"""Validate and apply the 17 Oct role check to a COPY of data/orgs.

usage: python3 apply.py <repo_copy_root> <findings_dir> [--write]
Without --write nothing is saved; the report is still produced.
"""
import copy, glob, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]); FIND = Path(sys.argv[2]); WRITE = "--write" in sys.argv
sys.path.insert(0, str(ROOT / "pipeline"))
import jsonschema
from schema import RECORD_SCHEMA, ORG_SCHEMA, _OPPORTUNITY_CORE

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
CORE = list(_OPPORTUNITY_CORE.keys())
ORGS = ROOT / "data" / "orgs"

# judgement calls resolved conservatively (documented in the report)
KEEP_AS_UNKNOWN = {"housing-justice-winter-shelter", "wlm-services-volunteer"}
SKIP_UPDATE = {"the-big-issue-frontline-office"}
SKIP_NEW = {  # new roles not worth publishing: expired dated events / ended recruitment rounds
    "kingston-churches-action-on-homelessness-wrecking-crew",
}
issues, applied, notes = [], [], []
pending_links = []
staged = {}
LOGOS = set(re.findall(r'^\s*"([a-z0-9-]+)":\s*"[^"]+\.(?:png|svg|webp|ico|jpg)"', (ROOT/"site"/"build.py").read_text(encoding="utf-8"), re.M))
sys.path.insert(0, str(ROOT / "site"))
from locations import BOROUGH_ZONES
BOROUGHS = {" ".join(b.casefold().split()) for b in BOROUGH_ZONES} | {"richmond", "kingston", "city of westminster", "hammersmith", "kensington", "barking"}
LONDON_WORDS = {"london", "greater london", "across london", "london wide", "london-wide", "all of london", "all london"}
LOCALITIES = {"west norwood", "wallington", "lower addiscombe road", "purley", "plumstead", "clapham", "east sheen",
              "streatham", "camberwell", "king's cross", "lambeth outreach", "south london", "deptford", "poplar",
              "brixton", "peckham", "crouch end", "turnham green", "caterham-on-the-hill", "caterh-on-the hill",
              "canning town warehouse/office", "canning town", "shoreditch", "stratford", "tottenham", "walthamstow", "wimbledon", "surbiton"}

def words(s): return re.findall(r"[a-z0-9']+", s.lower())

def run8(a, quotes):
    wa = words(a)
    grams = {tuple(wa[i:i+8]) for i in range(len(wa) - 7)}
    for q in quotes:
        wq = words(q)
        for i in range(len(wq) - 7):
            if tuple(wq[i:i+8]) in grams: return True
    return False

def get(r, path):
    cur = r
    for p in path.split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
    return cur

def put(r, path, v):
    parts = path.split("."); cur = r
    for p in parts[:-1]: cur = cur[p]
    cur[parts[-1]] = v

def asserted(r, path):
    v = get(r, path)
    if path == "screening.dbs": return v not in (None, "unknown")
    if path == "status": return v in ("open", "closed", "seasonal_closed", "oversubscribed")
    if path == "who_can_apply": return v in ("team_only", "either")
    if path == "eligibility": return bool(v)
    if path == "seasonal_window": return v is not None
    if path == "commitment": return v not in (None, "unknown")
    return v is not None

def forced(path):
    return "unknown" if path in ("screening.dbs", "status", "commitment") else ([] if path == "eligibility" else ("individual" if path == "who_can_apply" else None))

CRIT = ["status", "screening.dbs", "screening.references", "screening.interview", "screening.min_age",
        "next_intake", "specific_times", "commitment", "seasonal_window", "eligibility", "who_can_apply"]

def quote_ok(path, r, ev):
    if not isinstance(ev, dict): return False
    q, u = (ev.get("quote") or "").strip(), (ev.get("url") or "")
    if not q or len(q) > 240 or not u.startswith("http"): return False
    ql = q.lower(); v = get(r, path)
    if path == "screening.min_age": return str(v) in q
    if path == "screening.dbs":
        if v == "none": return bool(re.search(r"\bno\b|none|not (need|require)|without", ql))
        if v == "basic": return "basic" in ql or "dbs" in ql or "criminal" in ql or "disclosure" in ql
        if v == "enhanced": return "enhanced" in ql
        return bool(re.search(r"dbs|disclosure|criminal|police|background|checks?", ql))
    if path == "screening.references": return "refere" in ql
    return True

def build_prov(org, r, ev, cleared, existing_prov=None):
    verified = [p for p in CRIT if p in ev and asserted(r, p)]
    checked = len([p for p in CRIT if asserted(r, p)]) + len(cleared)
    conf = round(len(verified) / checked, 2) if checked else 0.7
    unsupported = list(cleared)
    for p in ("screening.dbs", "screening.min_age", "specific_times", "commitment", "status"):
        if not asserted(r, p) and p not in unsupported: unsupported.append(p)
    src = (ev.get("status") or {}).get("url") or r.get("apply_url") or next((e["url"] for e in ev.values() if isinstance(e, dict) and e.get("url")), "")
    on_board = bool(org.get("board"))
    return {"extracted_at": NOW, "method": "platform" if on_board else "llm", "reviewed_by_human": False,
            "confidence": conf, "source_url": src, "verified_fields": verified, "unsupported_fields": unsupported}

def core_of(r): return {k: r.get(k) for k in CORE if k != "stated_places"} | {"stated_places": r.get("stated_places", [])}

# Corrections from the independent browser spot-check (verify1/verify2.json)
OVERRIDES = {
    "the-upper-room-meals-volunteer": {"screening.dbs": "unknown", "screening.references": None},   # quote not on page
    "the-big-issue-frontline-office": {"status": "unknown"},                           # generic intro only
    "handson-london-community-day": {"status": "unknown"},                                        # two readings conflict
    "solace-womens-aid-next-steps-peer-mentor": {"screening.min_age": None},                       # org-wide FAQ
    "housing-justice-citadel": {"screening.min_age": None},                                       # belongs to one area listing
    "single-homeless-project-wellbeing-and-employment-programme-volunteer": {"status": "unknown"},                         # standing invitation
}
for _rid in ("emmaus-slc-kitchen-volunteer", "emmaus-slc-van-driver-crew", "emmaus-slc-retail-assistant"):
    OVERRIDES[_rid] = {"screening.min_age": None}                                                  # form dropdown label only

def process_role(org, oid, raw, existing):
    r = copy.deepcopy(raw); ev = r.pop("evidence", {}) or {}
    for _p, _v in OVERRIDES.get(r["id"], {}).items():
        if get(r, _p) != _v: notes.append(f"{r['id']}: override {_p}: {get(r,_p)!r} -> {_v!r}")
        put(r, _p, _v)
        if _p in ev: del ev[_p]
    if oid == "the-whitechapel-mission" and (r.get("screening") or {}).get("min_age") == 21:
        r["screening"]["min_age"] = None; ev.pop("screening.min_age", None)
        r["eligibility"] = (r.get("eligibility") or []) + ["Over 21, as the page words it"]
        notes.append(f"{r['id']}: min_age 21 -> null, 'over 21' kept as eligibility wording")
    r.pop("match", None); r.pop("changes_vs_current", None)
    r.setdefault("stated_places", [])
    sk = []
    for s in r.get("skills") or []:
        if len(s) > 40:
            s = s[:40].rsplit(" ", 1)[0]
            notes.append(f"{r['id']}: skill shortened to {s!r}")
        sk.append(s)
    r["skills"] = sk[:6]
    cleared = []
    for p in CRIT:
        if not asserted(r, p): continue
        if quote_ok(p, r, ev.get(p)): continue
        # no valid quote: keep only if unchanged from the published value
        if existing is not None and get(existing, p) == get(r, p):
            notes.append(f"{r['id']}: {p} kept (unchanged, no fresh quote)"); continue
        issues.append(f"{r['id']}: {p}={get(r,p)!r} had no usable quote -> forced {forced(p)!r}")
        put(r, p, forced(p)); cleared.append(p)
    quotes = [e["quote"] for e in ev.values() if isinstance(e, dict) and e.get("quote")]
    if run8(r["what_youd_do"], quotes):
        if existing is not None:
            issues.append(f"{r['id']}: what_youd_do shares 8 words with a quote -> kept existing text")
            r["what_youd_do"] = existing["what_youd_do"]
        else:
            issues.append(f"{r['id']}: what_youd_do shares 8 words with a quote -> REJECTED new role")
            return None, ev, cleared
    return r, ev, cleared

def main():
    files = sorted(glob.glob(str(FIND / "[A-I].json")))
    findings = {}
    for f in files:
        for o in json.load(open(f, encoding="utf-8"))["orgs"]:
            if o["org_id"] in findings:
                # I.json (direct read) supersedes H.json for KCAH, where the agent was blocked
                if f.endswith("I.json"):
                    notes.append(f"{o['org_id']}: findings from I.json supersede H.json")
                else:
                    continue
            findings[o["org_id"]] = o
    report = {"orgs": {}}
    all_ids = set()
    for p in sorted(ORGS.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8")); org = d["organisation"]; oid = org["id"]
        fnd = findings.get(oid)
        if not fnd:
            issues.append(f"{oid}: no findings"); all_ids |= {x['id'] for x in d['opportunities']}; continue
        existing = {x["id"]: x for x in d["opportunities"]}
        out, stat = [], {"unchanged": 0, "updated": 0, "new": 0, "retired": 0, "kept_unknown": 0, "skipped": 0}
        seen = set()
        if fnd["read_status"] in ("read_failed", "suspicious_page"):
            out = list(d["opportunities"]); seen = set(existing)
        for raw in fnd["roles"]:
            rid = raw["id"]
            if rid in SKIP_NEW and rid not in existing:
                stat["skipped"] += 1; continue
            ex = existing.get(rid)
            if rid in SKIP_UPDATE and ex is not None:
                seen.add(rid); out.append(ex); stat["unchanged"] += 1
                notes.append(f"{rid}: left as published (its volunteering page is on bigissue.com, the charity site on bigissue.org.uk; an unreviewed change would fail the build's domain rule)")
                continue
            if raw.get("match") == "existing" and ex is None: issues.append(f"{rid}: claimed existing but not found; treating as new")
            r, ev, cleared = process_role(org, oid, raw, ex)
            if r is None: stat["skipped"] += 1; continue
            seen.add(rid); r["org_id"] = oid
            if ex is not None:
                new = copy.deepcopy(ex)
                for k in CORE:
                    if k in r: new[k] = r[k]
                if "stated_places" not in r: new.setdefault("stated_places", [])
                if core_of(new) == core_of(ex) and not cleared:
                    out.append(ex); stat["unchanged"] += 1; continue
                new["provenance"] = build_prov(org, new, ev, cleared)
                out.append(new); stat["updated"] += 1
            else:
                r["coords"] = None
                r["provenance"] = build_prov(org, r, ev, cleared)
                out.append(r); stat["new"] += 1
        # retire
        for rt in fnd.get("retire", []):
            rid = rt["id"]
            if rid not in existing: issues.append(f"{oid}: retire id {rid} not found"); continue
            seen.add(rid)
            e = rt.get("evidence") or {}
            if rid in KEEP_AS_UNKNOWN or not e.get("quote"):
                x = copy.deepcopy(existing[rid]); x["status"] = "unknown"
                x["provenance"] = {**x["provenance"], "extracted_at": NOW, "reviewed_by_human": False,
                                   "unsupported_fields": sorted(set(x["provenance"].get("unsupported_fields", [])) | {"status"})}
                out.append(x); stat["kept_unknown"] += 1
                notes.append(f"{rid}: not found on live pages; kept with status unknown ({rt.get('reason','')[:120]})")
            else:
                stat["retired"] += 1; notes.append(f"{rid}: RETIRED ({rt.get('reason','')[:140]})")
        # roles the agent did not mention at all: keep untouched, report
        for rid, ex in existing.items():
            if rid not in seen and fnd["read_status"] not in ("read_failed", "suspicious_page"):
                out.append(ex); issues.append(f"{oid}: existing role {rid} not mentioned by the check; kept untouched")
        # org fields
        of = fnd.get("org_fields") or {}
        for k in ("summary", "boroughs", "charity_number"):
            if k in of and of[k] not in (None, "", []) and of[k] != org.get(k):
                notes.append(f"{oid}: {k}: {org.get(k)!r} -> {of[k]!r}"); org[k] = of[k]
        if oid == "centrepoint" and fnd.get("volunteer_url_suggestion"):
            u = fnd["volunteer_url_suggestion"].split(" ")[0]
            notes.append(f"{oid}: volunteer_url -> {u}"); org["volunteer_url"] = u
        elif fnd.get("volunteer_url_suggestion"):
            notes.append(f"{oid}: SUGGESTED volunteer_url (not applied): {fnd['volunteer_url_suggestion'][:160]}")
        if fnd["read_status"] == "ok":
            org["check"]["last_attempt"] = NOW; org["check"]["last_success"] = NOW
        # --- site constraints ---------------------------------------------------
        import urllib.parse as _u
        od = _u.urlparse(org["website_url"]).netloc.replace("www.", "")
        for r in out:
            if r["provenance"]["reviewed_by_human"] and r is existing.get(r["id"]): continue
            changed_rec = r is not existing.get(r["id"])
            if not changed_rec: continue
            # 1. places: the site only reads boroughs / "London" as London
            sp = r.get("stated_places") or []
            if sp:
                keep, dropped, has_local = [], [], False
                for pl in sp:
                    n = " ".join(pl.casefold().replace("’", "'").split())
                    if n in BOROUGHS or n in LONDON_WORDS: keep.append(pl)
                    elif "london" in n: keep.append("London"); dropped.append(pl)
                    elif n in LOCALITIES: has_local = True; dropped.append(pl)
                    else: keep.append(pl)
                if has_local: keep = [k for k in keep if k.casefold() in BOROUGHS or k.casefold() in LONDON_WORDS]
                keep = list(dict.fromkeys(keep))
                if keep != sp:
                    notes.append(f"{r['id']}: stated_places {sp} -> {keep} (site reads only boroughs or 'London' as London)")
                    r["stated_places"] = keep
            # 2. foreign-host apply_url on an unreviewed record is refused by the build
            ad = _u.urlparse(r.get("apply_url") or "").netloc.replace("www.", "")
            role_link = r.get("apply_url")
            if ad and od and not (ad == od or ad.endswith("." + od)):
                pending_links.append({"id": r["id"], "role_link": r["apply_url"], "charity": oid})
                r["apply_url"] = org["volunteer_url"]; r["url_specificity"] = "org_volunteer_page"
            # 3. source_url must be a printable page (not a feed with a query string);
            #    a source off the charity's own host must be named in unsupported_fields
            pv = r["provenance"]
            src = pv.get("source_url") or ""
            if "?" in src or "/api/" in src or not src:
                src = role_link if role_link and "?" not in role_link else org["volunteer_url"]
                pv["source_url"] = src
            sh = _u.urlparse(src).netloc.replace("www.", "")
            if sh and od and sh != od and not any(sh in x for x in pv["unsupported_fields"]):
                pv["unsupported_fields"] = list(pv["unsupported_fields"]) + [f"{sh}: facts read from the charity's volunteering platform"]
        if oid not in LOGOS and any(r is not existing.get(r["id"]) for r in out):
            staged[oid] = out
            notes.append(f"{oid}: {len(out)} roles STAGED, not written to data/orgs — no logo in site/static/logos (the build's tests require one per charity with roles)")
            out = list(d["opportunities"])
        d["opportunities"] = out
        # schema
        try: jsonschema.validate(org, ORG_SCHEMA)
        except Exception as e: issues.append(f"{oid}: ORG SCHEMA {str(e).splitlines()[0]}")
        for r in out:
            if r["id"] in all_ids: issues.append(f"DUPLICATE ID {r['id']}")
            all_ids.add(r["id"])
            try: jsonschema.validate(r, RECORD_SCHEMA)
            except Exception as e: issues.append(f"{r['id']}: RECORD SCHEMA {str(e).splitlines()[0][:200]}")
        report["orgs"][oid] = {**stat, "read_status": fnd["read_status"], "org_notes": fnd.get("org_notes", "")}
        if WRITE: p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["issues"] = issues; report["notes"] = notes; report["role_links_pending_review"] = pending_links; report["staged_orgs"] = sorted(staged)
    (FIND / "staged-new-charities.json").write_text(json.dumps(staged, indent=1, ensure_ascii=False), encoding="utf-8")
    (FIND / "validation-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    tot = {k: sum(o[k] for o in report["orgs"].values()) for k in ("unchanged", "updated", "new", "retired", "kept_unknown", "skipped")}
    print(tot, "issues:", len(issues), "notes:", len(notes))
    for i in issues: print(" ISSUE", i)

main()
