"""Static guards: only archive.py touches the observation file, and the season
configuration matches the pre-registration."""
from pathlib import Path

from denguecast import config

SRC = Path(__file__).resolve().parents[1] / "src" / "denguecast"


def test_only_archive_reads_observations_file():
    offenders = []
    for py in SRC.glob("*.py"):
        if py.name in ("archive.py", "config.py"):
            continue
        text = py.read_text()
        if "OBSERVATIONS_FILE" in text or "observations.csv" in text:
            offenders.append(py.name)
    assert not offenders, f"Only archive.py may read observations: {offenders}"


def test_season_split_matches_preregistration():
    assert config.TRAIN_SEASONS == {2022}
    assert config.VALIDATION_SEASONS == {2023}
    assert config.TEST_SEASONS == {2024, 2025}
    assert not (config.DEV_SEASONS & config.TEST_SEASONS)


def test_quantiles_match_preregistration():
    assert config.QUANTILES == [0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975]
