"""Conflict attribution: which fires don't look like any peacetime fire?

Method (AI pattern attribution, conservative):
  1. Take every satellite fire detection in the conflict period, and every detection in
     the same calendar window of the peacetime baseline years.
  2. Train a gradient-boosted classifier to tell conflict-year fires from peacetime fires,
     using where (lat, lon), when (day of year), day or night, and intensity (FRP).
     Training is cross-fitted on spatial blocks: a fire is always scored by a model that
     never saw its own block (neither conflict-year nor peacetime fires from that block).
  3. The classifier's odds give a density ratio: how much more likely a fire like this is
     in the conflict year than in peacetime. The share of each fire's FRP that peacetime
     patterns cannot explain is max(0, 1 - 1/odds).
  4. Noise floor: the exact same procedure is run on each peacetime year, treating it as
     if it were the conflict year. Whatever it flags there is false excess and is
     subtracted.
Each step uses 5 leave-one-year-out reference sets, so the result comes with a spread.

This measures fires that look different from peacetime fires. Extra burning in places and
seasons where fires were already common is not counted, so the result is a lower bound.

A simpler cross-check (per-cell envelope) is reported alongside: fire power in each grid
cell and month above the highest value that cell showed in the reference years.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .canonical import sig

CLASSIFIER_PARAMS = dict(max_iter=200, learning_rate=0.05, min_samples_leaf=40,
                         l2_regularization=1.0, early_stopping=False, random_state=0)
FEATURES = ["latitude", "longitude", "doy", "night", "log_frp"]
CROSS_FIT_FOLDS = 5
BLOCK_DEG = 0.2
P_CLIP = (1e-6, 0.999)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["year"] = [x.year for x in d["acq_date"]]
    d["month"] = [x.month for x in d["acq_date"]]
    d["doy"] = [x.timetuple().tm_yday for x in d["acq_date"]]
    d["night"] = (d["daynight"] == "N").astype(int)
    d["log_frp"] = np.log1p(d["frp"])
    return d


def _in_period(d: pd.DataFrame, case, year: int) -> pd.DataFrame:
    s, e = case.window_for_year(year)
    return d[(d["year"] == year) & (d["acq_date"] >= s) & (d["acq_date"] <= e)]


def _blocks(t: pd.DataFrame) -> np.ndarray:
    i = np.floor(t["latitude"].to_numpy() / BLOCK_DEG).astype(np.int64)
    j = np.floor(t["longitude"].to_numpy() / BLOCK_DEG).astype(np.int64)
    return (i * 1000 + j) % CROSS_FIT_FOLDS


def unexplained_share(target: pd.DataFrame, reference: pd.DataFrame) -> np.ndarray:
    """For each target fire, the share of its FRP that the reference (peacetime) pattern can't explain.

    Cross-fitting holds out one set of spatial blocks at a time, removing BOTH the target and
    the reference fires in those blocks from training. Fires in a held-out block are scored
    from the surrounding pattern only, so the model can't memorise local clusters, and it
    isn't biased by seeing only one class inside the block.
    """
    if len(target) == 0 or len(reference) == 0:
        return np.zeros(len(target))
    tb, rb = _blocks(target), _blocks(reference)
    p = np.zeros(len(target))
    for k in range(CROSS_FIT_FOLDS):
        test = tb == k
        if not test.any():
            continue
        tr, ref = target[~test], reference[rb != k]
        if len(tr) == 0 or len(ref) == 0:
            continue
        X = np.vstack([tr[FEATURES].to_numpy(), ref[FEATURES].to_numpy()])
        y = np.r_[np.ones(len(tr)), np.zeros(len(ref))]
        w = np.r_[np.ones(len(tr)), np.full(len(ref), len(tr) / len(ref))]   # balanced classes
        m = HistGradientBoostingClassifier(**CLASSIFIER_PARAMS)
        m.fit(X, y, sample_weight=w)
        p[test] = m.predict_proba(target[test][FEATURES].to_numpy())[:, 1]
    p = np.clip(p, *P_CLIP)
    return np.clip(1.0 - (1.0 - p) / p, 0.0, 1.0)


def _envelope(d: pd.DataFrame, case, base, target_year) -> dict:
    """Per grid cell and month: FRP above the cell's highest value in the reference years."""
    w, s = case.bbox[0], case.bbox[1]
    g = case.grid_deg
    rows = []
    for y in base + [target_year]:
        t = _in_period(d, case, y)
        rows.append(pd.DataFrame({"y": y, "i": np.floor((t["latitude"] - s) / g).astype(int),
                                  "j": np.floor((t["longitude"] - w) / g).astype(int),
                                  "m": t["month"], "frp": t["frp"]}))
    a = pd.concat(rows).pivot_table(index=["i", "j", "m"], columns="y", values="frp", aggfunc="sum", fill_value=0.0)
    for y in base + [target_year]:
        if y not in a.columns:
            a[y] = 0.0

    def excess(year, refs):
        return float(np.clip(a[year] - a[refs].max(axis=1), 0, None).sum())

    war = [excess(target_year, [b for b in base if b != h]) for h in base]
    false = [excess(h, [b for b in base if b != h]) for h in base]
    return {"method": "per-cell envelope (grid cell x month above the reference-year maximum)",
            "conflict_excess_frp_mw": sig(float(np.mean(war))),
            "peacetime_false_excess_frp_mw": [sig(f) for f in false],
            "net_excess_frp_mw": sig(float(np.mean(war) - np.mean(false)))}


def run(df: pd.DataFrame, case) -> dict:
    """df: filtered detections. Returns the excess spread for the Monte Carlo plus report sections."""
    target_year = case.period_start.year
    base = sorted(case.baseline_years)
    d = _prepare(df)
    by_year = {y: _in_period(d, case, y) for y in base + [target_year]}
    T = by_year[target_year]

    war, false, share = [], [], np.zeros(len(T))
    for h in base:
        refs = [b for b in base if b != h]
        ref_df = pd.concat([by_year[r] for r in refs])
        w = unexplained_share(T, ref_df)
        war.append(float((T["frp"].to_numpy() * w).sum()))
        share += w / len(base)
        f = unexplained_share(by_year[h], ref_df)
        false.append(float((by_year[h]["frp"].to_numpy() * f).sum()))

    # rounded before use so tiny cross-platform differences don't move the results
    war = [sig(x) for x in war]
    false = [sig(x) for x in false]

    ex = T.assign(excess=T["frp"].to_numpy() * share)
    g = case.grid_deg
    w0, s0 = case.bbox[0], case.bbox[1]
    cells = (ex.assign(i=np.floor((ex["latitude"] - s0) / g).astype(int), j=np.floor((ex["longitude"] - w0) / g).astype(int))
               .groupby(["i", "j"], as_index=False)["excess"].sum())
    cells = cells[cells["excess"] > 0].sort_values(["excess", "i", "j"], ascending=[False, True, True]).head(40)
    hotspots = [{"lat": round(s0 + (r.i + 0.5) * g, 4), "lon": round(w0 + (r.j + 0.5) * g, 4),
                 "excess_frp_mw": sig(float(r.excess))} for r in cells.itertuples()]
    by_month = [{"month": int(m), "observed_frp_mw": sig(float(v.frp.sum())), "excess_frp_mw": sig(float(v.excess.sum()))}
                for m, v in ex.groupby("month")]

    observed = float(T["frp"].sum())
    return {
        "conflict_excess": war,
        "peacetime_false_excess": false,
        "summary": {
            "method": "AI pattern attribution: cross-fitted gradient-boosted classifier, conflict year vs peacetime years",
            "classifier_params": CLASSIFIER_PARAMS,
            "features": FEATURES,
            "cross_fit": {"folds": CROSS_FIT_FOLDS, "block_deg": BLOCK_DEG},
            "baseline_years": base,
            "observed_frp_mw": sig(observed),
            "conflict_excess_by_reference_set": [{"left_out": h, "excess_frp_mw": v} for h, v in zip(base, war)],
            "peacetime_check": [{"year": h, "observed_frp_mw": sig(float(by_year[h]["frp"].sum())), "false_excess_frp_mw": v}
                                for h, v in zip(base, false)],
            "net_excess_frp_mw_central": sig(max(0.0, float(np.mean(war) - np.mean(false)))),
            "excess_by_month": by_month,
            "envelope_crosscheck": _envelope(d, case, base, target_year),
        },
        "hotspots": hotspots,
    }
