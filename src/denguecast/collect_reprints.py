"""Collect 2026 DGHS daily dengue releases from public newspaper reprints.

The DGHS dashboard refuses automated requests, so past daily releases are
recovered from reprints that sites publish the same day. Discovery uses each
site's public sitemap (bdnews24 daily sitemaps; The Report health sitemap);
pages are fetched politely with an honest user-agent and a delay.

Nothing is guessed. A day is accepted only when the admissions sentence(s)
give area counts that sum EXACTLY to the stated national total. Each sentence
is read in both word orders ("146 in DSCC" and "Rajshahi recorded 141"); a
day is accepted only if exactly one reading sums to the total. Where two
sites cover the same day they must agree, otherwise the day is rejected.
The "since 1 January" cumulative total, where printed, is kept as a check of
the date assignment (consecutive cumulative totals must differ by the day's
total).

For each page, the extracted text (title, publication time, paragraphs) is
stored with archive.save_raw_snapshot, with the SHA-256 of the full page in
its header; full pages are not stored, to keep the repository small.

Output: data/manual/reprints_2026.csv in the daily_releases.csv format (plus
cumulative_total), and results/reprints/reprints_report_<start>_<end>.csv with every candidate
and why it was accepted or rejected.

Usage:  python -m denguecast.collect_reprints [--start 2026-01-01] [--end 2026-10-17]
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import itertools
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from . import archive, config

USER_AGENT = "DengueCastBD-research-archiver/0.1 (+https://github.com/rashed-ahammod/denguecast-bd)"
DELAY_S = 1.5
CACHE_DIR = config.REPO_ROOT / ".cache" / "reprints"  # local HTTP cache, not committed
OUT_FILE = config.MANUAL_DIR / "reprints_2026.csv"
REPORT_FILE = config.REPO_ROOT / "results" / "reprints" / "report.csv"  # one file per run, named by date range
BDT = timezone(timedelta(hours=6))

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
                "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "zero": 0, "none": 0}
NUM = r"(\d{1,3}(?:,\d{3})+|\d+|" + "|".join(NUMBER_WORDS) + r")"
# Most specific first. Order matters: city corporations before "Dhaka".
UNITS = [
    ("DNCC", r"Dhaka\s+North(?:\s+City(?:\s+Corporation)?)?(?:\s*\(DNCC\))?|DNCC"),
    ("DSCC", r"Dhaka\s+South(?:\s+City(?:\s+Corporation)?)?(?:\s*\(DSCC\))?|DSCC"),
    # Dhaka division outside the city corporations is often written without the word "Dhaka division"
    ("DHAKA_DIV", r"(?:places\s+)?outside\s+(?:of\s+)?(?:the\s+)?two\s+(?:Dhaka\s+)?city\s+corporations|Dhaka(?:\s+[Dd]ivision)?"),
    ("CHATTOGRAM_DIV", r"(?:Chattogram|Chittagong)(?:\s+[Dd]ivision)?"),
    ("BARISHAL_DIV", r"(?:Barishal|Barisal)(?:\s+[Dd]ivision)?"),
    ("KHULNA_DIV", r"Khulna(?:\s+[Dd]ivision)?"),
    ("RAJSHAHI_DIV", r"(?:Rajshahi|Rajhshahi)(?:\s+[Dd]ivision)?"),
    ("RANGPUR_DIV", r"Rangpur(?:\s+[Dd]ivision)?"),
    ("MYMENSINGH_DIV", r"Mymensingh(?:\s+[Dd]ivision)?"),
    ("SYLHET_DIV", r"Sylhet(?:\s+[Dd]ivision)?"),
]
UNIT_RE = re.compile("|".join(f"(?P<{c}>{p})" for c, p in UNITS))
DEATH_RE = re.compile(r"\b(die[ds]?|death|deaths|fatalit|toll|killed|lives)\b", re.I)
ADMIT_RE = re.compile(r"hospitali[sz]|admitt|admission|patients?|logged|recorded|reported", re.I)
TOTAL_RES = [
    re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s+(?:(?:new|more|other|others|fresh|dengue|patients?|people|cases|hospital)\s+){0,3}"
               r"(?:(?:were|was|have|has|had|been|got|being)\s+){0,2}(?:hospitali[sz]ed|admitted|hospitali[sz]ations|admissions)\b", re.I),
    re.compile(r"(?:hospitali[sz]ed|admitted)[^.]{0,40}?\b(\d{1,3}(?:,\d{3})+|\d+)\s+(?:new\s+)?(?:patients|people|cases)", re.I),
]
CUM_RE = re.compile(r"(?:since\s+(?:1\s+)?January|this\s+year|so\s+far|year\s+to\s+date|in\s+total|total\s+of|same\s+period)", re.I)


# ----------------------------------------------------------------- fetching
class Fetcher:
    def __init__(self, delay: float = DELAY_S):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.delay, self.last = delay, 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> bytes | None:
        key = CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".bin")
        if key.exists():
            return key.read_bytes()
        wait = self.delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        try:
            r = self.session.get(url, timeout=60)
        except requests.RequestException as exc:
            print(f"  fetch failed {url}: {exc}", file=sys.stderr)
            return None
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
            return None
        key.write_bytes(r.content)
        return r.content


# ---------------------------------------------------------------- discovery
def discover_bdnews(f: Fetcher, start: date, end: date) -> list[str]:
    urls, d = [], start
    while d <= end + timedelta(days=1):  # an evening article can be listed the next day
        x = f.get(f"https://bdnews24.com/sitemap/sitemap-daily-{d.isoformat()}.xml")
        if x:
            for block in re.findall(rb"<url>(.*?)</url>", x, re.S):
                b = block.decode("utf-8", "replace")
                if re.search(r"dengue", b, re.I):
                    urls.append(re.search(r"<loc>([^<]+)", b).group(1))
        d += timedelta(days=1)
    return sorted(set(urls))


def discover_report(f: Fetcher, start: date, end: date) -> list[str]:
    x = f.get("https://thereport.live/sitemaps/health.xml") or b""
    out = []
    for block in re.findall(rb"<url>(.*?)</url>", x, re.S):
        b = block.decode("utf-8", "replace")
        loc = re.search(r"<loc>([^<]+)", b).group(1)
        lm = re.search(r"<lastmod>(\d{4}-\d{2}-\d{2})", b)
        if re.search(r"dengue", loc, re.I) and re.search(r"hospitali|admitt", loc, re.I) and lm:
            if start - timedelta(days=3) <= date.fromisoformat(lm.group(1)) <= end + timedelta(days=60):
                out.append(loc)
    return sorted(set(out))


# ----------------------------------------------------------------- parsing
def page_parts(raw: bytes) -> tuple[str, datetime | None, list[str]]:
    h = raw.decode("utf-8", "replace")
    t = re.search(r'property="og:title"\s+content="([^"]*)"', h) or re.search(r"<title>(.*?)</title>", h, re.S)
    title = htmllib.unescape(t.group(1)).strip() if t else ""
    pub = None
    m = re.search(r'property="article:published_time"\s+content="([^"]+)"', h)
    if m:
        v = m.group(1)
        pub = datetime.fromtimestamp(int(v), tz=timezone.utc) if v.isdigit() else datetime.fromisoformat(v.replace("Z", "+00:00"))
    paras = [re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
             for p in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)]
    paras = [p.split("-->")[-1].strip() for p in paras]  # some pages glue inline scripts onto the lead paragraph
    junk = re.compile(r"googletag|function\s*\(|\{|Read More|window\.|@media")
    return title, pub, [p for p in paras if p and not junk.search(p)]


def _num(tok: str) -> int:
    t = tok.lower()
    return NUMBER_WORDS[t] if t in NUMBER_WORDS else int(t.replace(",", ""))


def stated_total(title: str, paras: list[str]) -> tuple[int | None, str]:
    """National 24-hour total from the headline, checked against the body."""
    def first(text):
        for rx in TOTAL_RES:
            for m in rx.finditer(text):
                v = _num(m.group(1))
                if v >= 1:
                    return v
        return None
    t = first(title)
    day = re.compile(r"24\s*hours|24-hour|past\s+day|in\s+a\s+day|overnight|during\s+that\s+period", re.I)
    body = next((v for p in paras if day.search(p) and not CUM_RE.search(p) for v in [first(p)] if v is not None), None)
    if t is not None and body is not None and t != body:
        return None, f"headline total {t} != body total {body}"
    return (t if t is not None else body), ""


def _sentences(paras: list[str]) -> list[str]:
    out = []
    for p in paras:
        out += [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z])", p) if s.strip()]
    return out


def _readings(sentence: str) -> list[dict[str, int]]:
    """Two readings of one sentence: number-before-area and area-before-number."""
    s = re.sub(r"\(\s*(?:DNCC|DSCC)\s*\)", "", sentence)
    spans = [(m.start(), m.end(), next(c for c, _ in UNITS if m.group(c))) for m in UNIT_RE.finditer(s)]
    nums = [(m.start(), m.end(), _num(m.group(1))) for m in re.finditer(r"\b" + NUM + r"\b", s, re.I)]
    nums = [n for n in nums if not (1990 <= n[2] <= 2100 and re.search(r"(?:\bin|since|year)\s*$", s[:n[0]]))]
    a, b = {}, {}
    for us, ue, unit in spans:
        before = [n for n in nums if n[1] <= us and not any(ue2 <= us and ue2 > n[1] for _, ue2, _ in spans)]
        linked = re.search(r"\b(?:in|from|at|under|across)\b", s[before[-1][1]:us]) if before else None
        if before and us - before[-1][1] <= 60 and (linked or re.match(r"(?:places\s+)?outside", s[us:ue])):
            a[unit] = a.get(unit, before[-1][2]) if a.get(unit, before[-1][2]) == before[-1][2] else -1
        after = [n for n in nums if n[0] >= ue and not any(us2 >= ue and us2 < n[0] for us2, _, _ in spans)]
        if after and after[0][0] - ue <= 80:
            b[unit] = b.get(unit, after[0][2]) if b.get(unit, after[0][2]) == after[0][2] else -1
    return [r for r in (a, b) if r and -1 not in r.values()]


def area_counts(paras: list[str], total: int) -> tuple[dict[str, int] | None, str]:
    """Counts by area from the admissions sentence(s); exactly one consistent reading required."""
    sents = [s for s in _sentences(paras) if UNIT_RE.search(s) and not DEATH_RE.search(s) and ADMIT_RE.search(s)]
    options = [_readings(s) + [{}] for s in sents]
    found = set()
    for combo in itertools.product(*options):
        merged, ok = {}, True
        for r in combo:
            for k, v in r.items():
                if k in merged and merged[k] != v:
                    ok = False
                merged[k] = v
        if ok and merged and sum(merged.values()) == total:
            found.add(tuple(sorted(merged.items())))
    if not found:
        return None, "no reading of the admissions sentences sums to the stated total"
    if len(found) > 1:
        return None, f"{len(found)} different readings sum to the total (ambiguous)"
    counts = dict(next(iter(found)))
    if "DNCC" not in counts and "DSCC" not in counts and "DHAKA_DIV" in counts:
        counts[config.DHAKA_DIV_TOTAL] = counts.pop("DHAKA_DIV")  # Dhaka given as one figure incl. city corporations
    return counts, ""


def cumulative(paras: list[str], total: int) -> int | None:
    for p in paras:
        if CUM_RE.search(p) and re.search(r"admitt|hospitali|cases|infected|patients", p, re.I) and not DEATH_RE.search(p.split(".")[0]):
            vals = [_num(m) for m in re.findall(r"\b(\d{1,3}(?:,\d{3})+)\b", p)]
            vals = [v for v in vals if v > total]
            if vals:
                return vals[0]
    return None


def extract(url: str, raw: bytes) -> dict:
    title, pub, paras = page_parts(raw)
    row = {"url": url, "site": re.sub(r"^https?://(www\.)?", "", url).split("/")[0], "title": title,
           "published_bdt": pub.astimezone(BDT).isoformat() if pub else "", "report_date": pub.astimezone(BDT).date().isoformat() if pub else "",
           "page_sha256": hashlib.sha256(raw).hexdigest(), "total": None, "cumulative": None, "counts": None, "status": "", "reason": ""}
    if not pub:
        return {**row, "status": "rejected", "reason": "no publication time"}
    total, why = stated_total(title, paras)
    if total is None:
        return {**row, "status": "rejected", "reason": why or "no stated total"}
    counts, why = area_counts(paras, total)
    row.update(total=total, cumulative=cumulative(paras, total))
    if counts is None:
        return {**row, "status": "rejected", "reason": why}
    row["_text"] = "\n".join([f"title: {title}", f"published: {row['published_bdt']}", f"url: {url}",
                              f"full_page_sha256: {row['page_sha256']}", ""] + paras)
    return {**row, "counts": counts, "status": "consistent"}


# ------------------------------------------------------------- reconcile
def _coarse(counts: dict[str, int]) -> dict[str, int]:
    """Merge DHAKA_DIV + DNCC + DSCC into DHAKA_DIV_TOTAL so a split and an unsplit Dhaka figure can be compared."""
    c = dict(counts)
    if {"DHAKA_DIV", "DNCC", "DSCC"} <= set(c):
        c[config.DHAKA_DIV_TOTAL] = c.pop("DHAKA_DIV") + c.pop("DNCC") + c.pop("DSCC")
    return c


def reconcile(cands: list[dict], skip_dates: set[str]) -> tuple[pd.DataFrame, list[dict]]:
    by_date: dict[str, list[dict]] = {}
    for c in cands:
        if c["status"] == "consistent":
            by_date.setdefault(c["report_date"], []).append(c)
    accepted, rows = {}, []
    for d, cs in sorted(by_date.items()):
        if d in skip_dates:
            for c in cs:
                c.update(status="skipped", reason="date already entered by hand")
            continue
        distinct = {tuple(sorted(_coarse(c["counts"]).items())) for c in cs}
        if len(distinct) > 1:
            for c in cs:
                c.update(status="rejected", reason="sources disagree for this date")
            continue
        cum = next((c["cumulative"] for c in cs if c["cumulative"]), None)
        best = max(cs, key=lambda c: len(c["counts"]))  # most detailed: Dhaka split into DNCC / DSCC / rest
        cs = [best] + [c for c in cs if c is not best]
        accepted[d] = {"counts": best["counts"], "total": best["total"], "cum": cum, "cands": cs}
    # cumulative chain: cum(d) - cum(d-1) must equal total(d) where both are printed
    for d, a in accepted.items():
        prev = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
        if a["cum"] and prev in accepted and accepted[prev]["cum"]:
            a["chain"] = "ok" if a["cum"] - accepted[prev]["cum"] == a["total"] else f"mismatch ({a['cum'] - accepted[prev]['cum']} vs {a['total']})"
        else:
            a["chain"] = "unchecked"
    for d, a in accepted.items():
        cs = a["cands"]
        sources = " | ".join(c["url"] for c in cs)
        agree = f"{len(cs)} sources agree" if len(cs) > 1 else "single source"
        for c in cs:
            c.update(status="accepted", reason=f"{agree}; cumulative check {a['chain']}")
        for unit, v in a["counts"].items():
            rows.append({"report_date": d, "unit": unit, "admissions": v, "stated_total": a["total"], "source_url": cs[0]["url"],
                         "entered_by": "auto:collect_reprints",
                         "note": f"auto-extracted from reprint ({agree}; exact sum; cumulative check {a['chain']}); all sources: {sources}",
                         "release_complete": "yes", "cumulative_total": a["cum"] if a["chain"] == "ok" else ""})
    return pd.DataFrame(rows), cands


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-10-17")
    args = ap.parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    f = Fetcher()
    print("Discovering articles from sitemaps ...", flush=True)
    urls = discover_bdnews(f, start, end) + discover_report(f, start, end)
    print(f"  {len(urls)} candidate articles", flush=True)
    cands = []
    for i, u in enumerate(urls, 1):
        raw = f.get(u)
        if raw is None:
            cands.append({"url": u, "status": "rejected", "reason": "fetch failed"})
            continue
        c = extract(u, raw)
        if c.get("report_date") and not (start.isoformat() <= c["report_date"] <= end.isoformat()):
            continue
        cands.append(c)
        if i % 25 == 0:
            print(f"  {i}/{len(urls)} parsed", flush=True)
    manual = config.MANUAL_DIR / "daily_releases.csv"
    skip = set(pd.read_csv(manual, dtype=str)["report_date"]) if manual.exists() else set()
    out, cands = reconcile(cands, skip)
    for c in cands:
        if c.get("status") == "accepted" and c.get("_text"):
            archive.save_raw_snapshot(c["_text"].encode("utf-8"), f"reprint_{c['site'].split('.')[0]}", c["url"], "txt")
    if OUT_FILE.exists():  # keep earlier runs' days outside this run's range
        old = pd.read_csv(OUT_FILE, dtype={"report_date": str})
        old = old[~old["report_date"].between(start.isoformat(), end.isoformat())]
        out = pd.concat([old, out], ignore_index=True).sort_values(["report_date"], kind="stable")
    out.to_csv(OUT_FILE, index=False)
    rep = pd.DataFrame([{k: v for k, v in c.items() if k != "_text"} for c in cands])
    report_file = REPORT_FILE.with_name(f"reprints_report_{start.isoformat()}_{end.isoformat()}.csv")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    rep.to_csv(report_file, index=False)
    days = out["report_date"].nunique() if len(out) else 0
    print(f"Accepted {days} days ({len(out)} rows) -> {OUT_FILE.relative_to(config.REPO_ROOT)}; report -> {report_file.relative_to(config.REPO_ROOT)}")
    print(rep["status"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
