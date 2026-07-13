"""Produce the SYNTHETIC, verifier-ADMITTED P2S bundle the UI is built against.

    python -m p2s_arms.make_ui_fixture --out-root <dir outside every tracked tree>

W16 needs a payload to build the secondary-evidence panel against before the real run
exists. This produces one through the REAL producer and the REAL independent verifier — the
data is synthetic, the artifact is not. If the artifact shape moves, this stops admitting,
which is the point.

WHAT THE UI MUST READ OFF IT, AND MUST NOT
------------------------------------------
Read: ``support_status`` and ``opposed`` PER ``arm_key``, plus the denominators
(``n_runs``, ``n_selected_runs``) that go with every frequency.

Do NOT: rank by it, gate on it, promote or demote a Direct target with it, or show it as
agreement that "validates" a Direct result. It is reconstruction support, and
``lane_role = secondary_non_gating`` is in the artifact's own bytes.

A target may be SUPPORTED on one arm and OPPOSED on the other — that is not a contradiction,
it is the sign transform, and both must be shown as they are. Never fuse them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from . import binding, config, synthetic, upstream
from . import run_p2s_arms as runner
from . import verify_p2s_arms as verifier

ARM_KEY = f"direct|{synthetic.PROGRAM}|increase|{synthetic.CONDITION}"


def build(out_root: str, *, arm_key: str = ARM_KEY) -> dict:
    """Direct bundle -> P2S support -> independent verification. Deterministic at seed 42."""
    from direct import scorer_view

    release = synthetic.make_release()
    view = scorer_view.view(release)

    work = tempfile.mkdtemp(prefix="p2s_ui_fixture_")
    direct_dir = synthetic.write_arm_bundle(os.path.join(work, "direct"), view)

    paths = {
        "cells": synthetic.make_cells(os.path.join(work, "cells.npz")),
        "effects": synthetic.make_effects(os.path.join(work, "effects.parquet")),
        "masks": synthetic.make_masks(os.path.join(work, "masks.parquet")),
        "eligible": synthetic.make_eligible(os.path.join(work, "eligible.parquet")),
    }

    report = {"verdict": "admit",
              "verifier_id": "spot.stage02.direct.arm.verifier.v1",
              "report_sha256": "0" * 64}
    bound = binding.bind(arm_key=arm_key, bundle_dir=direct_dir, view=view,
                         verifier_report=report)

    up = upstream.identity(dict(synthetic.UPSTREAM_OBSERVED,
                                commit=config.UPSTREAM_COMMIT,
                                version=config.UPSTREAM_VERSION))

    out = runner.execute(
        bound=bound, release=release, view=view, up=up, paths=paths,
        out_root=out_root, lane=runner.LANE_SYNTHETIC, seed=config.RANDOM_STATE,
        argv=["--make-ui-fixture"], fit=synthetic.linear_fit)

    # generator != verifier: the fixture is only a fixture if the INDEPENDENT verifier
    # admits it. A payload the UI is built against that its own verifier would reject is a
    # payload that will never appear in production.
    report = verifier.verify(out["out_dir"])
    out["verification"] = report
    with open(os.path.join(out["out_dir"], "p2s_verification.json"), "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-root", required=True,
                    help="a directory OUTSIDE every tracked tree")
    ap.add_argument("--arm-key", default=ARM_KEY)
    args = ap.parse_args(argv)

    out = build(args.out_root, arm_key=args.arm_key)
    verdict = out["verification"]["verdict"]

    print(json.dumps({
        "p2s_run_id": out["p2s_run_id"],
        "out_dir": out["out_dir"],
        "arm_key": out["arm_key"],
        "n_support_rows": out["n_support_rows"],
        "verdict": verdict,
        "lane_role": config.LANE_ROLE,
        "data": "SYNTHETIC — planted contributor and planted OPPOSED contributor",
    }, indent=2))

    if verdict != verifier.ADMIT:
        print("the independent verifier REJECTED the fixture", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
