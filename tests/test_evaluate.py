"""Replay engine, phases and bootstrap. Archives here are SYNTHETIC."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from denguecast import archive, config, evaluate
from conftest import synthetic_daily_rows


def test_replay_refuses_test_seasons_without_variable(tmp_archive):
    for season in (2024, 2025):
        with pytest.raises(archive.SeasonLockError):
            evaluate.replay(season, ["persistence"])
        with pytest.raises(archive.SeasonLockError):
            evaluate.histories(season)


def test_as_of_is_saturday_2359_bdt():
    t = evaluate.as_of_for(pd.Timestamp("2023-10-28"))
    assert t.isoformat() == "2023-10-28T17:59:00+00:00"
    assert t.tz_convert("Asia/Dhaka").strftime("%a %H:%M") == "Sat 23:59"


def test_replay_and_scoring_on_synthetic_archive(tmp_archive):
    rows = synthetic_daily_rows(date(2022, 1, 2), date(2023, 3, 4), seed=1)
    rows["source"] = "mendeley_z5mvwrfgsz"  # a truth source; rows remain SYNTHETIC (see note column)
    archive.append_observations(rows)
    hist = evaluate.histories(2023)
    assert list(hist)[0] == pd.Timestamp("2023-01-07")
    # history at each origin never extends past that origin
    for origin, h in hist.items():
        assert pd.to_datetime(h["week_end"]).max() == origin
    fc, info = evaluate.replay(2023, ["persistence"], hist=hist)
    truth = evaluate.truth_for(2023, list(hist), evaluated_at="2024-06-01T00:00:00+00:00")
    scores = evaluate.score_all(fc, truth)
    assert {"count", "log1p"} == set(scores["scale"])
    assert (scores["wis"] >= 0).all() and len(scores) > 0
    assert set(truth["truth_source"].replace("", np.nan).dropna()) == {"mendeley_z5mvwrfgsz (7 daily)"}


def test_phase_labels():
    weeks = [pd.Timestamp(o) for o in evaluate.season_origins(2023)]
    vals = [10.0] * 20 + [10.0 * 1.5 ** i for i in range(1, 11)] + [576.0] + [576.0 / 1.5 ** i for i in range(1, 22)]
    truth = pd.DataFrame({"unit": "X", "week_end": [w.date() for w in weeks], "value": vals[:52]})
    ph = evaluate.phase_labels(truth, 2023).set_index("week_end")["phase"]
    assert ph[weeks[30].date()] == "peak"
    assert ph[weeks[0].date()] == "low"
    assert ph[weeks[25].date()] == "growth"
    assert ph[weeks[33].date()] == "decline"


def _scores(seed):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(30):
        for u in ("A", "B"):
            for h in (1, 2):
                rows.append({"unit": u, "origin_week_end": date(2023, 1, 7) + timedelta(weeks=i), "horizon": h,
                             "wis": float(rng.gamma(2.0, 5.0))})
    return pd.DataFrame(rows)


def test_bootstrap_reproducible_and_brackets_point():
    m, c = _scores(1), _scores(2)
    b1, b2 = evaluate.bootstrap(m, c), evaluate.bootstrap(m, c)
    assert b1 == b2
    assert b1["lower95"] <= b1["relative_wis"] <= b1["upper95"]
    assert b1["n_weeks"] == 30 and b1["seed"] == config.RANDOM_SEED
    assert evaluate.bootstrap(c, c)["relative_wis"] == 1.0
