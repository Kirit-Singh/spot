"""THE EXACT PER-LANE CLI INVOCATION CONTRACT. W7's scheduler reads this.

REGENERATED against the ACTUAL production producer modules and their real argparse flags
(``run_arms`` / ``run_temporal_arms`` / ``run_pathway_arms``). The previous contract named
``direct.cli``, ``direct.run_pathway`` and a batch of ``--stage1-v3-*`` / ``--batch-policy``
flags that no current parser defines — a manifest advertising THAT would state a different
execution than the one that produced its bundles. Every ``required_arguments`` entry below is
a flag the named module's parser actually accepts (``test_cli_contracts`` parser-tests it).

No count is written here: a number in this file would be a number nobody measured. The SOURCE
of each count is named instead, so a reader can go and check it.
"""
from __future__ import annotations

from .arm_topology import BUNDLE_FILES, LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL

# The ACTUAL production module for each lane (a fully-qualified ``python -m`` target).
LANE_MODULE = {
    LANE_DIRECT: "direct.run_arms",
    LANE_TEMPORAL: "direct.temporal.arms.run_temporal_arms",
    LANE_PATHWAY: "direct.run_pathway_arms",
}

# Named so a scheduler cannot rediscover a lane the topology retired. These are NOT the
# production producers and must never appear in a captured invocation.
RETIRED_LANE_MODULES = ("direct.cli", "direct.run_pathway", "direct.temporal.cli")

CLI_CONTRACTS = {
    LANE_DIRECT: {
        "command": "python -m direct.run_arms",
        # The complete Direct release is ONE invocation with --all-conditions (every
        # condition the bound Stage-1 release ships), not one run per condition.
        "required_arguments": [
            "--all-conditions", "--de-main", "--stage1-release", "--stage1-release-root",
            "--registry", "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
            "--source-registry", "--lane", "--env-lock", "--out-root"],
        "one_invocation_per": "the complete Direct release (--all-conditions): one all-arm "
                              "bundle per condition the bound Stage-1 release ships",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_DIRECT].values()) | {
            "arms.parquet", "masks.parquet", "contributing_guides.parquet",
            "guide_support.parquet", "donor_support.parquet",
            "gene_universe.json", "input_manifest.json"}),
        "expected_row_count_source":
            "one arm row per released pooled-main estimate at the bundle's condition — "
            "provenance.json.n_arm_rows, re-derived by the verifier from the DE release obs",
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable in the release's "
            "scorer view (cross-checked against release.selector.admitted_programs)",
        "expected_exit_code": 0,
    },
    LANE_TEMPORAL: {
        # The PRODUCTION all-arm reusable lane. It differences TWO admitted Direct all-arm
        # bundles per condition (--direct-bundle COND:DIR + --w10-report COND:REPORT) and
        # emits all six ordered-pair bundles in one --all-pairs invocation.
        "command": "python -m direct.temporal.arms.run_temporal_arms",
        "required_arguments": [
            "--stage1-view", "--stage1-release", "--direct-bundle", "--w10-report",
            "--env-lock", "--conditions", "--all-pairs", "--out-root"],
        "one_invocation_per": "the complete temporal release (--all-pairs): all six ordered "
                              "condition-pair bundles from the admitted Direct endpoints",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_TEMPORAL].values()) | {
            "rankings/"}),
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
        # ONE (condition, source) bundle per invocation; six invocations = 3 conditions x 2
        # pinned gene-set sources. Step 0 (signature_matrix.build_condition) runs first, once
        # per condition.
        "required_arguments": [
            "--condition", "--gene-sets", "--de-main", "--signature-matrix-root",
            "--stage1-release", "--stage1-release-root", "--registry", "--by-guide",
            "--by-donors", "--sgrna", "--guide-manifest", "--source-registry", "--lane",
            "--env-lock", "--out-root"],
        "one_invocation_per": "condition x gene-set source",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_PATHWAY].values()) | {
            "pathway_evidence.json", "gene_sets.source.json", "signature_ref.json"}),
        "expected_row_count_source":
            "one pathway record per gene set in the PINNED bundle — "
            "pathway_provenance.json.run_binding.evidence_artifacts (gene_set_release.n_sets)",
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable, every arm "
            "referencing the ONE shared convergence artifact of this (condition, source)",
        "expected_hit_count_source":
            "RECONSTRUCTED, never declared: n_headline_rankable = |gene-set members (target "
            "namespace) INTERSECT the ranked target ids of that arm|, from the bundle's own "
            "bound bytes",
        "expected_exit_code": 0,
    },
}
