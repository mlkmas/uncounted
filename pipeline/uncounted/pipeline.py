"""Turn a case + data snapshot into a canonical, hashable report."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import attribution, emissions
from . import params as P
from .canonical import REPORT_DIR, canonical_bytes, rel, sha256_bytes, sha256_file, sig
from .cases import Case, case_to_dict
from .firms import load_snapshot

SCHEMA = "uncounted.report/1"
MC_DRAWS = 20000
MC_SEED = 20261025


def _wildfire(case: Case, df: pd.DataFrame, rng) -> tuple[dict, dict, list]:
    s, e = case.period_start, case.period_end
    d = df[(df["acq_date"] >= s) & (df["acq_date"] <= e)]
    frp = float(d["frp"].sum())
    factors = emissions.sample_factors(case.fuel_mix, len(case.sources), MC_DRAWS, rng)
    result = emissions.summarize(emissions.emissions_from_frp(frp, factors))
    g = case.grid_deg
    w, so = case.bbox[0], case.bbox[1]
    cells = (d.assign(i=np.floor((d["latitude"] - so) / g).astype(int), j=np.floor((d["longitude"] - w) / g).astype(int))
              .groupby(["i", "j"], as_index=False)["frp"].sum()
              .sort_values(["frp", "i", "j"], ascending=[False, True, True]).head(40))
    hotspots = [{"lat": round(so + (r.i + 0.5) * g, 4), "lon": round(w + (r.j + 0.5) * g, 4),
                 "frp_mw": sig(float(r.frp))} for r in cells.itertuples()]
    inputs = {"detections_in_period": int(len(d)), "frp_sum_mw": sig(frp)}
    return result, inputs, hotspots


def _conflict(case: Case, df: pd.DataFrame, rng) -> tuple[dict, dict, list, dict]:
    a = attribution.run(df, case)
    factors = emissions.sample_factors(case.fuel_mix, len(case.sources), MC_DRAWS, rng)
    war = np.array(a["conflict_excess"])
    false = np.array(a["peacetime_false_excess"])
    i = rng.integers(0, len(war), MC_DRAWS)
    j = rng.integers(0, len(false), MC_DRAWS)
    excess = np.clip(war[i] - false[j], 0, None)
    result = emissions.summarize(emissions.emissions_from_frp(excess, factors))
    result["excess_frp_mw"] = {k: sig(float(v)) for k, v in zip(("p05", "p50", "p95"), np.percentile(excess, [5, 50, 95]))}
    s, e = case.period_start, case.period_end
    n = int(((df["acq_date"] >= s) & (df["acq_date"] <= e)).sum())
    inputs = {"detections_in_period": n, "frp_sum_mw": a["summary"]["observed_frp_mw"]}
    return result, inputs, a["hotspots"], a["summary"]


def environment() -> dict:
    """Library versions that produced the report. Recorded, so verifiers can match them."""
    import platform
    import sklearn
    return {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "scikit-learn": sklearn.__version__}


def build_report(case: Case, snapshot_path: Path) -> dict:
    data_sha = sha256_file(snapshot_path)
    raw = load_snapshot(snapshot_path)
    df = emissions.filter_detections(raw)
    rng = np.random.default_rng(MC_SEED)

    attribution_summary = None
    if case.kind == "wildfire":
        result, inputs, hotspots = _wildfire(case, df, rng)
    else:
        result, inputs, hotspots, attribution_summary = _conflict(case, df, rng)

    crosscheck = None
    if case.crosscheck:
        crosscheck = emissions.burned_area_crosscheck(case.crosscheck, case.fuel_mix, MC_DRAWS,
                                                      np.random.default_rng(MC_SEED + 1))

    report = {
        "schema": SCHEMA,
        "case": case_to_dict(case),
        "subject": case.subject(),
        "data": {
            "provider": "NASA FIRMS active fire detections",
            "products": case.sources,
            "bbox_wsen": case.bbox,
            "snapshot_file": rel(snapshot_path),
            "snapshot_sha256": data_sha,
            "rows_in_snapshot": int(len(raw)),
            "rows_after_filters": int(len(df)),
            **inputs,
        },
        "method": {
            "version": P.METHOD_VERSION,
            "parameters": P.as_dict(),
            "monte_carlo": {"draws": MC_DRAWS, "seed": MC_SEED},
        },
        "environment": environment(),
        "result": result,
        "hotspots": hotspots,
        "notes": _notes(case),
    }
    if attribution_summary:
        report["attribution"] = attribution_summary
    if crosscheck:
        report["crosscheck"] = crosscheck
    return report


def _notes(case: Case) -> list:
    n = ["Estimates are ranges (5th to 95th percentile), not exact figures.",
         "Fire radiative power integration uses a simple duration model; see method.parameters."]
    if case.kind == "conflict":
        n.append("Counts only fires whose pattern (place, season, time of day, intensity) is unlike peacetime fires. "
                 "Extra burning that looks like normal burning is not counted.")
        n.append("Military fuel use, munitions, infrastructure damage and reconstruction are not included, "
                 "so this is a lower bound on the climate cost of the conflict.")
        n.append("Vegetation emission factors are used as a proxy for all fuels burned.")
    if "SYNTHETIC" in case.region:
        n.insert(0, "SYNTHETIC TEST DATA. Not a real-world estimate.")
    return n


def write_report(report: dict, out: Path | None = None) -> tuple[Path, str]:
    data = canonical_bytes(report)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = out or REPORT_DIR / f"{report['case']['case_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out, sha256_bytes(data)


def chain_input(report_path: Path, case: Case) -> dict:
    """The exact values the smart contract receives for this report."""
    report = json.loads(Path(report_path).read_bytes())
    start, end = case.period_unix
    t = report["result"]["tco2e"]
    return {
        "kind": case.chain_kind,
        "region": case.region,
        "periodStart": start,
        "periodEnd": end,
        "tco2eLow": t["p05"],
        "tco2eCentral": t["p50"],
        "tco2eHigh": t["p95"],
        "reportHash": sha256_file(report_path),
        "dataHash": report["data"]["snapshot_sha256"],
        "methodVersion": report["method"]["version"],
        "reportURI": rel(report_path),
    }
