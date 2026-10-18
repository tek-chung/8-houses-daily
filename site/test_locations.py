"""Geographic grouping must not invent a venue or a convenient journey."""
import locations

DISTRICTS = {'SE18': 'Greenwich', 'NW5': 'Camden', 'SW4': 'Lambeth', 'E1': 'Tower Hamlets'}
ORGS = {'sample': {'boroughs': ['Westminster', 'Haringey', 'Hackney']}}


def role(district=None, kind='in_person'):
    return {'org_id': 'sample', 'postcode_district': district, 'location_type': kind}


def test_central_districts_do_not_swallow_outer_postcodes():
    for district in ('WC2N', 'EC1', 'W1', 'SW1P', 'SE1'):
        assert locations.zones_for(role(district), ORGS, DISTRICTS) == ['central']
    assert locations.zones_for(role('SE18'), ORGS, DISTRICTS) == ['south-east']
    assert locations.zones_for(role('SW4'), ORGS, DISTRICTS) == ['south-west']


def test_stated_postcode_overrides_organisation_coverage():
    assert locations.zones_for(role('E1'), ORGS, DISTRICTS) == ['east']
    assert locations.zones_for(role('NW5'), ORGS, DISTRICTS) == ['north']
    assert locations.location_basis(role('E1'), ORGS) == 'postcode'


def test_multi_area_coverage_is_explicit_and_unknown_district_is_not_guessed():
    assert locations.zones_for(role(), ORGS, DISTRICTS) == ['central', 'east', 'north']
    assert locations.location_basis(role(), ORGS) == 'charity_coverage'
    assert locations.zones_for(role('ZZ99'), ORGS, DISTRICTS) == []
    assert locations.zones_for(role(), {'sample': {'boroughs': []}}, DISTRICTS) == []


def test_role_zones_come_from_the_page_and_beat_charity_coverage():
    op = {**role(), 'role_zones': ['north', 'east', 'south-east']}
    assert locations.zones_for(op, ORGS, DISTRICTS) == ['east', 'north', 'south-east']
    assert locations.location_basis(op, ORGS) == 'role_areas'
    assert locations.area_label({**op, 'org_id': 'bare'}, {'bare': {}}) == \
        'East London, North London, South-east London'
    # A stated postcode still wins, and remote roles ignore areas entirely.
    assert locations.zones_for({**op, 'postcode_district': 'E1'}, ORGS, DISTRICTS) == ['east']
    assert locations.zones_for({**op, 'location_type': 'remote'}, ORGS, DISTRICTS) == []


def test_london_wide_is_only_said_when_the_page_said_it():
    bare = {'bare': {'boroughs': []}}
    plain = {'org_id': 'bare', 'postcode_district': None, 'location_type': 'in_person'}
    assert locations.area_label(plain, bare) is None
    assert locations.location_basis(plain, bare) == 'unknown'
    wide = {**plain, 'london_wide': True}
    assert locations.area_label(wide, bare) == 'Across London'
    assert locations.location_basis(wide, bare) == 'london_wide'
    assert locations.zones_for(wide, bare, DISTRICTS) == []
    # Charity coverage, when present, is the more specific statement.
    assert locations.area_label({**wide, 'org_id': 'sample'}, ORGS) is None


def stated(places, kind='in_person', district=None):
    return {'org_id': 'sample', 'postcode_district': district, 'location_type': kind,
            'stated_places': places}


def test_places_the_page_names_beat_the_charitys_coverage():
    """Workshop Assistant is Hammersmith and Fulham and Hackney, not the charity's
    Westminster, Haringey and Hackney."""
    op = stated(['Hammersmith and Fulham', 'Hackney'])
    assert locations.stated_boroughs(op) == ['Hackney', 'Hammersmith and Fulham']
    assert locations.zones_for(op, ORGS, DISTRICTS) == ['east', 'west']
    assert locations.location_basis(op, ORGS) == 'role_areas'
    assert locations.in_london(op)
    assert locations.zones_for(stated(['hammersmith & fulham']), ORGS, DISTRICTS) == ['west']


def test_a_role_placed_only_outside_london_is_not_a_london_role():
    """The St Mungo's Outreach Volunteer: Bournemouth and Reading."""
    op = stated(['Bournemouth', 'Reading'])
    assert not locations.in_london(op)
    # One London place is enough to keep it, and only that place is its area.
    mixed = stated(['Bournemouth', 'Reading', 'Oxford', 'Westminster'])
    assert locations.in_london(mixed) and locations.stated_boroughs(mixed) == ['Westminster']
    # Nothing stated: nothing says it is elsewhere, so it stays.
    assert locations.in_london(stated([])) and locations.in_london(role())
    # Remote work can be done from anywhere.
    assert locations.in_london(stated(['Bristol'], kind='remote'))


def test_bare_london_does_not_inherit_the_charitys_boroughs():
    op = stated(['London'])
    assert locations.in_london(op)
    assert locations.zones_for(op, ORGS, DISTRICTS) == []
    assert locations.location_basis(op, ORGS) == 'london_wide'
    assert locations.area_label(op, ORGS) == 'London'


def test_a_stated_postcode_still_beats_stated_places():
    assert locations.zones_for(stated(['Hackney'], district='SW4'), ORGS, DISTRICTS) == ['south-west']
    assert locations.stated_boroughs(stated(['Hackney'], district='SW4')) == []


def test_remote_and_hosting_do_not_inherit_charity_locations():
    for kind in ('remote', 'own_home'):
        assert locations.zones_for(role('E1', kind), ORGS, DISTRICTS) == []


def test_every_london_borough_has_one_browsing_area():
    assert len(locations.BOROUGH_ZONES) == 33
    assert len(locations.ZONES) == 7
    assert set(locations.BOROUGH_ZONES.values()) == {zone['id'] for zone in locations.ZONES}


def test_london_neighbourhoods_count_as_their_borough():
    """A role "in Plumstead" or "at Clapham" is a London role. These were read as
    elsewhere and hidden until the neighbourhood names were taught."""
    for place, borough in [('Plumstead', 'Greenwich'), ('Clapham', 'Lambeth'), ('East Sheen', 'Richmond upon Thames'),
                           ('Wallington', 'Sutton'), ("King's Cross", 'Camden'), ('the City of London', 'City of London')]:
        op = stated([place])
        assert locations.in_london(op), place
        assert locations.stated_boroughs(op) == [borough], place
    mixed = stated(['West Norwood', 'Wallington', 'Caterham-on-the-Hill'])
    assert locations.in_london(mixed)
    assert locations.stated_boroughs(mixed) == ['Lambeth', 'Sutton']


def test_london_labels_say_london_without_naming_an_area():
    for label in ('South London', 'London - Croydon Skylight', 'London-wide Services team', 'West London'):
        op = stated([label])
        assert locations.in_london(op), label
        assert locations.stated_boroughs(op) == [], label
        assert locations.location_basis(op, ORGS) == 'london_wide', label


def test_places_outside_london_stay_outside():
    """Teaching the neighbourhoods must not let Surrey or the south coast in."""
    for place in ('Bournemouth', 'Reading', 'Caterham', 'Bristol', 'London Colney', 'Watford'):
        assert not locations.in_london(stated([place])), place
    # Places that straddle two boroughs are not guessed.
    for place in ('Blackheath', 'Finsbury Park', 'Kilburn', 'Crystal Palace'):
        assert not locations.in_london(stated([place])), place
