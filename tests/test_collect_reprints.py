"""Reprint extraction on real 2026 sentences (bdnews24, The Report), checked by hand
against the W42 releases in data/manual/daily_releases.csv."""
from denguecast import collect_reprints as cr

BDNEWS_2026_10_24 = [
    "Another six people have died from dengue and 1,898 have been hospitalised in Bangladesh over the past 24 hours.",
    "According to the DGHS bulletin issued on Tuesday, 159 patients were admitted to hospitals in Dhaka North City Corporation (DNCC), "
    "while 341 were admitted in Dhaka South City Corporation (DSCC).",
    "Hospitals elsewhere in Dhaka Division logged another 281 admissions.",
    "Khulna reported the highest number of admissions at 359, followed by Barishal with 252 and Chattogram with 232.",
    "Rajshahi recorded 141 admissions, Mymensingh 75, Rangpur 51 and Sylhet seven.",
]
REPORT_2026_10_22 = [
    "Four more people died of dengue in the past 24 hours, while 1,512 patients have been admitted to hospitals across the country "
    "with the mosquito-borne disease during the same period.",
    "According to the report, among the newly hospitalised patients, 146 were admitted in Dhaka South City Corporation, 111 in Dhaka "
    "North City Corporation, 294 in Chattogram division, 250 in Dhaka division outside the city corporations, 231 in Barishal division, "
    "206 in Khulna division, 162 in Rajshahi division, 60 in Mymensingh division, 44 in Rangpur division and eight in Sylhet division.",
    "During the same period, 118,502 dengue patients have been admitted to hospitals across the country.",
]
# bdnews24 printed Rajshahi as 164 on 22 Oct: areas sum to 1,514, not 1,512
BDNEWS_2026_10_22_TYPO = [
    "Bangladesh has recorded four more dengue deaths in a 24-hour count while 1,512 others have been admitted to hospitals around the country.",
    "Among the latest fatalities reported, one occurred at a hospital in an area under Dhaka North City Corporation, one in an area under "
    "Dhaka South City Corporation and two outside Mymensingh Division, according to the health directorate.",
    "Of the new admissions, 111 were in Dhaka North City Corporation and 146 in Dhaka South.",
    "Another 250 were admitted to hospitals elsewhere in Dhaka Division.",
    "Elsewhere, Barishal Division recorded 231 admissions, Chattogram 294, Khulna 206, Mymensingh 60, Rajshahi 164, Rangpur 44 and Sylhet eight.",
]
REPORT_2026_10_23 = [
    "Three more people died of dengue in the past 24 hours, while another 1,299 patients have been admitted to hospitals.",
    "According to the report, Dhaka Division recorded the highest number of new hospital admissions, with 521 patients admitted in the "
    "past 24 hours. Chattogram Division recorded 219 admissions, followed by Barishal with 159, Khulna with 147, Rajshahi with 113, "
    "Mymensingh with 100, Rangpur with 38 and Sylhet with two.",
]


def test_mixed_word_orders_and_deaths_ignored():
    total, why = cr.stated_total("Six more dengue deaths in Bangladesh, 1,898 hospitalised", BDNEWS_2026_10_24)
    assert total == 1898 and not why
    counts, why = cr.area_counts(BDNEWS_2026_10_24, total)
    assert counts == {"DNCC": 159, "DSCC": 341, "DHAKA_DIV": 281, "KHULNA_DIV": 359, "BARISHAL_DIV": 252,
                      "CHATTOGRAM_DIV": 232, "RAJSHAHI_DIV": 141, "MYMENSINGH_DIV": 75, "RANGPUR_DIV": 51, "SYLHET_DIV": 7}


def test_number_first_list_and_cumulative():
    total, _ = cr.stated_total("4 more die of dengue, 1512 hospitalised in 24 hours", REPORT_2026_10_22)
    counts, _ = cr.area_counts(REPORT_2026_10_22, total)
    assert total == 1512 and counts["RAJSHAHI_DIV"] == 162 and counts["DHAKA_DIV"] == 250 and sum(counts.values()) == 1512
    assert cr.cumulative(REPORT_2026_10_22, total) == 118502


def test_misprinted_reprint_is_rejected_not_fixed():
    total, _ = cr.stated_total("Four more die as dengue pushes this year's death toll to 368 in Bangladesh", BDNEWS_2026_10_22_TYPO)
    assert total == 1512
    counts, why = cr.area_counts(BDNEWS_2026_10_22_TYPO, total)
    assert counts is None and "sums to the stated total" in why


def test_single_dhaka_figure_becomes_dhaka_div_total():
    total, _ = cr.stated_total("3 more die of dengue, 1299 hospitalised in 24 hours", REPORT_2026_10_23)
    counts, _ = cr.area_counts(REPORT_2026_10_23, total)
    assert counts["DHAKA_DIV_TOTAL"] == 521 and "DHAKA_DIV" not in counts and sum(counts.values()) == 1299


def test_headline_and_body_must_agree():
    total, why = cr.stated_total("5 more die of dengue, 1999 hospitalised in 24 hours", BDNEWS_2026_10_24)
    assert total is None and "!=" in why


def _cand(url, counts, total, cum=None):
    return {"url": url, "site": "x", "report_date": "2026-10-23", "status": "consistent", "counts": counts, "total": total, "cumulative": cum}


def test_reconcile_split_and_unsplit_dhaka_agree_and_detail_wins():
    split = {"DHAKA_DIV": 274, "DNCC": 116, "DSCC": 131, "SYLHET_DIV": 2}
    whole = {"DHAKA_DIV_TOTAL": 521, "SYLHET_DIV": 2}
    out, _ = cr.reconcile([_cand("a", whole, 523), _cand("b", split, 523)], set())
    assert set(out["unit"]) == {"DHAKA_DIV", "DNCC", "DSCC", "SYLHET_DIV"}
    assert "2 sources agree" in out["note"].iloc[0]


def test_reconcile_disagreement_rejects_day_and_manual_dates_skipped():
    out, cands = cr.reconcile([_cand("a", {"SYLHET_DIV": 2, "KHULNA_DIV": 1}, 3), _cand("b", {"SYLHET_DIV": 1, "KHULNA_DIV": 2}, 3)], set())
    assert out.empty and all(c["status"] == "rejected" for c in cands)
    out, cands = cr.reconcile([_cand("a", {"SYLHET_DIV": 3}, 3)], {"2026-10-23"})
    assert out.empty and cands[0]["status"] == "skipped"


def test_dhaka_outside_city_corporations_phrase():
    paras = [
        "Two more people have died of dengue while 723 new patients have been hospitalised with the Aedes mosquito-borne disease "
        "across Bangladesh over the past 24-hour count.",
        "Of them, 101 were hospitalised in Dhaka North City Corporation, while 112 were admitted to hospitals under Dhaka South City Corporation.",
        "Another 107 patients were admitted outside the two Dhaka city corporations.",
        "Across other divisions, Barishal recorded 101 hospitalisations, Chattogram 83, Khulna 98, Mymensingh 45, Rajshahi 63, Rangpur 12, "
        "and Sylhet registered one.",
    ]
    total, _ = cr.stated_total("Two more die, 723 hospitalised with dengue fever", paras)
    counts, why = cr.area_counts(paras, total)
    assert total == 723 and counts["DHAKA_DIV"] == 107 and counts["SYLHET_DIV"] == 1 and sum(counts.values()) == 723, why


def test_publication_time_formats():
    assert cr._iso("2026-09-22T13:14:26+06:00.000+00:00").isoformat() == "2026-09-22T13:14:26+06:00"
    assert cr._iso("1792671558").isoformat() == "2026-10-22T12:19:18+00:00"
    assert cr._iso("2026-10-24T13:10:20Z").utcoffset().total_seconds() == 0
    assert cr._published('<script>{"datePublished": "2026-09-23T19:40:00+0600"}</script>').isoformat() == "2026-09-23T19:40:00+06:00"


def test_measles_and_single_hospital_articles_rejected():
    raw = (b'<meta property="og:title" content="Four more die with measles symptoms, 1,306 hospitalised">'
           b'<meta property="article:published_time" content="2026-10-15T12:00:00+00:00">'
           b"<p>Four more people have died with measles symptoms over the past 24 hours, while another 1,306 people have been admitted.</p>"
           b"<p>Of them, 1,000 were admitted in Dhaka Division, 200 in Khulna, 100 in Sylhet and six in Rangpur.</p>")
    assert "measles" in cr.extract("https://x/m", raw)["reason"]
    raw = (b'<meta property="og:title" content="Dengue: 127 hospitalised at Mymensingh hospital in 24 hours">'
           b'<meta property="article:published_time" content="2026-10-09T12:00:00+00:00">'
           b"<p>In the past 24 hours 127 dengue patients were admitted, all of them in Mymensingh division.</p>")
    assert "not a national bulletin" in cr.extract("https://x/h", raw)["reason"]


def test_morning_articles_rejected_as_ambiguous_date():
    raw = (b'<meta property="og:title" content="Dengue: 3 die, 1,299 hospitalised in 24 hours">'
           b'<meta property="article:published_time" content="2026-10-24T03:00:00+00:00">'  # 09:00 BDT
           b"<p>Three people died of dengue and 1,299 were hospitalised in 24 hours.</p>")
    assert "before noon" in cr.extract("https://x/a", raw)["reason"]


def test_retraction_rows_withdraw_only_dropped_values(tmp_archive):
    import pandas as pd
    from denguecast import archive
    old = pd.DataFrame({"report_date": ["2026-09-12", "2026-09-12", "2026-09-13"], "unit": ["KHULNA_DIV", "SYLHET_DIV", "KHULNA_DIV"]})
    new = pd.DataFrame({"report_date": ["2026-09-13"], "unit": ["KHULNA_DIV"]})
    rows = cr.retraction_rows(old, new, "2026-10-27T12:00:00+00:00", "morning article, date ambiguous")
    assert set(zip(rows.reference_date, rows.unit)) == {("2026-09-12", "KHULNA_DIV"), ("2026-09-12", "SYLHET_DIV"), ("2026-09-12", "NATIONAL")}
    # appended after an earlier value, the retraction makes get_data return no value for that day
    first = rows.iloc[[0]].assign(value="5", raw_sha256="orig", note="SYNTHETIC")
    archive.append_observations(first)
    archive.append_observations(rows)
    got = archive.get_data("2026-10-28T00:00:00+00:00", period="day")
    assert got["value"].isna().all()


def test_explicit_zero_area_and_whole_dhaka():
    paras = [
        "Two people died of dengue and 790 new patients were hospitalized across the country in the 24 hours to 8am on Friday.",
        "Among the newly admitted patients between 8am on Thursday and 8am on Friday, 372 were from Dhaka division, 73 from Mymensingh "
        "division, 196 from Chittagong division, 60 from Khulna division, 38 from Rangpur division, 33 from Rajshahi division and 18 from "
        "Barisal division.",
        "No new dengue patients were reported in Sylhet division during the period.",
    ]
    total, _ = cr.stated_total("Dengue: Two more die as 790 hospitalized in 24 hours", paras)
    counts, why = cr.area_counts(paras, total)
    assert counts["SYLHET_DIV"] == 0 and counts["DHAKA_DIV_TOTAL"] == 372 and sum(counts.values()) == 790, why
