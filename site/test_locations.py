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


def test_remote_and_hosting_do_not_inherit_charity_locations():
    for kind in ('remote', 'own_home'):
        assert locations.zones_for(role('E1', kind), ORGS, DISTRICTS) == []


def test_every_london_borough_has_one_browsing_area():
    assert len(locations.BOROUGH_ZONES) == 33
    assert len(locations.ZONES) == 7
    assert set(locations.BOROUGH_ZONES.values()) == {zone['id'] for zone in locations.ZONES}
