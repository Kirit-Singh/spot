"""Independent verifier CLI.

    python -m verifier.verify_stage4 --release outputs/<scorecard_set_id> [--method method]

Exit 0 = every reconstruction and hash check passed. Exit 1 = at least one failed.
It reads only the release directory and the declared method bundle; it never imports the
generator, so a bug or a tamper in `analysis/` cannot validate itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .checks import verify_release

DEFAULT_METHOD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "method"
)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="verify_stage4", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", required=True, help="a Stage-4 scorecard-set directory")
    ap.add_argument("--method", default=DEFAULT_METHOD_DIR)
    ap.add_argument("--json", action="store_true", help="print the full verification document")
    args = ap.parse_args(argv)

    report = verify_release(args.release, args.method)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"release        {args.release}")
        print(f"scorecard_set  {report['scorecard_set_id']}")
        print(f"scope          {report['scope']}")
        print(f"status         {report['status']}  "
              f"({report['n_checks']} checks, {report['n_failed']} failed)")
        for c in report["checks"]:
            if c["status"] == "fail":
                print(f"  FAIL {c['check_id']}: {c['detail']}", file=sys.stderr)

    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
