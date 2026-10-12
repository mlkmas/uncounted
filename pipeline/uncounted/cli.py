"""Command line interface.

  python -m uncounted fetch <case_id>            download NASA FIRMS data (needs FIRMS_MAP_KEY)
  python -m uncounted synthetic <case_id>        make synthetic test data (offline smoke runs only)
  python -m uncounted estimate <case_id> [--synthetic]
  python -m uncounted verify <report.json>       re-run the pipeline and compare hashes
  python -m uncounted hash <file>
  python -m uncounted cases
"""
import argparse
import json
import os
import sys
from pathlib import Path

from .canonical import REPORT_DIR, SNAPSHOT_DIR, rel, sha256_file
from .cases import case_from_report, get_case, load_cases


def _pointer(case_id: str) -> Path:
    return SNAPSHOT_DIR / f"{case_id}.latest"


def _remember(case_id: str, path: Path):
    _pointer(case_id).write_text(path.name + "\n")


def _latest(case_id: str) -> Path:
    p = _pointer(case_id)
    if not p.exists():
        raise SystemExit(f"No data snapshot for {case_id}. Run fetch (or synthetic) first.")
    return SNAPSHOT_DIR / p.read_text().strip()


def cmd_cases(_):
    for c in load_cases().values():
        print(f"{c.case_id:28s} {c.kind:9s} {c.region}  {c.period_start} .. {c.period_end}")


def cmd_fetch(a):
    from .firms import fetch_case
    key = a.map_key or os.environ.get("FIRMS_MAP_KEY")
    if not key:
        raise SystemExit("Set FIRMS_MAP_KEY (free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/)")
    case = get_case(a.case_id)
    print(f"Fetching {case.case_id} from NASA FIRMS ...")
    path, digest = fetch_case(case, key)
    _remember(case.case_id, path)
    print(f"Snapshot: {rel(path)}\nsha256:   {digest}")


def cmd_synthetic(a):
    from .firms import write_snapshot
    from .synthetic import generate, synthetic_case
    case = synthetic_case(get_case(a.case_id))
    path, digest = write_snapshot(generate(case), case.case_id)
    _remember(case.case_id, path)
    print(f"SYNTHETIC snapshot: {rel(path)}\nsha256: {digest}")


def cmd_estimate(a):
    from .pipeline import build_report, chain_input, write_report
    from .synthetic import synthetic_case
    case = get_case(a.case_id)
    if a.synthetic:
        case = synthetic_case(case)
    snap = Path(a.snapshot) if a.snapshot else _latest(case.case_id)
    print(f"Estimating {case.case_id} from {rel(snap)} ...")
    report = build_report(case, snap)
    path, digest = write_report(report)
    ci = chain_input(path, case)
    path.with_suffix(".chain.json").write_text(json.dumps(ci, indent=2) + "\n")
    t = report["result"]["tco2e"]
    print(f"Report:      {rel(path)}\nreportHash:  {digest}\n"
          f"tCO2e:       {t['p05']:,} .. {t['p50']:,} .. {t['p95']:,}  (5th / median / 95th pct)")
    if "attribution" in report:
        print("Peacetime check (observed / expected):",
              ", ".join(f"{v['year']}: {v['ratio']}" for v in report["attribution"]["peacetime_validation"]))


def cmd_verify(a):
    from .pipeline import build_report, write_report
    published = Path(a.report)
    original = json.loads(published.read_bytes())
    case = case_from_report(original)
    snap = Path(original["data"]["snapshot_file"])
    if not snap.is_absolute():
        from .canonical import ROOT
        snap = ROOT / snap
    result = {"report": rel(published), "published_hash": sha256_file(published)}
    snap_hash = sha256_file(snap) if snap.exists() else None
    result["data_hash_ok"] = snap_hash == original["data"]["snapshot_sha256"]
    if not result["data_hash_ok"]:
        result.update(match=False, reason="data snapshot missing or altered")
    else:
        out = REPORT_DIR / "reproduced" / published.name
        _, reproduced = write_report(build_report(case, snap), out)
        result.update(reproduced_hash=reproduced, reproduced_file=rel(out), match=reproduced == result["published_hash"])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["match"] else 1)


def cmd_hash(a):
    print(sha256_file(a.file))


def main(argv=None):
    p = argparse.ArgumentParser(prog="uncounted", description="Satellite estimates of unreported fire emissions")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cases").set_defaults(fn=cmd_cases)
    f = sub.add_parser("fetch"); f.add_argument("case_id"); f.add_argument("--map-key"); f.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("synthetic"); s.add_argument("case_id"); s.set_defaults(fn=cmd_synthetic)
    e = sub.add_parser("estimate"); e.add_argument("case_id"); e.add_argument("--synthetic", action="store_true")
    e.add_argument("--snapshot"); e.set_defaults(fn=cmd_estimate)
    v = sub.add_parser("verify"); v.add_argument("report"); v.set_defaults(fn=cmd_verify)
    h = sub.add_parser("hash"); h.add_argument("file"); h.set_defaults(fn=cmd_hash)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
