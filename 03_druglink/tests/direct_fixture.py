"""Build a REAL Stage-2 Direct run directory for the Stage-3 contract tests.

This is not a hand-authored Direct artifact and it is not a mock. It drives Direct's
ACTUAL ``run_screen`` over synthetic input matrices, producing a genuine run directory
that Direct's OWN standalone verifier accepts (exit 0). Stage 3 is then tested against
the thing it will really be given, and the Stage-3 loader re-runs that verifier on
every load.

The wiring below MIRRORS Direct's current ``tests/direct/conftest.py::synthetic_run``
rather than reimplementing it. That matters: Stage 2 is under active development, and
a Stage-3 fixture that quietly reimplemented a stale version of Direct's evidence
wiring would be testing a Direct that no longer exists. If Direct's helpers change
again, this raises loudly — it does not fall back to an older artifact, because an
artifact Direct's current verifier rejects is exactly what Stage 3 must refuse.

The biology is synthetic and the lane is fixture-namespaced by construction: Direct's
``research_only`` lane stamps ``rq_`` identifiers and
``production_gate_passed=false`` / ``production_eligible=false`` /
``stage3_eligible=false`` — which is the shape of the forthcoming real run. Nothing
here may ever be presented as a scientific result.

The default 18-row screen deliberately contains every branch Stage 3 must handle:

  * ENSG00000000210  A_desired=decrease, B_desired=increase  -> the CROSS-ARM CONFLICT
  * ENSG00000000212  A evaluable, B not evaluable            -> asymmetric arms
  * ENSG00000000213  B evaluable, A not evaluable            -> the reciprocal
  * MTRNR2L1/4/8, OCLM  gene_symbol namespace, null Ensembl  -> unmapped dispositions
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

DEFAULT_DIRECT_WT = "/home/tcelab/worktrees/spot-stage2-direct"

# Two REAL Ensembl gene ids are substituted into Direct's synthetic target list so the
# PINNED REAL public responses (UniProt + ChEMBL 37) actually answer this run. The
# perturbation biology stays synthetic — only the gene LABELS are real — but it means
# the end-to-end research path is driven by genuine public drug evidence rather than by
# invented compounds. Nothing here is a scientific finding.
#
# With Direct's default specs this lands as:
#   CTLA4  index 1   away_from_A rank 1, desired decrease ; toward_B no_direction_evidence
#   IL2RA  index 10  away_from_A rank 2, desired decrease ; toward_B desired INCREASE
# so IL2RA is the CROSS-ARM CONFLICT row, and the same real drug is
# loss-of-function-like on one arm and OPPOSED on the other.
CTLA4 = "ENSG00000163599"
IL2RA = "ENSG00000134460"
REAL_ENSG_SLOTS = {1: CTLA4, 10: IL2RA}


class DirectFixtureError(RuntimeError):
    """Direct's current test helpers could not build a run Stage 3 may consume."""


def real_ensg_specs(default_specs: list) -> list:
    """Direct's own default specs, with two targets relabelled to real Ensembl ids."""
    import dataclasses
    out = []
    for i, spec in enumerate(default_specs):
        real = REAL_ENSG_SLOTS.get(i)
        out.append(dataclasses.replace(spec, target=real) if real else spec)
    return out


def direct_roots() -> tuple[str, str]:
    """(analysis root, Direct's test-fixture root). Absent Direct is a hard error."""
    wt = os.environ.get("SPOT_DIRECT_WT", DEFAULT_DIRECT_WT)
    analysis = os.path.join(wt, "02_geneskew", "analysis")
    fixtures = os.path.join(wt, "02_geneskew", "tests", "direct")
    if not os.path.isfile(os.path.join(analysis, "direct", "verify_run.py")):
        raise DirectFixtureError(
            "the Stage-2 Direct worktree is required to test the Stage-3 Direct "
            f"bridge, and was not found at {wt!r}. Stage 3's whole admission contract "
            "is 'Direct's standalone verifier reconstructed this run', so these tests "
            "cannot be faked or skipped. Set $SPOT_DIRECT_WT.")
    return analysis, fixtures


def build_direct_run(dest: str, *, lane: str = "analysis",
                     specs: Optional[list] = None,
                     real_ensg: bool = True) -> dict[str, Any]:
    """Drive Direct's real screen. Returns {run_dir, inputs_root, run_id, analysis}.

    Mirrors Direct's current ``synthetic_run`` fixture. A release-grade lane
    (production / research_only) may NOT stand on a pinned replay report, so it runs a
    fresh STRICT replay against the fixture's own raw source — the same gate the real
    run will face.
    """
    analysis, fixtures = direct_roots()
    for path in (analysis, fixtures):
        if path not in sys.path:
            sys.path.insert(0, path)

    try:
        import fixtures_direct as F
        import fixtures_evidence as E
        import fixtures_io as IO
        from direct import trust as T
        from direct.run_screen import build_screen
    except ImportError as exc:               # Direct's helper surface moved
        raise DirectFixtureError(
            f"Direct's test helpers do not expose the expected modules ({exc}). "
            "Stage 3 refuses to substitute an older artifact: a run that Direct's "
            "CURRENT verifier would reject is precisely what the loader must refuse."
        ) from exc

    prefix = {"research_only": "rq_", "synthetic": "fx_", "production": ""}[lane]
    release_lane = lane in ("production", "research_only")
    os.makedirs(dest, exist_ok=True)
    if specs is None:
        specs = F.default_specs()
        if real_ensg:
            specs = real_ensg_specs(specs)

    registry = os.path.join(dest, "registry.json")
    registry_sha = F._write_registry(registry, prefix=prefix)
    names = F.program_names(prefix, None)

    # selectable=False is the FAILED Stage-1 production gate — the real run's state.
    val_path, gate_path = F.write_stage1_gates(
        dest, selectable=(lane == "production"), program_ids=names)

    # Contributor evidence, built in the one order the identity rule permits:
    # raw source -> kept-offset proof -> records -> ids -> manifest citations.
    evidence = E.write_evidence(dest, specs)

    release_path, release_hashes = None, None
    if release_lane:
        kind = "production" if lane == "production" else "research"
        release_path = F.write_stage1_release(dest, registry, val_path, gate_path,
                                              kind=kind)
        rel = (T.load_production_release(release_path) if kind == "production"
               else T.load_research_release(release_path))
        release_hashes = {
            "registry_sha256": rel.hashes["registry_canonical_sha256"],
            "method_version": rel.method_version,
            "validation_sha256": rel.hashes["validation_raw_sha256"],
            "gate_spec_sha256": rel.hashes["gate_spec_raw_sha256"],
            "input_manifest_sha256": rel.hashes["input_manifest_raw_sha256"],
            "scores_sha256": rel.hashes["scores_raw_sha256"],
            "code_sha256": rel.hashes["code_raw_sha256"],
            "environment_sha256": rel.hashes["environment_raw_sha256"],
        }
        if kind == "production":
            release_hashes["selectability_pointer_sha256"] = \
                rel.hashes["selectability_pointer_raw_sha256"]

    selection = os.path.join(dest, "selection.json")
    if lane == "research_only":
        F.write_research_bridge(selection, registry_sha, release_hashes,
                                prefix=prefix)
    else:
        F.write_selection(selection, registry_sha, lane=lane, prefix=prefix,
                          release_hashes=release_hashes)

    paths = {n: os.path.join(dest, n) for n in
             ("de.h5ad", "by_guide.h5mu", "by_donors.h5mu", "sgrna.csv")}
    IO._write_main(paths["de.h5ad"], specs)
    IO._write_by_guide(paths["by_guide.h5mu"], specs)
    IO._write_by_donors(paths["by_donors.h5mu"], specs)
    IO._write_sgrna(paths["sgrna.csv"], specs)

    args = F.RunArgs(
        stage1_release=release_path, selection=selection, registry=registry,
        de_main=paths["de.h5ad"], by_guide=paths["by_guide.h5mu"],
        by_donors=paths["by_donors.h5mu"], sgrna=paths["sgrna.csv"],
        guide_manifest=evidence.manifest_path, lane=lane,
        source_registry=evidence.registry_path,
        stage1_validation=val_path, stage1_gate_spec=gate_path,
        strict_replay=release_lane, pseudobulk=evidence.source_path,
        out_root=os.path.join(dest, "out"))
    result = build_screen(args)

    return {"run_dir": result["out_dir"], "inputs_root": dest,
            "run_id": result["run_id"], "analysis": analysis}
