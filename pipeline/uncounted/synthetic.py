"""Synthetic FIRMS-like data for tests and offline smoke runs.

Never used for real estimates. Synthetic cases get case_id "synthetic-..." and a region
starting with "SYNTHETIC", and every report built from them says so in its notes.
"""
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd

from .cases import Case


def synthetic_case(case: Case) -> Case:
    return replace(case, case_id=f"synthetic-{case.case_id}", region=f"SYNTHETIC {case.region}", crosscheck=None)


def _row(rng, d, lat, lon, frp):
    return {"latitude": lat, "longitude": lon, "acq_date": d.isoformat(),
            "acq_time": f"{rng.choice([1, 11, 13, 23]):02d}{rng.integers(0, 60):02d}",
            "satellite": "N", "confidence": rng.choice(["n", "n", "h", "l"]),
            "frp": frp, "daynight": "D", "type": "0", "source": "VIIRS_SNPP_SP"}


def generate(case: Case, seed: int = 7, frontline: bool = True) -> pd.DataFrame:
    """frontline=False gives the same background without the injected conflict fires (ground truth for tests)."""
    rng = np.random.default_rng(seed)
    rng_front = np.random.default_rng(seed + 1000)
    w, s, e, n = case.bbox
    rows = []
    if case.kind == "wildfire":
        days = (case.period_end - case.period_start).days + 1
        cx, cy = w + 0.3 * (e - w), s + 0.5 * (n - s)
        for k in range(days):
            d = case.period_start + timedelta(days=k)
            intensity = np.exp(-((k - days * 0.3) ** 2) / (2 * (days * 0.25) ** 2))
            for _ in range(int(400 * intensity) + 2):
                lat = np.clip(cy + rng.normal(0, 0.05), s, n)
                lon = np.clip(cx + 0.02 * k + rng.normal(0, 0.06), w, e)
                rows.append(_row(rng, d, lat, lon, float(rng.lognormal(2.7, 1.0))))
        return pd.DataFrame(rows)

    # conflict: seasonal agricultural burning every year, plus front-line fires in the target year
    target = case.period_start.year
    gi, gj = np.meshgrid(np.linspace(s, n, 8), np.linspace(w, e, 12), indexing="ij")
    base_rate = rng.gamma(1.5, 0.8, gi.shape)
    for y in sorted(set(case.baseline_years) | {target}):
        a, b = case.window_for_year(y, 21)
        d = a
        while d <= b:
            doy = d.timetuple().tm_yday
            season = 0.3 + 1.5 * np.exp(-((doy - 205) ** 2) / (2 * 20 ** 2))   # harvest burning peak
            year_noise = 1 + 0.15 * np.sin(y * 1.7)
            counts = rng.poisson(base_rate * season * year_noise * 0.4)
            for (ii, jj), c in np.ndenumerate(counts):
                for _ in range(c):
                    rows.append(_row(rng, d, gi[ii, jj] + rng.uniform(0, (n - s) / 8),
                                     gj[ii, jj] + rng.uniform(0, (e - w) / 12), float(rng.lognormal(1.6, 0.8))))
            if frontline and y == target and case.period_start <= d <= case.period_end:
                fr = rng_front
                for _ in range(fr.poisson(14)):
                    t = fr.uniform(0, 1)
                    lat = s + (n - s) * (0.2 + 0.6 * t) + fr.normal(0, 0.05)
                    lon = w + (e - w) * (0.15 + 0.5 * t) + fr.normal(0, 0.05)
                    rows.append(_row(fr, d, float(np.clip(lat, s, n - 1e-6)), float(np.clip(lon, w, e - 1e-6)),
                                     float(fr.lognormal(2.2, 1.0))))
            d += timedelta(days=1)
    return pd.DataFrame(rows)
