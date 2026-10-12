"""Conflict attribution: how much fire activity is above what a peacetime year would show?

Same idea as excess mortality. A gradient-boosted model learns, from pre-conflict years,
how much fire radiative power (FRP) each grid cell normally produces in each week of the
year (agricultural burning seasons, recurring wildfires). For the conflict period:

    excess FRP = observed FRP - expected FRP

The model is checked with leave-one-year-out validation on the peacetime years: for each
held-out year we compare observed with expected over the same calendar window. The spread
of those ratios becomes the uncertainty of "expected" in the Monte Carlo.

Only fire emissions are attributed. Military fuel use, munitions and reconstruction are
not included, so the result is a lower bound on the climate cost of a conflict.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .canonical import sig

MODEL_PARAMS = dict(loss="poisson", max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                    min_samples_leaf=20, l2_regularization=1.0, early_stopping=False, random_state=0)
FEATURES = ["lat", "lon", "week_sin", "week_cos", "clim_cell", "clim_cell_all", "clim_region"]
SMOOTH_WEEKS = 2
MIN_LOG_RATIO_SD = 0.10


def week_of(d: date) -> int:
    return (d.timetuple().tm_yday - 1) // 7


class Grid:
    """FRP summed per (year, week, cell) as a dense array F[year, week, i, j]."""

    def __init__(self, df: pd.DataFrame, case, years):
        self.case, self.years = case, list(years)
        w, s, e, n = case.bbox
        g = case.grid_deg
        self.ni = max(1, int(np.ceil((n - s) / g)))
        self.nj = max(1, int(np.ceil((e - w) / g)))
        self.lat = s + (np.arange(self.ni) + 0.5) * g
        self.lon = w + (np.arange(self.nj) + 0.5) * g
        windows = {y: case.window_for_year(y, 21) for y in self.years}
        self.w0 = min(week_of(a) for a, _ in windows.values())
        self.w1 = max(week_of(b) for _, b in windows.values())
        self.nw = self.w1 - self.w0 + 1
        self.F = np.zeros((len(self.years), self.nw, self.ni, self.nj))

        d = df.copy()
        d["y"] = [x.year for x in d["acq_date"]]
        d = d[d["y"].isin(self.years)]
        yi = d["y"].map({y: k for k, y in enumerate(self.years)}).to_numpy()
        wi = np.array([week_of(x) for x in d["acq_date"]], dtype=int) - self.w0
        ii = np.floor((d["latitude"].to_numpy() - s) / g).astype(int)
        jj = np.floor((d["longitude"].to_numpy() - w) / g).astype(int)
        ok = (wi >= 0) & (wi < self.nw) & (ii >= 0) & (ii < self.ni) & (jj >= 0) & (jj < self.nj)
        np.add.at(self.F, (yi[ok], wi[ok], ii[ok], jj[ok]), d["frp"].to_numpy()[ok])

        # smoothed over +/- SMOOTH_WEEKS for climatology features
        self.Fs = np.zeros_like(self.F)
        for k in range(self.nw):
            a, b = max(0, k - SMOOTH_WEEKS), min(self.nw, k + SMOOTH_WEEKS + 1)
            self.Fs[:, k] = self.F[:, a:b].mean(axis=1)

    def yidx(self, y):
        return self.years.index(y)

    def period_weights(self, year: int) -> np.ndarray:
        """Fraction of each week's 7 days that falls inside the case period in this year."""
        s, e = self.case.window_for_year(year)
        wts = np.zeros(self.nw)
        d = s
        while d <= e:
            k = week_of(d) - self.w0
            if 0 <= k < self.nw:
                wts[k] += 1 / 7
            d += timedelta(days=1)
        return wts

    def rows(self, year: int, clim_years) -> pd.DataFrame:
        """Feature rows for every (week, cell) of `year`, climatology from `clim_years` only."""
        clim_years = [c for c in clim_years if c != year]
        ci = [self.yidx(c) for c in clim_years]
        clim_cell = self.Fs[ci].mean(axis=0)                     # (nw, ni, nj)
        clim_all = self.F[ci].mean(axis=(0, 1))                  # (ni, nj)
        clim_region = self.Fs[ci].mean(axis=(0, 2, 3))           # (nw,)
        K, I, J = np.meshgrid(np.arange(self.nw), np.arange(self.ni), np.arange(self.nj), indexing="ij")
        weeks = K + self.w0
        out = pd.DataFrame({
            "k": K.ravel(), "i": I.ravel(), "j": J.ravel(),
            "lat": self.lat[I.ravel()], "lon": self.lon[J.ravel()],
            "week_sin": np.sin(2 * np.pi * weeks.ravel() / 52), "week_cos": np.cos(2 * np.pi * weeks.ravel() / 52),
            "clim_cell": clim_cell.ravel(), "clim_cell_all": clim_all[I.ravel(), J.ravel()],
            "clim_region": clim_region[K.ravel()],
            "y": self.F[self.yidx(year)].ravel(),
        })
        return out


def _fit(grid: Grid, train_years):
    X = pd.concat([grid.rows(y, train_years) for y in train_years], ignore_index=True)
    m = HistGradientBoostingRegressor(**MODEL_PARAMS)
    m.fit(X[FEATURES], X["y"])
    return m


def _expected(grid: Grid, model, year, clim_years):
    R = grid.rows(year, clim_years)
    pred = np.clip(model.predict(R[FEATURES]), 0, None)
    w = grid.period_weights(year)[R["k"].to_numpy()]
    return R, pred, w


def observed_in_period(df: pd.DataFrame, case, year: int) -> float:
    s, e = case.window_for_year(year)
    m = (df["acq_date"] >= s) & (df["acq_date"] <= e)
    return float(df.loc[m, "frp"].sum())


def run(df: pd.DataFrame, case) -> dict:
    """df: filtered detections. Returns everything the Monte Carlo and the report need."""
    target = case.period_start.year
    base = sorted(case.baseline_years)
    grid = Grid(df, case, base + [target])

    # leave-one-year-out validation on peacetime years
    validation = []
    for h in base:
        train = [y for y in base if y != h]
        model = _fit(grid, train)
        _, pred, w = _expected(grid, model, h, train)
        exp_h = float((pred * w).sum())
        obs_h = observed_in_period(df, case, h)
        validation.append({"year": h, "observed_frp_mw": sig(obs_h), "expected_frp_mw": sig(exp_h),
                           "ratio": sig(obs_h / exp_h) if exp_h > 0 else None})

    ratios = [v["ratio"] for v in validation if v["ratio"]]
    if len(ratios) < 2:
        raise RuntimeError("baseline years have too little fire activity to calibrate the model")
    logr = np.log(ratios)
    mu, sd = float(np.mean(logr)), max(float(np.std(logr, ddof=1)), MIN_LOG_RATIO_SD)

    model = _fit(grid, base)
    R, pred, w = _expected(grid, model, target, base)
    expected_raw = float((pred * w).sum())
    observed = observed_in_period(df, case, target)
    expected_central = expected_raw * np.exp(mu)

    # per-cell excess for the map
    obs_cell = grid.F[grid.yidx(target)].ravel() * w
    exp_cell = pred * w * np.exp(mu)
    R = R.assign(excess=obs_cell - exp_cell)
    cells = R.groupby(["i", "j"], as_index=False)["excess"].sum()
    cells = cells[cells["excess"] > 0].sort_values(["excess", "i", "j"], ascending=[False, True, True]).head(40)
    hotspots = [{"lat": round(float(grid.lat[r.i]), 4), "lon": round(float(grid.lon[r.j]), 4),
                 "excess_frp_mw": sig(float(r.excess))} for r in cells.itertuples()]

    return {
        "observed_frp_mw": observed,
        "expected_frp_mw_raw": expected_raw,
        "log_ratio_mu": mu,
        "log_ratio_sd": sd,
        "summary": {
            "model": "HistGradientBoostingRegressor (Poisson loss), cell-week FRP",
            "model_params": MODEL_PARAMS,
            "features": FEATURES,
            "grid_deg": case.grid_deg,
            "baseline_years": base,
            "peacetime_validation": validation,
            "calibration_log_ratio": {"mean": sig(mu), "sd": sig(sd)},
            "observed_frp_mw": sig(observed),
            "expected_frp_mw_central": sig(expected_central),
            "excess_share_central": sig(max(0.0, 1 - expected_central / observed)) if observed > 0 else 0.0,
        },
        "hotspots": hotspots,
    }
