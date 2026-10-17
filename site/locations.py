"""Broad browsing areas, not fare zones or calculated journey times.

Postcode districts take precedence over organisation-wide coverage. Central is
deliberately approximate: EC/WC, W1, SW1 and SE1, plus central borough coverage.
No station, walking distance or direct connection is inferred from these areas.
"""
import re

ZONES = [
    {'id': 'central', 'label': 'Central London', 'places': 'West End · City · Waterloo · London Bridge'},
    {'id': 'north', 'label': 'North London', 'places': 'Camden · Holloway · Tottenham · Barnet'},
    {'id': 'north-west', 'label': 'North-west London', 'places': 'Wembley · Kilburn · Harrow'},
    {'id': 'east', 'label': 'East London', 'places': 'Hackney · Whitechapel · Stratford · Ilford'},
    {'id': 'south-east', 'label': 'South-east London', 'places': 'Peckham · Greenwich · Lewisham · Bromley'},
    {'id': 'south-west', 'label': 'South & south-west London', 'places': 'Brixton · Croydon · Wimbledon · Richmond'},
    {'id': 'west', 'label': 'West London', 'places': 'Hammersmith · Acton · Ealing · Hounslow'},
]
BOROUGH_ZONES = {
    'City of London': 'central', 'Westminster': 'central',
    'Barnet': 'north', 'Camden': 'north', 'Enfield': 'north',
    'Haringey': 'north', 'Islington': 'north',
    'Brent': 'north-west', 'Harrow': 'north-west',
    'Hackney': 'east', 'Tower Hamlets': 'east', 'Newham': 'east',
    'Waltham Forest': 'east', 'Redbridge': 'east',
    'Barking and Dagenham': 'east', 'Havering': 'east',
    'Southwark': 'south-east', 'Greenwich': 'south-east', 'Lewisham': 'south-east',
    'Bexley': 'south-east', 'Bromley': 'south-east',
    'Lambeth': 'south-west', 'Wandsworth': 'south-west', 'Croydon': 'south-west',
    'Merton': 'south-west', 'Sutton': 'south-west',
    'Richmond upon Thames': 'south-west', 'Kingston upon Thames': 'south-west',
    'Ealing': 'west', 'Hounslow': 'west', 'Hillingdon': 'west',
    'Hammersmith and Fulham': 'west', 'Kensington and Chelsea': 'west',
}


def _norm(value):
    return ' '.join(str(value).casefold().replace('&', ' and ').replace('’', "'").split()).strip(' ,.;:')


_BOROUGH_NAMES = {_norm(b): b for b in BOROUGH_ZONES}
_BOROUGH_NAMES.update({'richmond': 'Richmond upon Thames', 'kingston': 'Kingston upon Thames',
                       'city of westminster': 'Westminster', 'hammersmith': 'Hammersmith and Fulham',
                       'kensington': 'Kensington and Chelsea', 'barking': 'Barking and Dagenham'})
_LONDON_WORDS = {'london', 'greater london', 'across london', 'london wide', 'london-wide',
                 'all of london', 'all london'}


def stated(op):
    """What the charity's page names as this role's places (the stated_places field).

    Returns (boroughs, london_only, elsewhere): London boroughs named, whether the page
    says just "London", and any other places named (Bournemouth, Reading ...).
    """
    boroughs, elsewhere, london_word = set(), [], False
    for place in op.get('stated_places') or []:
        n = _norm(place)
        if n in _BOROUGH_NAMES:
            boroughs.add(_BOROUGH_NAMES[n])
        elif n in _LONDON_WORDS:
            london_word = True
        else:
            elsewhere.append(place)
    return sorted(boroughs), (london_word and not boroughs), elsewhere


def in_london(op):
    """False only when the page names places for the role and none is in London.

    Remote and own-home roles can be done from anywhere, so a place named for them
    does not take them out of London. A role with no stated place is kept: nothing
    says it is elsewhere.
    """
    if op['location_type'] in ('remote', 'own_home') or not op.get('stated_places'):
        return True
    boroughs, london_only, _ = stated(op)
    return bool(boroughs) or london_only


def stated_boroughs(op):
    """London boroughs the page names for the role (never the charity's coverage)."""
    if op['location_type'] in ('remote', 'own_home') or op.get('postcode_district'):
        return []
    return stated(op)[0]


def zones_for(op, orgs, district_borough):
    if op['location_type'] in ('remote', 'own_home'):
        return []
    district = (op.get('postcode_district') or '').upper().strip()
    if district:
        match = re.fullmatch(r'([A-Z]+)(\d+)[A-Z]?', district)
        if match:
            prefix, number = match.groups()
            if prefix in ('EC', 'WC') or (prefix in ('W', 'SW', 'SE') and number == '1'):
                return ['central']
        borough = district_borough.get(district)
        if borough in BOROUGH_ZONES:
            return [BOROUGH_ZONES[borough]]
        # A district we cannot place must not inherit a charity's unrelated venues.
        return []
    boroughs, london_only, _ = stated(op)
    if boroughs:
        # Named for this role on the charity's page: beats the charity's coverage.
        return sorted({BOROUGH_ZONES[b] for b in boroughs})
    if london_only:
        return []           # "London" names no area; it must not inherit the charity's
    if op.get('role_zones'):
        # Areas the charity's own page names for this role; more specific than
        # the charity's general coverage.
        valid = {z['id'] for z in ZONES}
        return sorted(z for z in set(op['role_zones']) if z in valid)
    coverage = orgs[op['org_id']].get('boroughs', [])
    return sorted({BOROUGH_ZONES[b] for b in coverage if b in BOROUGH_ZONES})


def location_basis(op, orgs):
    if op['location_type'] in ('remote', 'own_home'):
        return op['location_type']
    if op.get('postcode_district'):
        return 'postcode'
    boroughs, london_only, _ = stated(op)
    if boroughs:
        return 'role_areas'
    if london_only:
        return 'london_wide'
    if op.get('role_zones'):
        return 'role_areas'
    if orgs[op['org_id']].get('boroughs'):
        return 'charity_coverage'
    if op.get('london_wide'):
        return 'london_wide'
    return 'unknown'


def area_label(op, orgs):
    """Words for a role with no postcode or borough, or None when nothing is stated.

    Only what the charity's page said: named areas, or "Across London". Never a
    guessed venue.
    """
    if op['location_type'] in ('remote', 'own_home') or op.get('postcode_district'):
        return None
    boroughs, london_only, _ = stated(op)
    if boroughs:
        return ', '.join(boroughs)
    if london_only:
        return 'London'
    if op.get('role_zones'):
        names = {z['id']: z['label'] for z in ZONES}
        return ', '.join(names[z] for z in zones_for(op, orgs, {}) if z in names) or None
    if not orgs[op['org_id']].get('boroughs') and op.get('london_wide'):
        return 'Across London'
    return None
