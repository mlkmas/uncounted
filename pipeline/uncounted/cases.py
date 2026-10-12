"""Case definitions (what to estimate, where, when)."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .canonical import ROOT

CASES_FILE = ROOT / "cases.json"
MARGIN_DAYS = 21  # extra days fetched around the window so climatology features see neighbouring weeks


@dataclass
class Case:
    case_id: str
    kind: str                      # "wildfire" | "conflict"
    region: str
    bbox: list                     # [west, south, east, north]
    period_start: date
    period_end: date
    fuel_mix: dict
    sources: list = field(default_factory=lambda: ["VIIRS_SNPP_SP"])
    baseline_years: list = field(default_factory=list)   # conflict only
    grid_deg: float = 0.25
    crosscheck: dict | None = None  # optional burned-area cross-check inputs
    description: str = ""

    def __post_init__(self):
        if self.kind not in ("wildfire", "conflict"):
            raise ValueError("kind must be wildfire or conflict")
        if self.period_end < self.period_start:
            raise ValueError("period_end before period_start")
        if abs(sum(self.fuel_mix.values()) - 1.0) > 1e-9:
            raise ValueError("fuel_mix weights must sum to 1")
        if self.kind == "conflict":
            if self.period_start.year != self.period_end.year:
                raise ValueError("conflict period must sit inside one calendar year")
            if len(self.baseline_years) < 3:
                raise ValueError("conflict cases need at least 3 baseline years")

    @property
    def chain_kind(self) -> int:
        return {"wildfire": 0, "conflict": 1}[self.kind]

    @property
    def period_unix(self):
        s = datetime.combine(self.period_start, datetime.min.time(), tzinfo=timezone.utc)
        e = datetime.combine(self.period_end, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
        return int(s.timestamp()), int(e.timestamp())

    def window_for_year(self, year: int, margin: int = 0):
        s = self.period_start.replace(year=year) - timedelta(days=margin)
        e = self.period_end.replace(year=year) + timedelta(days=margin)
        return s, e

    def fetch_windows(self):
        if self.kind == "wildfire":
            return [(self.period_start, self.period_end)]
        years = sorted(set(self.baseline_years) | {self.period_start.year})
        return [self.window_for_year(y, MARGIN_DAYS) for y in years]

    def subject(self):
        return {"kind": self.kind, "region": self.region,
                "period_start": self.period_start.isoformat(), "period_end": self.period_end.isoformat()}


def _parse(d: dict) -> Case:
    d = dict(d)
    d["period_start"] = date.fromisoformat(d["period_start"])
    d["period_end"] = date.fromisoformat(d["period_end"])
    return Case(**d)


def load_cases(path: Path = CASES_FILE) -> dict[str, Case]:
    raw = json.loads(Path(path).read_text())
    return {c["case_id"]: _parse(c) for c in raw["cases"]}


def get_case(case_id: str) -> Case:
    cases = load_cases()
    if case_id not in cases:
        raise SystemExit(f"Unknown case '{case_id}'. Known: {', '.join(cases)}")
    return cases[case_id]


def case_from_report(report: dict) -> Case:
    """Rebuild the exact case definition stored inside a report (used by verify)."""
    return _parse(report["case"])


def case_to_dict(c: Case) -> dict:
    return {
        "case_id": c.case_id, "kind": c.kind, "region": c.region, "bbox": list(c.bbox),
        "period_start": c.period_start.isoformat(), "period_end": c.period_end.isoformat(),
        "fuel_mix": dict(c.fuel_mix), "sources": list(c.sources),
        "baseline_years": list(c.baseline_years), "grid_deg": c.grid_deg,
        "crosscheck": c.crosscheck, "description": c.description,
    }
