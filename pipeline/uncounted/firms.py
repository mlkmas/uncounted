"""NASA FIRMS active-fire data: download, snapshot, load.

API: https://firms.modaps.eosdis.nasa.gov/api/area/
  /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE<=5}/{YYYY-MM-DD}
A free MAP_KEY is available at https://firms.modaps.eosdis.nasa.gov/api/map_key/
Limit: 5000 transactions per 10 minutes.
"""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .canonical import RAW_DIR, SNAPSHOT_DIR, sha256_bytes

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
MAX_DAYS = 5
SNAPSHOT_COLUMNS = ["source", "latitude", "longitude", "acq_date", "acq_time",
                    "satellite", "confidence", "frp", "daynight", "type"]


def daterange_chunks(start: date, end: date, step: int = MAX_DAYS):
    d = start
    while d <= end:
        n = min(step, (end - d).days + 1)
        yield d, n
        d += timedelta(days=n)


def fetch_window(map_key: str, source: str, bbox, start: date, end: date, pause: float = 0.25) -> pd.DataFrame:
    """Download one date window, caching each 5-day chunk so interrupted runs resume."""
    area = ",".join(f"{v:g}" for v in bbox)
    cache = RAW_DIR / source / area.replace(",", "_")
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for d, n in daterange_chunks(start, end):
        f = cache / f"{d.isoformat()}_{n}.csv"
        if not f.exists():
            url = f"{API}/{map_key}/{source}/{area}/{n}/{d.isoformat()}"
            for attempt in range(4):
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(5 * (attempt + 1))
            r.raise_for_status()
            text = r.text
            if not text.startswith("latitude"):
                raise RuntimeError(f"FIRMS returned an error for {d}: {text[:200]}")
            f.write_text(text)
            time.sleep(pause)
        df = pd.read_csv(f, dtype=str)
        if len(df):
            df["source"] = source
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the columns we use, in fixed formats and a fixed order, so the snapshot hash is stable."""
    out = pd.DataFrame()
    for c in SNAPSHOT_COLUMNS:
        out[c] = df[c].astype(str) if c in df.columns else ""
    out["latitude"] = out["latitude"].astype(float).map(lambda v: f"{v:.5f}")
    out["longitude"] = out["longitude"].astype(float).map(lambda v: f"{v:.5f}")
    out["frp"] = out["frp"].astype(float).map(lambda v: f"{v:.2f}")
    out["acq_time"] = out["acq_time"].astype(str).str.zfill(4)
    out["confidence"] = out["confidence"].str.lower().str.strip()
    out["type"] = out["type"].replace({"nan": ""})
    out = out.drop_duplicates()
    return out.sort_values(["acq_date", "acq_time", "latitude", "longitude", "source", "satellite"]).reset_index(drop=True)


def write_snapshot(df: pd.DataFrame, case_id: str) -> tuple[Path, str]:
    """Write the normalized data and return (path, sha256). The hash goes on chain as dataHash."""
    data = normalize(df).to_csv(index=False, lineterminator="\n").encode("utf-8")
    digest = sha256_bytes(data)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{case_id}__{digest[2:14]}.csv"
    path.write_bytes(data)
    return path, digest


def load_snapshot(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    df["frp"] = df["frp"].astype(float)
    df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.date
    return df


def fetch_case(case, map_key: str) -> tuple[Path, str]:
    frames = []
    for source in case.sources:
        for start, end in case.fetch_windows():
            print(f"  {source} {start} .. {end}")
            frames.append(fetch_window(map_key, source, case.bbox, start, end))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    return write_snapshot(df, case.case_id)
