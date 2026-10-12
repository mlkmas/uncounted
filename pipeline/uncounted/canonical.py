"""Canonical serialization and hashing.

A report is stored on disk as its canonical JSON bytes. The on-chain reportHash is the
SHA-256 of exactly those bytes, so anyone (Python, a browser, a shell) can check a file
against the chain without re-serializing it.
"""
import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(os.environ.get("UNCOUNTED_ROOT", Path(__file__).resolve().parents[2]))
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"


def canonical_bytes(obj) -> bytes:
    _reject_bad_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return "0x" + hashlib.sha256(b).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sig(x: float, digits: int = 3) -> float:
    """Round to significant figures. Estimates are uncertain; we never report false precision."""
    if x == 0 or not math.isfinite(x):
        return 0.0
    return float(round(x, -int(math.floor(math.log10(abs(x)))) + (digits - 1)))


def sig_int(x: float, digits: int = 3) -> int:
    return int(sig(x, digits))


def rel(path) -> str:
    """Repo-relative path with forward slashes (stable across operating systems)."""
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _reject_bad_floats(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("non-finite float in report")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_bad_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_bad_floats(v)
