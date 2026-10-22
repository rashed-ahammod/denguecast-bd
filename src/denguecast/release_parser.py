"""Parse division-level admissions from DGHS daily release text.

DGHS's daily dengue statement is reprinted by BSS, UNB and newspapers in a
few recurring sentence patterns, e.g.
  "(of the 371) 69 patients were hospitalised in Barishal division, 91 in
   Chattogram division, ... and two in Sylhet division"
The parser never guesses silently: it returns every count it found, the total
the text states, and warnings (sum mismatch, ambiguous names, leading zeros).
A reprint that omits some areas will show a sum mismatch, and must be
flagged rather than "fixed".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

# Longest / most specific names first so "Dhaka North City Corporation" wins over "Dhaka".
UNIT_PATTERNS: list[tuple[str, str]] = [
    ("DNCC", r"Dhaka\s+North\s+City\s+Corporation(?:\s*\(DNCC\))?|DNCC"),
    ("DSCC", r"Dhaka\s+South\s+City\s+Corporation(?:\s*\(DSCC\))?|DSCC"),
    ("DHAKA_DIV", r"Dhaka(?!\s+(?:North|South))(?:\s+[Dd]ivision)?"),
    ("CHATTOGRAM_DIV", r"(?:Chattogram|Chittagong)(?:\s+[Dd]ivision)?"),
    ("BARISHAL_DIV", r"(?:Barishal|Barisal)(?:\s+[Dd]ivision)?"),
    ("KHULNA_DIV", r"Khulna(?:\s+[Dd]ivision)?"),
    ("RAJSHAHI_DIV", r"Rajshahi(?:\s+[Dd]ivision)?"),
    ("RANGPUR_DIV", r"Rangpur(?:\s+[Dd]ivision)?"),
    ("MYMENSINGH_DIV", r"Mymensingh(?:\s+[Dd]ivision)?"),
    ("SYLHET_DIV", r"Sylhet(?:\s+[Dd]ivision)?"),
]
_UNIT_ALT = "|".join(f"(?P<{code}>{pat})" for code, pat in UNIT_PATTERNS)
_NUM = r"(?P<num>\d[\d,]*|" + "|".join(NUMBER_WORDS) + r")"

# Pattern A: "<num> [patients] [were hospitalised|admitted] in [the] <unit>"
PATTERN_A = re.compile(
    _NUM + r"\s+(?:patients?\s+)?(?:(?:were|was)\s+(?:hospitalised|hospitalized|admitted)\s+)?in\s+(?:the\s+)?(?:" + _UNIT_ALT + r")",
    re.IGNORECASE,
)
# Pattern B: "<unit> [Division] [(...)] recorded|reported|logged <num>"
PATTERN_B = re.compile(
    r"(?:" + _UNIT_ALT + r")\s*(?:\([^)]*\))?\s*(?:recorded|reported|logged)\s+" + _NUM,
    re.IGNORECASE,
)
TOTAL_PATTERN = re.compile(r"\bof\s+the\s+(\d[\d,]*)", re.IGNORECASE)


@dataclass
class ParsedRelease:
    counts: dict[str, int]
    stated_total: int | None
    warnings: list[str] = field(default_factory=list)

    @property
    def parsed_sum(self) -> int:
        return sum(self.counts.values())

    @property
    def consistent(self) -> bool:
        return self.stated_total is not None and self.parsed_sum == self.stated_total


def _to_int(token: str) -> tuple[int, str | None]:
    t = token.strip().lower()
    if t in NUMBER_WORDS:
        return NUMBER_WORDS[t], None
    digits = t.replace(",", "")
    warn = f"leading zero in '{token}'" if len(digits) > 1 and digits.startswith("0") else None
    return int(digits), warn


def _unit_of(match: re.Match) -> str:
    for code, _ in UNIT_PATTERNS:
        if match.group(code):
            return code
    raise AssertionError("unreachable")


def parse_release_text(text: str) -> ParsedRelease:
    norm = re.sub(r"\s+", " ", text)
    counts: dict[str, int] = {}
    warnings: list[str] = []
    for pattern in (PATTERN_A, PATTERN_B):
        for m in pattern.finditer(norm):
            unit = _unit_of(m)
            value, warn = _to_int(m.group("num"))
            if warn:
                warnings.append(warn)
            matched_name = m.group(unit)
            if unit == "DHAKA_DIV" and "division" not in matched_name.lower():
                warnings.append("bare 'Dhaka' read as Dhaka division outside the two city corporations")
            if unit in counts and counts[unit] != value:
                warnings.append(f"{unit} appears twice with different values ({counts[unit]} vs {value})")
                continue
            counts[unit] = value
    total_match = TOTAL_PATTERN.search(norm)
    stated_total = int(total_match.group(1).replace(",", "")) if total_match else None
    result = ParsedRelease(counts=counts, stated_total=stated_total, warnings=warnings)
    if stated_total is None:
        result.warnings.append("no stated total found; cannot check completeness")
    elif not result.consistent:
        result.warnings.append(
            f"parsed areas sum to {result.parsed_sum} but release states {stated_total}; "
            "the reprint may omit areas"
        )
    return result
