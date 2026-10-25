# Data sources

All sources are public. Raw downloads are stored unchanged under `data/raw/`
and logged with SHA-256 hashes in `data/archive/raw_manifest.csv`.

| Source | Use | Status |
| --- | --- | --- |
| [DGHS Dengue Dynamic Dashboard](https://dashboard.dghs.gov.bd/pages/heoc_dengue_v1.php) (Health Emergency Operation Center & Control Room, DGHS) | Live daily and epi-week admissions | Returned HTTP 403 to automated requests on 2026-10-25; no table parser; live values come from manual entry |
| DGHS daily dengue releases, as reprinted by BSS, UNB and newspapers | First-reported daily values | Parser built and tested on 6 real 2026 reprints; manual entry path available |
| [Mendeley: division-wise daily dengue cases with weather, 2022-2024](https://data.mendeley.com/datasets/z5mvwrfgsz/1) (Naher, 2026, DOI 10.17632/z5mvwrfgsz.1) | Development seasons 2022-2023; test season 2024 | Verified 2026-10-25: 8 daily division files, no gaps in 2022-2023, no DNCC/DSCC split, no national series; licence **CC BY 4.0** |
| [Mendeley: monthly division-level dengue cases, 2020-2025](https://data.mendeley.com/datasets/cgwjshkx5k) (DOI 10.17632/cgwjshkx5k.2) | Cross-check only (monthly) | Downloaded; licence CC BY 4.0; not used |
| Open-Meteo Historical Weather API (ERA5) and Previous Runs API | Weather features | Reachable (probe 2026-10-25); not used for this submission (D3) |
| BBS Population and Housing Census 2022 | Population weights | Not used for this submission (D3) |

Credit: case data are published by the Directorate General of Health Services,
Bangladesh. Dataset authors are credited above; check each dataset's licence
before redistributing its files.
