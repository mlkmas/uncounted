"""Fire radiative power -> greenhouse gas emissions, with Monte Carlo uncertainty.

  dry matter (kg) = sum(FRP, MW) x duration (s) x combustion factor (kg/MJ)
  gas (g)         = dry matter (kg) x emission factor (g/kg)
  CO2e (t)        = sum over gases of gas x GWP100 / 1e6

All uncertain inputs are sampled jointly; results are reported as the 5th, 50th and 95th
percentiles, rounded to 3 significant figures.
"""
import numpy as np
import pandas as pd

from . import params as P
from .canonical import sig, sig_int

GASES = ("CO2", "CH4", "N2O")


def filter_detections(df: pd.DataFrame) -> pd.DataFrame:
    keep = ~df["confidence"].isin(P.EXCLUDED_CONFIDENCE) & df["type"].astype(str).isin(P.KEPT_TYPES)
    return df[keep]


def sample_factors(fuel_mix: dict, n_sources: int, n: int, rng: np.random.Generator) -> dict:
    """Draw every uncertain factor n times. Order of draws is fixed for reproducibility."""
    passes = P.PASSES_PER_DAY_PER_SATELLITE * n_sources
    lo, hi = P.DURATION_SCALE_RANGE
    duration_s = (24.0 / passes) * 3600.0 * rng.uniform(lo, hi, n)
    beta = np.clip(rng.normal(P.COMBUSTION_FACTOR_KG_PER_MJ["mean"], P.COMBUSTION_FACTOR_KG_PER_MJ["sd"], n), 1e-6, None)
    ef = {g: np.zeros(n) for g in GASES}
    for fuel in sorted(fuel_mix):
        w = fuel_mix[fuel]
        for g in GASES:
            mean, sd = P.EMISSION_FACTORS_G_PER_KG[fuel][g]
            ef[g] += w * np.clip(rng.normal(mean, sd, n), 0.0, None)
    return {"duration_s": duration_s, "beta": beta, "ef": ef}


def emissions_from_frp(frp_mw_draws, factors: dict) -> dict:
    """frp_mw_draws: scalar or array (one value per draw) of summed FRP in MW."""
    dm_kg = np.asarray(frp_mw_draws, dtype=float) * factors["duration_s"] * factors["beta"]
    gas_t = {g: dm_kg * factors["ef"][g] / 1e6 for g in GASES}
    co2e_t = sum(gas_t[g] * P.GWP100[g] for g in GASES)
    return {"dry_matter_t": dm_kg / 1000.0, "gas_t": gas_t, "co2e_t": co2e_t}


def summarize(e: dict) -> dict:
    q = np.percentile(e["co2e_t"], [5, 50, 95])
    return {
        "tco2e": {"p05": sig_int(q[0]), "p50": sig_int(q[1]), "p95": sig_int(q[2])},
        "by_gas_median_t": {g: sig(float(np.median(e["gas_t"][g]))) for g in GASES},
        "dry_matter_burned_median_t": sig(float(np.median(e["dry_matter_t"]))),
    }


def burned_area_crosscheck(cc: dict, fuel_mix: dict, n: int, rng: np.random.Generator) -> dict:
    """Independent estimate from burned area (Seiler & Crutzen 1980; IPCC 2006 Eq. 2.27).

    cc = {"burned_area_ha": [low, high], "fuel_consumed_t_per_ha": [low, high], "sources": [...]}
    Uniform sampling between the given bounds.
    """
    area = rng.uniform(*cc["burned_area_ha"], n)
    fuel = rng.uniform(*cc["fuel_consumed_t_per_ha"], n)
    dm_t = area * fuel
    co2e = np.zeros(n)
    for f in sorted(fuel_mix):
        for g in GASES:
            mean, sd = P.EMISSION_FACTORS_G_PER_KG[f][g]
            co2e += fuel_mix[f] * dm_t * np.clip(rng.normal(mean, sd, n), 0, None) / 1000.0 * P.GWP100[g]
    q = np.percentile(co2e, [5, 50, 95])
    return {"method": "burned area x fuel consumed x emission factor",
            "inputs": cc,
            "tco2e": {"p05": sig_int(q[0]), "p50": sig_int(q[1]), "p95": sig_int(q[2])}}
