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
    coverage = orgs[op['org_id']].get('boroughs', [])
    return sorted({BOROUGH_ZONES[b] for b in coverage if b in BOROUGH_ZONES})


def location_basis(op, orgs):
    if op['location_type'] in ('remote', 'own_home'):
        return op['location_type']
    if op.get('postcode_district'):
        return 'postcode'
    if orgs[op['org_id']].get('boroughs'):
        return 'charity_coverage'
    return 'unknown'
