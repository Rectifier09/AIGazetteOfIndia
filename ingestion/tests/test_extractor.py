from pathlib import Path
from extractor import parse_central, parse_gujarat

SAMPLES = Path(__file__).parent.parent / "samples"


def test_parse_central_extracts_core_fields():
    text = (SAMPLES / "central_so_2455.txt").read_text()
    rec = parse_central(text)
    assert rec.gazette_id == "CG-DL-E-14052026-272564"
    assert rec.gazette_type == "EXTRAORDINARY"
    assert rec.notification_number == "S.O. 2455(E)"
    assert rec.act_reference == "Code on Wages, 2019 (29 of 2019)"
    assert rec.issuing_authority == "Ministry of Labour And Employment"


def test_parse_central_detects_supersession_relationship():
    text = (SAMPLES / "central_so_2457.txt").read_text()
    rec = parse_central(text)
    assert len(rec.relationships) == 1
    rel = rec.relationships[0]
    assert rel.rel_type == "supersedes"
    assert "2765" in rel.target
    assert "1965" in rel.target


def test_parse_gujarat_extracts_core_fields():
    text = (SAMPLES / "gujarat_wages.txt").read_text()
    rec = parse_gujarat(text)
    assert rec.gazette_id == "Gujarat-Extra-62"
    assert rec.issuing_authority == "Labour, Skill Development And Employment Department"
    assert rec.act_reference == "Code on Wages, 2019 (29 of 2019)"
