"""THE EXACT PER-LANE CLI INVOCATION CONTRACT. W7's scheduler reads this.

Split out of ``arm_topology`` for size. No number is written here: a count in this file
would be a count nobody measured. The SOURCE of each count is named instead, so a reader
can go and check it.
"""
from __future__ import annotations

from .arm_topology import BUNDLE_FILES, LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL

# --------------------------------------------------------------------------- #
# THE EXACT PER-LANE CLI INVOCATION CONTRACT.
#
# WHAT produces each bundle, WHAT it writes, and WHERE its row count is supposed to come
# from. No count is written here: a number in this file would be a number nobody measured.
# The SOURCE of the count is named, so a reader can go and check it.
# --------------------------------------------------------------------------- #
CLI_CONTRACTS = {
    LANE_DIRECT: {
        "command": "python -m direct.cli",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
            "--source-registry", "--stage1-release", "--env-lock", "--lane",
            "--out-root"],
        "one_invocation_per": "condition",
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
        # the PRODUCTION scheduler path. `direct.temporal.cli` is the RETIRED flat lane: it
        # emits one pair's two arms, not the six all-arm bundles, and a scheduler that ran
        # it would produce a release the aggregate must then refuse.
        "command": "python -m direct.temporal.arms.run_temporal_arms",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
            "--source-registry", "--stage1-release", "--batch-policy", "--out-root"],
        "one_invocation_per": "ordered condition pair",
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
        "command": "python -m direct.run_pathway",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--gene-sets", "--guide-manifest",
            "--source-registry", "--stage1-release", "--out-root"],
        "one_invocation_per": "condition x gene-set source",
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
