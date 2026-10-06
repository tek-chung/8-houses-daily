"""Guided discovery alongside the searchable directory. No accounts or backend."""
import json
import locations


def notice(b, op, orgs, fresh):
    """A beginner's decision card; secondary particulars expand on demand."""
    org = orgs[op['org_id']]
    stale = b.suppressed(op, fresh)
    title, description = b.e(op['title']), b.e(op['what_youd_do'])
    text = op['what_youd_do']
    lead = text if len(text) <= 140 else text[:137].rsplit(' ', 1)[0] + '…'
    where = ('Your own home' if op['location_type'] == 'own_home'
             else 'Remote' if op['location_type'] == 'remote'
             else ', '.join(b.boroughs_of(op, orgs)) or 'Location not stated')
    if op.get('postcode_district') and op['location_type'] not in ('remote', 'own_home'):
        district = op['postcode_district']
        where = district + (' · ' + where if where != district else '')
    basis = locations.location_basis(op, orgs)
    location_note = ('<p class="role-location-note">Charity coverage area; confirm the venue.</p>'
                     if basis == 'charity_coverage' else '')
    travel = ('<a class="role-travel" href="https://tfl.gov.uk/plan-a-journey/" target="_blank" rel="noopener">Check your journey with TfL &rarr;</a>'
              if op['location_type'] not in ('remote', 'own_home') else '')
    frequency = {'one_off': 'One-off', 'flexible': 'Flexible frequency',
                 'weekly': 'Weekly', 'fortnightly': 'Every fortnight',
                 'monthly': 'Monthly', 'long_term': 'Ongoing commitment',
                 'unknown': 'Frequency not stated'}[op['commitment']]
    if op.get('min_term_months'):
        frequency += f' · at least {op["min_term_months"]} months'
    timing = 'Confirm with charity' if stale else op.get('specific_times') or 'Times not stated'
    if op.get('typical_shift_hours'):
        frequency += f' · {op["typical_shift_hours"]:g}h per shift'
    requirements = list(op.get('eligibility') or [])
    if not stale and op['screening'].get('min_age'):
        requirements.append(f'Aged {op["screening"]["min_age"]} or over')
    eligibility = (f'<p class="role-eligibility"><b>Before you save:</b> {b.e(" · ".join(requirements))}</p>'
                   if requirements else '')
    screening = 'Screening needs a fresh check' if stale else b.DBS_LABEL[op['screening']['dbs']]
    details = '<p>' + description + '</p><dl><dt>Screening</dt><dd>' + b.e(screening) + '</dd>'
    if not stale:
        for key, label in [('induction', 'Training'), ('references', 'References'), ('interview', 'Interview')]:
            value = op['screening'].get(key)
            if value is not None:
                details += f'<dt>{label}</dt><dd>{b.e(str(value))}</dd>'
    if op.get('skills'):
        details += '<dt>Skills mentioned</dt><dd>' + b.e(', '.join(op['skills'])) + '</dd>'
    if not op.get('typical_shift_hours'):
        details += '<dt>Shift length</dt><dd>Not stated</dd>'
    details += '</dl>'
    checked = (org.get('check') or {}).get('last_success')
    source = 'Source check date not recorded'
    if checked:
        try:
            source = 'Recorded source check: ' + b.short_date(b.datetime.fromisoformat(checked.replace('Z', '+00:00')))
        except ValueError:
            pass
    state = 'Check current availability' if stale else b.STATUS_LABEL[op['status']]
    uncertain = '<p class="role-uncertainty">Some particulars could not be confirmed. Check the charity’s own page.</p>' if op['provenance']['confidence'] < .7 else ''
    images = {'cooking_serving': 'soup-kitchen', 'befriending': 'coffee-chat', 'mentoring': 'coffee-chat', 'hosting': 'hosting'}
    picture = (f'<div class="role-illustration" aria-hidden="true" style="background-image:url(/assets/videos/{images[op["activity"]]}.webp)"></div>'
               if op['activity'] in images else '')
    href = op.get('apply_url') or org['volunteer_url']
    return f'''<article class="ad role-notice" data-id="{b.e(op['id'])}">
<div class="role-topline">{b.e(org['name'])}</div>{picture}
<h3><a href="/role/{b.e(op['id'])}/">{title}</a></h3>
<p class="role-lead">{b.e(lead)}</p>
<dl class="role-facts"><dt>Where</dt><dd>{b.e(where)}</dd>
<dt>When</dt><dd>{b.e(timing)}</dd><dt>Commitment</dt><dd>{b.e(frequency)}</dd></dl>
{location_note}{travel}
{eligibility}<p class="role-recruitment">{b.e(state)}</p>{uncertain}
<details class="role-details"><summary>Requirements &amp; details</summary>{details}
<p class="role-source">{b.e(source)}. Confirm details before enquiring.</p></details>
<a class="apply" href="{b.e(href)}" target="_blank" rel="noopener nofollow">Enquire with the charity &rarr;</a>
</article>'''


def build(b, orgs, opps, fresh, total):
    roles, templates = [], []
    boroughs = {item['name'] for item in (b.map_data() or {}).get('boroughs', [])}
    # This journey is for an individual's first enquiry. Team-only opportunities
    # and roles recorded as closed remain available in the full directory.
    for op in opps:
        if op['who_can_apply'] == 'team_only' or op['status'] == 'closed':
            continue
        stale = b.suppressed(op, fresh)
        roles.append({
            'id': op['id'], 'title': op['title'], 'charity': orgs[op['org_id']]['name'],
            'activity': op['activity'],
            'summary': op['what_youd_do'],
            'commitment': op['commitment'], 'when': [] if stale else op['when'],
            'min_term_months': op.get('min_term_months'),
            'areas': [a for a in b.boroughs_of(op, orgs) if a in boroughs],
            'zones': locations.zones_for(op, orgs, b.DISTRICT_BOROUGH),
            'location_basis': locations.location_basis(op, orgs),
            'location_type': op['location_type'],
            'status': 'unknown' if stale else op['status'],
            'confidence': op['provenance']['confidence'],
        })
        templates.append(f'<template data-role="{b.e(op["id"])}">{notice(b, op, orgs, fresh)}</template>')

    payload = json.dumps(roles, separators=(',', ':')).replace('<', '\\u003c')
    body = f'''<main class="wrap discovery" id="main">
  <div class="discovery-heading">
    <p class="discovery-kicker">Volunteer in London</p>
    <h1>Find your way to help.</h1>
    <p>A role that fits your life. A first step that matters.</p>
    <div class="discovery-heading-actions"><a href="/all/">Browse all roles &rarr;</a></div>
  </div>
  <div class="discovery-bar">
    <span id="journey-progress">Start with a few examples</span>
    <div class="journey-tools"><button type="button" id="undo-action" disabled>Undo</button>
    <button type="button" id="show-shortlist">Saved roles <span id="saved-count">0</span></button></div>
  </div>
  <p id="journey-status" class="discovery-status" role="status" aria-live="polite"></p>
  <div id="discovery-stage"><h2>Explore a few roles</h2></div>
  <noscript><p>This guided journey needs JavaScript. You can still <a href="/all/">browse every role in the directory</a>.</p></noscript>
  <p class="discovery-footnote">No account needed. Saves stay on this device.
    Enquire directly with the charity. Saving does not contact them.</p>
  {f'<div class="notice"><b>Publication suspended</b>{b.e(fresh.get("site_banner_copy") or "")}</div>' if fresh.get('site_banner') else ''}
  <details class="discovery-about"><summary>About these notices</summary>
    {b.banner(dict(fresh, site_banner=False), len(orgs), total, wrap=False)}</details>
</main>
<div hidden id="discovery-templates">{''.join(templates)}</div>
<script type="application/json" id="discovery-data">{payload}</script>
<script type="application/json" id="discovery-locations">{json.dumps({'zones': locations.ZONES, 'borough_zones': locations.BOROUGH_ZONES})}</script>
<script src="/assets/discovery.js" defer></script>'''
    b.write('/find/', b.shell(title=f'Find a volunteering role — {b.SITE_NAME}',
            desc='A few questions to find a London homelessness volunteering role that fits your life.',
            path='/find/', body=body, search=False, needs_data=False, state={'discovery': 'true'},
            extra_head='<link rel="stylesheet" href="/assets/discovery.css">'))
    return ['/find/']
