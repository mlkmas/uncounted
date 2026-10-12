from datetime import date

import numpy as np
import pytest

from uncounted import emissions
from uncounted import params as P
from uncounted.canonical import canonical_bytes, sha256_bytes, sha256_file, sig
from uncounted.cases import Case
from uncounted.firms import load_snapshot, write_snapshot
from uncounted.pipeline import build_report, chain_input, write_report
from uncounted.synthetic import generate


def wildfire_case():
    return Case(case_id="t-fire", kind="wildfire", region="SYNTHETIC test fire", bbox=[31.2, 36.7, 31.9, 37.2],
                period_start=date(2021, 7, 28), period_end=date(2021, 8, 12),
                fuel_mix={"extratropical_forest": 1.0}, grid_deg=0.05)


def conflict_case(cid="t-war"):
    return Case(case_id=cid, kind="conflict", region="SYNTHETIC test conflict", bbox=[32.0, 45.9, 35.3, 47.6],
                period_start=date(2022, 3, 1), period_end=date(2022, 10, 31),
                fuel_mix={"agricultural_residue": 0.6, "savanna_grassland": 0.4},
                baseline_years=[2017, 2018, 2019, 2020, 2021])


def test_canonical_json_is_order_independent():
    assert canonical_bytes({"b": 1, "a": [1, 2]}) == canonical_bytes({"a": [1, 2], "b": 1})
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})


def test_sig_rounding():
    assert sig(1234567) == 1230000
    assert sig(0.0012345) == 0.00123
    assert sig(0) == 0


def test_emission_units_by_hand():
    """1 MW for one 12 h window, beta 0.368 kg/MJ, pure CO2 EF 1569 g/kg."""
    f = {"duration_s": np.array([12 * 3600.0]), "beta": np.array([0.368]),
         "ef": {"CO2": np.array([1569.0]), "CH4": np.array([0.0]), "N2O": np.array([0.0])}}
    e = emissions.emissions_from_frp(1.0, f)
    dm_kg = 1.0 * 12 * 3600 * 0.368            # MW * s = MJ ; MJ * kg/MJ = kg
    assert e["dry_matter_t"][0] == pytest.approx(dm_kg / 1000)
    assert e["co2e_t"][0] == pytest.approx(dm_kg * 1569 / 1e6)


def test_gwp_is_applied():
    f = {"duration_s": np.array([1e6]), "beta": np.array([1.0]),
         "ef": {"CO2": np.array([0.0]), "CH4": np.array([1.0]), "N2O": np.array([0.0])}}
    e = emissions.emissions_from_frp(1.0, f)
    assert e["co2e_t"][0] == pytest.approx(1e6 * 1.0 / 1e6 * P.GWP100["CH4"])


def test_filters_drop_low_confidence_and_static_sources():
    import pandas as pd
    df = pd.DataFrame({"confidence": ["n", "l", "h", "n"], "type": ["0", "0", "2", ""]})
    assert list(emissions.filter_detections(df).index) == [0, 3]


def test_snapshot_hash_is_stable():
    c = wildfire_case()
    df = generate(c)
    p1, h1 = write_snapshot(df, "a")
    p2, h2 = write_snapshot(df.sample(frac=1, random_state=1), "b")   # shuffled rows
    assert h1 == h2 == sha256_file(p1)


def test_wildfire_report_reproducible_and_consistent():
    c = wildfire_case()
    snap, data_hash = write_snapshot(generate(c), c.case_id)
    r1 = build_report(c, snap)
    r2 = build_report(c, snap)
    assert canonical_bytes(r1) == canonical_bytes(r2)
    t = r1["result"]["tco2e"]
    assert 0 < t["p05"] <= t["p50"] <= t["p95"]
    path, h = write_report(r1)
    ci = chain_input(path, c)
    assert ci["reportHash"] == h == sha256_bytes(path.read_bytes())
    assert ci["dataHash"] == data_hash
    assert ci["kind"] == 0 and ci["periodEnd"] > ci["periodStart"]


def test_conflict_attribution_recovers_injected_fires():
    """Ground truth: synthetic background + injected front-line fires with a known FRP total."""
    c = conflict_case()
    with_war = generate(c)
    without = generate(c, frontline=False)
    def period_frp(df):
        snap, _ = write_snapshot(df, "tmp")
        d = emissions.filter_detections(load_snapshot(snap))
        m = (d["acq_date"] >= c.period_start) & (d["acq_date"] <= c.period_end)
        return d.loc[m, "frp"].sum()
    truth = period_frp(with_war) - period_frp(without)
    snap, _ = write_snapshot(with_war, c.case_id)
    r = build_report(c, snap)
    ex = r["result"]["excess_frp_mw"]
    # conservative by design: recovers most of the injected fire, never invents much more
    assert 0.6 * truth <= ex["p50"] <= 1.15 * truth, (truth, ex)
    assert ex["p05"] <= ex["p50"] <= ex["p95"]
    # the strongest hotspot sits on the injected front line (diagonal through the box)
    h = r["hotspots"][0]
    w, s, e, n = c.bbox
    t_lat, t_lon = (h["lat"] - s) / (n - s), (h["lon"] - w) / (e - w)
    assert abs((t_lat - 0.2) / 0.6 - (t_lon - 0.15) / 0.5) < 0.35, h


def test_peacetime_year_shows_little_excess():
    c = conflict_case("t-peace")
    snap, _ = write_snapshot(generate(c, frontline=False), c.case_id)
    r = build_report(c, snap)
    observed = r["attribution"]["observed_frp_mw"]
    assert r["result"]["excess_frp_mw"]["p50"] < 0.10 * observed, r["result"]
    assert len(r["attribution"]["peacetime_check"]) == 5


def test_verify_tolerance_rules():
    from copy import deepcopy
    from uncounted.verify import compare_reports
    c = wildfire_case()
    snap, _ = write_snapshot(generate(c), "t-verify")
    rep = build_report(c, snap)
    assert compare_reports(rep, deepcopy(rep)) == []
    small = deepcopy(rep); small["result"]["tco2e"]["p50"] = int(rep["result"]["tco2e"]["p50"] * 1.02)
    assert compare_reports(rep, small) == []                       # 2 % drift: same result
    big = deepcopy(rep); big["result"]["tco2e"]["p50"] = int(rep["result"]["tco2e"]["p50"] * 1.2)
    assert any("tco2e.p50" in d for d in compare_reports(rep, big))  # 20 %: not reproduced
    changed = deepcopy(rep); changed["method"]["monte_carlo"]["seed"] += 1
    assert any("seed" in d for d in compare_reports(rep, changed))   # inputs must be identical


def test_burned_area_crosscheck_units():
    c = wildfire_case()
    c.crosscheck = {"burned_area_ha": [1000, 1000], "fuel_consumed_t_per_ha": [20, 20]}
    snap, _ = write_snapshot(generate(c), "t-cc")
    cc = build_report(c, snap)["crosscheck"]
    # 20,000 t dry matter x (1569 + 27*4.7 + 273*0.26) g/kg = about 36,300 t CO2e
    assert 30000 < cc["tco2e"]["p50"] < 43000, cc
