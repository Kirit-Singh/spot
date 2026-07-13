"""Public-packaging hygiene regression scan.

(1) No machine-local absolute path or developer identity in the human-authored public
    surface (root + stage READMEs, DATA_LICENSES, schemas, docs, the HF templates, and the
    touched browser test). Frozen hash-pinned data artifacts (e.g. effect_universe_gwcd4i.json,
    whose full-file SHA is bound in PROTECTED_HASHES.json + the release manifest) are OUT of
    this scan: their bytes cannot change without a coordinated re-freeze. The one such artifact
    that still carries a build-time machine path is tracked in docs/PUBLIC_PACKAGING_CHECKLIST.md
    as a deferred reseal item.

(2) The rewritten public READMEs describe the CURRENT generic pipeline, not a retired
    fixed-Treg axis / traffic-light / DGIdb-LINCS-as-current framing.

This file itself is NOT in the scan set: it legitimately contains the path patterns as
detection logic.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

# machine-local path / developer-identity patterns that must not appear in the public surface
MACHINE_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"/home/[A-Za-z0-9._-]+"),
    re.compile(r"\btcedirector:"),
    re.compile(r"\btcefold:"),
    re.compile(r"/mnt/tcenas"),
    re.compile(r"\bkiritsingh\b"),
]

# human-authored public surface scanned for machine paths (repo-relative)
SCANNED_FILES = [
    "README.md",
    "DATA_LICENSES.md",
    "schemas/README.md",
    "schemas/paper_concordance_run_receipt.schema.json",
    "schemas/source_license_inventory.json",
    "01_programs/README.md",
    "02_geneskew/README.md",
    "03_druglink/README.md",
    "04_PKPD/README.md",
    "01_programs/hf_release/STAGE1_V3_DATASET_CARD.template.md",
    "01_programs/hf_release/stage1_release_hf_manifest.template.json",
    "docs/history/README.md",
    "docs/PUBLIC_PACKAGING_CHECKLIST.md",
    "01_programs/analysis/test_selection_v3_browser.mjs",
    "deploy/RELEASE_ASSEMBLY.md",
    "deploy/release_spec.template.json",
    "deploy/handoff_release.sh",
]

# deploy/assemble_release.py and deploy/tests/ are deliberately NOT scanned: like this file,
# they carry the machine-path patterns as detection logic / refusal fixtures.

# frozen, hash-pinned artifact that legitimately still carries a build-time machine path,
# deferred to the coordinated reseal (docs/PUBLIC_PACKAGING_CHECKLIST.md). NOT scanned.
KNOWN_DEFERRED = {"01_programs/analysis/effect_universe_gwcd4i.json"}

# READMEs that must describe the current generic pipeline
README_DOCS = ["README.md", "02_geneskew/README.md", "03_druglink/README.md", "04_PKPD/README.md"]

# framings that must not appear as a CURRENT claim in the public READMEs
BANNED_CURRENT = ["traffic light", "traffic_light", "locked treg", "fixed treg axis", "dgidb", "lincs"]
# a banned term is admissible only when the SAME line marks it retired / negated / planned
QUALIFIERS = ("no traffic", "not a fixed", "no fixed", "retired", "historical", "no longer",
              "not currently", "not in the current", "planned", "deferred", "demo default",
              "labelled demo", "only as", "never", "no composite")


def test_no_machine_local_paths():
    offenders = []
    for rel in SCANNED_FILES:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            offenders.append(f"{rel}: MISSING (expected in the public-surface scan set)")
            continue
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                # strip URLs first: an official URL may legitimately contain "/home/" etc.
                # (e.g. ncbi.nlm.nih.gov/home/about/policies/); a machine path is never a URL.
                scan = re.sub(r"https?://\S+", "", line)
                for pat in MACHINE_PATTERNS:
                    if pat.search(scan):
                        offenders.append(f"{rel}:{i}: machine path {pat.pattern!r}")
    assert not offenders, "machine-local path(s) in public surface:\n" + "\n".join(offenders)


def test_public_readmes_have_no_retired_current_framing():
    offenders = []
    for rel in README_DOCS:
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                low = line.lower()
                for term in BANNED_CURRENT:
                    if term in low and not any(q in low for q in QUALIFIERS):
                        offenders.append(f"{rel}:{i}: unqualified retired framing {term!r}")
    assert not offenders, "retired-as-current framing in public READMEs:\n" + "\n".join(offenders)


def test_public_readmes_assert_current_generic_pipeline():
    root = open(os.path.join(REPO, "README.md"), encoding="utf-8").read()
    assert "generic" in root and "spot.stage01_selection.v3" in root, \
        "root README must name the generic selector + v3 selection contract"
    s2 = open(os.path.join(REPO, "02_geneskew/README.md"), encoding="utf-8").read()
    for origin in ("Direct", "temporal", "pathway"):
        assert origin in s2, f"Stage-2 README must keep the {origin!r} origin explicit"
    s3 = open(os.path.join(REPO, "03_druglink/README.md"), encoding="utf-8").read()
    assert "direction" in s3.lower(), "Stage-3 README must describe direction-aware annotation"
