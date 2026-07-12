"""The INDEPENDENT Stage-3 verifier.

    PYTHONPATH=. python -m verifier.verify_stage3 \
        --bundle <stage3 research bundle dir> \
        --cache-root <acquisition cache> \
        --direct-run <verified Direct run dir> \
        --direct-inputs-root <raw Direct inputs> \
        --artifact_class research_only \
        --write-report

Independence is structural and test-enforced: this package imports NOTHING from
``druglink``. It restates the contract (``verifier/policy.py``), reimplements content
addressing (``verifier/canon.py``), re-expands the two arms straight from Direct's
``screen.parquet``, re-derives every intervention effect and translation class from
the retained verbatim source fields, and re-runs Direct's OWN standalone verifier.

Exit 0 = every check passed. A zero candidate count is a scientific result, not a
verification failure.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Optional

from . import checks


def verify(*, bundle: str, cache_root: str, direct_run: str,
           direct_inputs_root: str, artifact_class: str,
           direct_analysis: Optional[str] = None,
           science_registry_root: Optional[str] = None) -> checks.Report:
    return checks.run_checks(bundle=bundle, cache_root=cache_root,
                             direct_run=direct_run,
                             direct_inputs_root=direct_inputs_root,
                             artifact_class=artifact_class,
                             direct_analysis=direct_analysis,
                             science_registry_root=science_registry_root)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Independent Stage-3 verifier")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--direct-run", required=True)
    ap.add_argument("--direct-inputs-root", required=True)
    ap.add_argument("--artifact-class", required=True,
                    choices=["analysis", "fixture"])
    ap.add_argument("--direct-analysis", default=None)
    ap.add_argument("--science-registry", default=None,
                    help="the Claude Science evidence registry. Every "
                         "referenced record is resolved and re-hashed.")
    ap.add_argument("--write-report", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        rep = verify(bundle=args.bundle, cache_root=args.cache_root,
                     direct_run=args.direct_run,
                     direct_inputs_root=args.direct_inputs_root,
                     artifact_class=args.artifact_class,
                     direct_analysis=args.direct_analysis,
                     science_registry_root=args.science_registry)
    except Exception as exc:                # a crash IS a verification failure
        rep = checks.Report()
        rep.check(f"verifier completed ({type(exc).__name__}: {exc})", False)

    payload = rep.as_dict(
        artifact_class=args.artifact_class,
        bundle_id=os.path.basename(os.path.abspath(args.bundle.rstrip("/"))),
        verified_at=_dt.datetime.now(_dt.UTC).isoformat())

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(rep.render())
        if rep.failures:
            print("\nFAILURES:")
            for name, detail in rep.failures:
                print(f"  - {name} {detail}")

    if args.write_report:
        path = os.path.join(args.bundle, "verification.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")

    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
