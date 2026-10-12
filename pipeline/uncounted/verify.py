"""Independent verification of a published report.

A verifier re-runs the open pipeline on the published data snapshot and compares:
  * inputs (case, data, method, parameters): must be identical
  * results: must agree within RTOL. Machine-learning steps can differ by tiny amounts
    across operating systems and library versions, so results are compared with a
    tolerance well inside the stated uncertainty range. When the verifier uses the same
    library versions (see requirements-lock.txt) the reproduction is usually bit-exact.
The verdict is written to a .verification.json file that the attest task reads.
"""
import json
from pathlib import Path

from .canonical import REPORT_DIR, ROOT, rel, sha256_file
from .cases import case_from_report

RTOL = 0.05          # 5 % relative
ATOL = 5.0           # absolute floor for small MW / tonne values
EXACT = ["schema", "case", "subject", "data", "method", "notes"]
TOLERANT = ["result", "attribution", "crosscheck"]


def _compare(a, b, path, diffs, tolerant):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append(f"{path}.{k}: missing on one side")
            else:
                _compare(a[k], b[k], f"{path}.{k}", diffs, tolerant)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _compare(x, y, f"{path}[{i}]", diffs, tolerant)
    elif tolerant and isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > max(RTOL * max(abs(a), abs(b)), ATOL):
            diffs.append(f"{path}: {a} vs {b}")
    elif a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")


def compare_reports(published: dict, reproduced: dict) -> list:
    diffs = []
    for k in EXACT:
        _compare(published.get(k), reproduced.get(k), k, diffs, tolerant=False)
    for k in TOLERANT:
        _compare(published.get(k), reproduced.get(k), k, diffs, tolerant=True)
    # hotspots are illustrative; compare their total only
    tot = lambda r: sum(next(v for kk, v in h.items() if kk not in ("lat", "lon")) for h in r.get("hotspots", []))
    a, b = tot(published), tot(reproduced)
    if abs(a - b) > max(RTOL * max(abs(a), abs(b)), ATOL):
        diffs.append(f"hotspots total: {a} vs {b}")
    return diffs


def verify(report_path: Path) -> dict:
    from .pipeline import build_report, environment, write_report
    report_path = Path(report_path)
    published = json.loads(report_path.read_bytes())
    snap = ROOT / published["data"]["snapshot_file"]
    out = {"report": rel(report_path), "published_hash": sha256_file(report_path),
           "verifier_environment": environment(), "published_environment": published.get("environment")}
    if not snap.exists() or sha256_file(snap) != published["data"]["snapshot_sha256"]:
        out.update(verdict="not_reproduced", reason="data snapshot missing or altered")
        return out
    reproduced = build_report(case_from_report(published), snap)
    rpath, rhash = write_report(reproduced, REPORT_DIR / "reproduced" / report_path.name)
    out["reproduced_hash"] = rhash
    out["reproduced_file"] = rel(rpath)
    if rhash == out["published_hash"]:
        out["verdict"] = "bit_exact"
        return out
    diffs = compare_reports(published, reproduced)
    out["verdict"] = "within_tolerance" if not diffs else "not_reproduced"
    out["tolerance"] = {"relative": RTOL, "absolute": ATOL}
    out["differences"] = diffs[:30]
    return out


def write_verification(result: dict) -> Path:
    name = Path(result["report"]).name.replace(".json", ".verification.json")
    p = REPORT_DIR / "reproduced" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2) + "\n")
    return p
