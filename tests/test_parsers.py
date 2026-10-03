"""Wikipedia cell parsing, name matching and team normalisation."""
from src.enrich import bowling_type
from src.ingest import canonical_venue
from src.player_map import score_pair
from src.teams import team_code
from src.wiki_auction import parse_cell, parse_tables


def test_money_templates():
    assert parse_cell("{{INRConvert|18|c|lk=on}}").lakh == 1800
    assert parse_cell("{{INRConvert|30|l}}").lakh == 30
    assert parse_cell("₹6.75 crore").lakh == 675


def test_sortname_with_disambiguation():
    c = parse_cell('scope="row" | {{sortname|Sarfaraz|Khan|dab=cricketer}}'.split("|", 1)[1])
    assert c.text == "Sarfaraz Khan"
    assert c.link == "Sarfaraz Khan (cricketer)"


def test_country_flag():
    assert parse_cell("{{cr|IND}}").country == "IND"
    assert parse_cell("{{cr|West Indies}}").country == "WEST INDIES"


def test_table_rowspan_and_colspan():
    text = """== Sold players ==
{| class="wikitable"
! Name !! Team !! Price
|-
| [[A Player]] || rowspan="2" | [[Mumbai Indians]] || 100
|-
| [[B Player]] || 200
|-
| colspan="2" | [[C Player]] || 300
|}"""
    t = parse_tables(text)[0]
    assert [c.text for c in t.rows[1]] == ["B Player", "Mumbai Indians", "200"]
    assert [c.text for c in t.rows[2]] == ["C Player", "C Player", "300"]


def test_team_aliases():
    assert team_code("Kings XI Punjab") == "PBKS"
    assert team_code("Royal Challengers Bangalore") == "RCB"
    assert team_code("Delhi Daredevils") == "DC"


def test_venue_canonicalisation():
    assert canonical_venue("Wankhede Stadium, Mumbai") == canonical_venue("Wankhede Stadium")
    assert canonical_venue("Feroz Shah Kotla") == "Arun Jaitley Stadium, Delhi"


def test_bowling_type_primary_style_first():
    assert bowling_type("Left-arm unorthodox spin") == "wrist_spin"
    assert bowling_type("Slow left-arm orthodox") == "finger_spin"
    assert bowling_type("Right-arm medium; Right-arm offbreak") == "pace"
    assert bowling_type(None) is None


def test_name_matching_prefers_initials_and_team():
    good = score_pair("Ruturaj Gaikwad", "RD Gaikwad", same_team=True)
    wrong_initial = score_pair("Pratham Singh", "RK Singh", same_team=True)
    wrong_first_name = score_pair("Pratham Singh", "Harbhajan Singh", same_team=False)
    assert good >= 100
    assert wrong_initial < good
    assert wrong_first_name < 70
