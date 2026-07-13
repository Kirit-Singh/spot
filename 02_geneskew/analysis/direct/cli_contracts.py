"""THE EXACT PER-LANE CLI INVOCATION CONTRACT. W7's scheduler reads this.

EVERY FLAG HERE WAS READ OFF THE PRODUCER'S OWN ``argparse``, at the pinned commit below,
and ``test_cli_contracts.py`` RE-EXTRACTS them from those same bytes and refuses if this file
has drifted. That check exists because this file had drifted, comprehensively:

    it named `python -m direct.cli`          the producer is `direct.run_arms`
    it named `python -m direct.run_pathway`  the producer is `direct.run_pathway_arms`
    it required `--stage1-v3-selection`      NO producer has ever had such a flag
    it required `--stage1-v3-schema`         nor such a flag

A scheduler that ran this contract would have died on argv, on every lane. An invocation
contract nobody parses is a comment with a colon in it.

No COUNT is written here: a number in this file would be a number nobody measured. The
SOURCE of each count is named instead, so a reader can go and check it.
"""
from __future__ import annotations

from .arm_topology import BUNDLE_FILES, LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL

# THE BYTES THIS CONTRACT WAS READ FROM. The parser test re-extracts from exactly these, so
# a producer that changes its argv without changing this file fails a test rather than a run.
PRODUCER_SOURCE = {
    LANE_DIRECT: ("fc9bdcd", "02_geneskew/analysis/direct/run_arms.py"),
    LANE_TEMPORAL: ("2021d90",
                    "02_geneskew/analysis/direct/temporal/arms/run_temporal_arms.py"),
    LANE_PATHWAY: ("2435b92", "02_geneskew/analysis/direct/run_pathway_arms.py"),
}

# The retired entry points. Each still runs, and each produces a release the aggregate must
# then refuse — which is the worst possible failure mode: a scheduler that "worked".
RETIRED_COMMANDS = {
    "python -m direct.cli": "the per-condition SCREEN, not an all-arm bundle",
    "python -m direct.temporal.cli": (
        "the RETIRED flat temporal lane: it emits ONE pair's two arms, not the six all-arm "
        "bundles"),
    "python -m direct.run_pathway": "the pathway SCREEN, not the pathway ARM bundles",
}

CLI_CONTRACTS = {
    LANE_DIRECT: {
        "command": "python -m direct.run_arms",
        # argparse `required=True`, from the producer's own bytes.
        "required_arguments": ["--de-main", "--out-root"],
        # ONE invocation emits ALL THREE condition bundles. Not three invocations: the lane's
        # own flag says so, and a scheduler that looped conditions would write three
        # single-condition runs whose run-ids do not agree.
        "invocation_flags": ["--all-conditions"],
        "one_invocation_per": "the whole lane (--all-conditions emits every condition bundle)",
        "n_invocations": 1,
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_DIRECT].values()) | {
            "screen.parquet", "masks.parquet", "contributing_guides.parquet",
            "guide_support.parquet", "donor_support.parquet", "axis.json",
            "gene_universe.json", "input_manifest.json"}),
        "expected_row_count_source":
            "one screen row per released pooled-main estimate at the bundle's condition — "
            "verification.json.source_target_count, re-derived by verify_run from the DE "
            "release obs (culture_condition == the bundle's condition)",
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable in the release's "
            "scorer view (cross-checked against release.selector.admitted_programs)",
        "expected_exit_code": 0,
    },
    LANE_TEMPORAL: {
        "command": "python -m direct.temporal.arms.run_temporal_arms",
        "required_arguments": ["--conditions", "--env-lock", "--out-root", "--stage1-view"],
        # ONE invocation emits all six ordered pairs.
        "invocation_flags": ["--all-pairs"],
        "one_invocation_per": "the whole lane (--all-pairs emits every ordered pair bundle)",
        "n_invocations": 1,
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_TEMPORAL].values()) | {
            "temporal.parquet", "endpoints.parquet"}),
        "expected_row_count_source":
            "one temporal record per target in the UNION of the two endpoints' released "
            "pooled-main targets — temporal_provenance.json.n_records",
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable in the release's "
            "scorer view (cross-checked against release.selector.admitted_programs)",
        "expected_exit_code": 0,
    },
    LANE_PATHWAY: {
        "command": "python -m direct.run_pathway_arms",
        "required_arguments": ["--condition", "--de-main", "--gene-sets", "--out-root",
                               "--signature-matrix-root"],
        # ...and this lane has NO all-in-one flag: it is invoked once per bundle.
        "invocation_flags": [],
        "one_invocation_per": "condition x gene-set source",
        "n_invocations": 6,
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_PATHWAY].values()) | {
            "pathway.json"}),
        "expected_row_count_source":
            "one pathway record per gene set in the PINNED bundle — "
            "pathway_provenance.json.run_binding.gene_sets.gene_set_release.n_sets",
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable, every arm "
            "referencing the ONE shared convergence artifact of this (condition, source)",
        "expected_hit_count_source":
            "RECONSTRUCTED, never declared: n_hits_in_ranking = |gene-set members (target "
            "namespace) INTERSECT the ranked target ids of that arm's bound ranking|, both "
            "read from the bundle's own bound bytes",
        "expected_exit_code": 0,
    },
}
