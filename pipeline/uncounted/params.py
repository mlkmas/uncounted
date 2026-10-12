"""Physical parameters used by the estimators.

Every number here ends up inside the hashed report, so changing a value changes the
report hash. Values marked VERIFY should be checked against the cited source before
any public submission.
"""

METHOD_VERSION = "uncounted-frp/0.2.0"

# Fire radiative energy (MJ) -> dry matter burned (kg).
# Wooster et al. (2005), JGR Atmospheres, 110, D24311: 0.368 +/- 0.015 kg/MJ.
COMBUSTION_FACTOR_KG_PER_MJ = {"mean": 0.368, "sd": 0.015,
                               "source": "Wooster et al. 2005, JGR 110, D24311"}

# Emission factors, g of gas per kg of dry matter burned (mean, sd).
# Means: IPCC 2006 Guidelines Vol.4 Ch.2 Table 2.5 (checked). SDs: Andreae & Merlet (2001), VERIFY.
EMISSION_FACTORS_G_PER_KG = {
    "extratropical_forest": {"CO2": (1569, 131), "CH4": (4.7, 1.9), "N2O": (0.26, 0.07)},
    "savanna_grassland":    {"CO2": (1613, 95),  "CH4": (2.3, 0.9), "N2O": (0.21, 0.10)},
    "agricultural_residue": {"CO2": (1515, 177), "CH4": (2.7, 0.9), "N2O": (0.07, 0.03)},
    "tropical_forest":      {"CO2": (1580, 90),  "CH4": (6.8, 2.0), "N2O": (0.20, 0.10)},
}
EMISSION_FACTORS_SOURCE = "IPCC 2006 GL Vol.4 Ch.2 Table 2.5 (means); Andreae & Merlet 2001 (SDs)"

# 100-year global warming potentials, IPCC AR6 WG1 Ch.7 Table 7.15 (non-fossil CH4). VERIFY.
GWP100 = {"CO2": 1.0, "CH4": 27.0, "N2O": 273.0}
GWP_SOURCE = "IPCC AR6 WG1 Table 7.15, GWP100, non-fossil CH4 (VERIFY)"

# Temporal integration of instantaneous FRP into energy.
# Each VIIRS satellite views a mid-latitude point about twice a day (day + night pass),
# so each detection is taken to represent 24h / passes_per_day of burning, scaled by an
# uncertain factor. This is the dominant uncertainty of the FRP method; the burned-area
# cross-check exists to calibrate it.
PASSES_PER_DAY_PER_SATELLITE = 2
DURATION_SCALE_RANGE = (0.5, 1.5)   # uniform

# Detection filters (FIRMS VIIRS conventions).
EXCLUDED_CONFIDENCE = ["l"]          # drop low-confidence detections
KEPT_TYPES = ["0", ""]               # 0 = presumed vegetation fire; "" when product has no type column


def as_dict():
    """Parameters as they are written into the report (part of the hash)."""
    return {
        "combustion_factor_kg_per_mj": COMBUSTION_FACTOR_KG_PER_MJ,
        "emission_factors_g_per_kg": {k: {g: list(v) for g, v in d.items()}
                                      for k, d in EMISSION_FACTORS_G_PER_KG.items()},
        "emission_factors_source": EMISSION_FACTORS_SOURCE,
        "gwp100": GWP100,
        "gwp_source": GWP_SOURCE,
        "passes_per_day_per_satellite": PASSES_PER_DAY_PER_SATELLITE,
        "duration_scale_range": list(DURATION_SCALE_RANGE),
        "excluded_confidence": EXCLUDED_CONFIDENCE,
        "kept_types": KEPT_TYPES,
    }
