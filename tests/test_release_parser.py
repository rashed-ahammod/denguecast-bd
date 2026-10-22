import json
from pathlib import Path

import pytest

from denguecast.release_parser import parse_release_text

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "release_reprints_2026.json").read_text())


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["id"] for f in FIXTURES])
def test_real_reprints(fx):
    r = parse_release_text(fx["text"])
    assert r.counts == fx["expected_counts"]
    assert r.stated_total == fx["expected_total"]
    assert r.consistent == fx["expected_consistent"]
    if not fx["expected_consistent"]:
        assert any("sum to" in w for w in r.warnings)


def test_no_total_is_warned():
    r = parse_release_text("12 in Khulna division and 3 in Sylhet division")
    assert r.counts == {"KHULNA_DIV": 12, "SYLHET_DIV": 3}
    assert r.stated_total is None and not r.consistent
