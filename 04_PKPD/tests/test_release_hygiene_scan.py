"""Release-hygiene scans over the TRACKED bytes — the ones a stranger actually receives.

From the final-release hygiene audit (2026-07-13): B2, B4 and M1. Three of its findings were
things no test could see, because every existing test asks whether the ENGINE is honest and none
asked what the REPOSITORY ships:

  * **M1** — 26 real ChEMBL/UniProt response files were tracked under
    `tests/fixtures/stage3_annotation/cache/raw/`, labelled `acquired_public` in their own
    manifest, while the README called the fixtures synthetic and `analysis/acquisition.py` states
    the invariant "Git holds small synthetic fixtures and manifests only". They were removed.
  * **B4** — machine-local paths (`/home/tcelab/.spot-runs/…`) were bound into a tracked test, so
    the suite verified exactly one machine.
  * **B2** — `DATA_LICENSES.md` said "No third-party data is bundled in this repo", which was
    false: the tracked Stage-3 bundle fixtures carry ChEMBL-derived facts (CHEMBL ids, target
    classes), which are CC BY-SA 3.0, not MIT.

The rule these encode: **provenance metadata is committed; third-party payload bytes are not.**
A locator + hash + licence is how a byte is re-fetched and audited. The byte itself is somebody
else's, cached outside the tree under the run root.
"""

from __future__ import annotations

import os
import re
import subprocess

import pytest

STAGE4_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(STAGE4_DIR)
DATA_LICENSES = os.path.join(REPO_ROOT, "DATA_LICENSES.md")


def _tracked(prefix: str) -> list[str]:
    """Files Git actually ships. Not what is on disk — untracked scratch is not released."""
    out = subprocess.run(["git", "-C", REPO_ROOT, "ls-files", prefix],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        pytest.skip("not a git checkout; the release scan has nothing to scan")
    return [p for p in out.stdout.splitlines() if p.strip()]


def _read(rel: str) -> str:
    """A tracked file that is missing on disk is a staging mistake, not a scan crash."""
    path = os.path.join(REPO_ROOT, rel)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# --------------------------------------------------------------- B4: no machine-local paths

# A filesystem path, not a URL path: `https://www.ncbi.nlm.nih.gov/home/about/policies/` is a
# public locator and must keep working. The lookbehind rejects a match glued to a hostname.
MACHINE_PATH = re.compile(
    r"(?<![A-Za-z0-9.])(?:/home/|/Users/|/mnt/tcenas|/media/|/root/)[a-z]"
    r"|tcedirector|tcefold|\b100\.117\.50\.59\b")

# Obviously-fake stand-ins used to PROVE a refusal (an absolute cache path is rejected). They
# name no real machine, and removing them would delete the negative test.
SYNTHETIC_PLACEHOLDERS = ("/home/somebody", "/Users/example")

# The ONLY files allowed to name a machine path, and the reason each is allowed. A blanket
# "skip the tests directory" would have hidden the very defect this scan exists to catch.
MACHINE_PATH_ALLOWED = {
    # The detectors themselves: they must spell the patterns out in order to reject them.
    "04_PKPD/analysis/canonical.py",
    "04_PKPD/tests/test_source_verify.py",
    "04_PKPD/tests/test_release_hygiene_scan.py",
    # Historical prose: the docstring explains the defect it fixed, and names the path that used
    # to be hard-coded. The audit allows exactly this — "a narrow allowlist only for explicitly
    # historical audit prose".
    "04_PKPD/analysis/source_verify.py",
}


def test_no_tracked_stage4_file_binds_a_machine_local_path():
    """A hash that binds one developer's path is not a scientific identity, and a test that
    reads `/home/<someone>/…` verifies exactly one machine."""
    offenders = {}
    for rel in _tracked("04_PKPD"):
        if rel in MACHINE_PATH_ALLOWED or rel.endswith((".parquet", ".xml")):
            continue
        body = _read(rel)
        for fake in SYNTHETIC_PLACEHOLDERS:
            body = body.replace(fake, "<placeholder>")
        hits = sorted({m.group(0) for m in MACHINE_PATH.finditer(body)})
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "tracked Stage-4 files bind machine-local paths. Take the value from an environment "
        f"variable or a CLI argument, or add it to MACHINE_PATH_ALLOWED with a reason: {offenders}")


# ------------------------------------------- M1: no third-party payload bytes in the release

def test_no_third_party_response_payload_is_tracked():
    """The repo's own law, enforced: `analysis/acquisition.py` — "Git holds small synthetic
    fixtures and manifests only", and `RunRoot` refuses a cache inside the working tree.

    26 real ChEMBL/UniProt responses were tracked under a `cache/raw/` tree anyway. A live public
    response committed by accident is a licensing problem that no later `git rm` undoes, because
    the bytes stay in history.
    """
    payloads = [rel for rel in _tracked("04_PKPD")
                if re.search(r"(^|/)(raw|cache)/", rel)]
    assert not payloads, (
        "raw third-party response bytes are tracked. Cache them outside the tree under the run "
        f"root and commit the manifest (locator + hash + licence), never the payload: {payloads}")


def test_no_tracked_fixture_claims_a_real_public_acquisition_of_its_own_bytes():
    """`acquired_public` on a tracked PAYLOAD means real bytes are in Git.

    On a tracked MANIFEST it means the opposite and is correct: the record says where a byte came
    from, what it hashed to and under what terms — which is exactly what must be committed so the
    fetch can be audited and repeated. So this scans the payload formats only.
    """
    suspects = []
    for rel in _tracked("04_PKPD/tests/fixtures"):
        if not rel.endswith((".json", ".xml")):
            continue
        body = _read(rel)
        # a stored ChEMBL/UniProt response body carries the API's own envelope
        if '"page_meta"' in body or '"x-total-results"' in body:
            suspects.append(rel)

    assert not suspects, (
        f"a real public API response body is tracked as a fixture: {suspects}")


# ------------------------------------------------- B2: the licence ledger may not contradict

def test_the_licence_ledger_does_not_deny_the_third_party_bytes_the_repo_ships():
    """`DATA_LICENSES.md` claimed "No third-party data is bundled in this repo". The tracked
    Stage-3 bundle fixtures carry ChEMBL-derived facts (CHEMBL ids, target classes). A reader
    who believed the ledger would treat CC BY-SA 3.0 content as MIT."""
    ledger = _read("DATA_LICENSES.md")

    assert "No third-party data is bundled" not in ledger, (
        "the ledger still denies bundling third-party data while ChEMBL-derived fixtures are "
        "tracked")
    for required in ("CC BY-SA 3.0", "ChEMBL", "UniProt"):
        assert required in ledger, f"the ledger does not state {required!r}"


def test_the_root_MIT_licence_is_scoped_to_code_not_to_data():
    """The audit's failure scenario, exactly: "The repository is published under MIT while
    containing ChEMBL-derived response bytes … A downstream user could reasonably but
    incorrectly treat all tracked content as MIT.\""""
    ledger = _read("DATA_LICENSES.md")
    assert re.search(r"code is \*\*MIT\*\*|MIT.{0,60}\bcode\b|\bcode\b.{0,60}MIT",
                     ledger, re.S | re.I), (
        "the ledger must scope MIT to spot's own code, and say so before any data table")
    assert re.search(r"data.{0,80}(are|is) not MIT|not.{0,40}MIT", ledger, re.S | re.I), (
        "the ledger must say plainly that the third-party data it ships are NOT MIT")


def test_the_ledger_states_the_sources_stage4_actually_queries():
    """Source-by-source, with terms — not one averaged claim. openFDA is CC0 *with marked
    exceptions*; DailyMed has no verified blanket licence; ClinicalTrials.gov is not public
    domain. Each was previously flattened into "US public domain"."""
    ledger = _read("DATA_LICENSES.md")
    for source in ("DailyMed", "openFDA", "PubChem", "RxNorm", "ClinicalTrials.gov"):
        assert source in ledger, f"{source} is queried or refused by Stage 4 but is not in the ledger"

    assert "US public domain | U.S. FDA" not in ledger
    assert re.search(r"ClinicalTrials\.gov.{0,200}not", ledger, re.S | re.I), (
        "ClinicalTrials.gov must not be relabelled public domain")


# ------------------------------------- the re-audit of f8495d5: claims that outlived their truth

# Phrases that were TRUE once and are now false. A doc that says the engine cannot do what it
# demonstrably does is not a stale sentence, it is a wrong capability claim — and it is exactly
# what a stranger reads first. Each retired phrase is pinned here so it cannot creep back.
RETIRED_CLAIMS = {
    "Stage 3 has not landed":
        "the two-gate Stage-3 admission is wired and 13 admission tests pass",
    "is scaffolding and emits nothing":
        "Stage 3 emits real bundles; Stage 4 admits them",
    "No real-source evidence loader is wired":
        "the public acquisition adapters (PubChem, RxNorm, DailyMed, openFDA) are wired",
    "no_real_evidence_adapters_wired":
        "this refusal code exists nowhere in the codebase — the doc invented a guard",
    "academic / non-commercial":
        "a project-wide non-commercial restriction was never true of the code (MIT) and is not "
        "how per-source terms work; reuse follows each row's own licence",
}


def test_no_retired_capability_claim_survives_in_a_tracked_doc():
    """The docs may not deny a capability the code has, nor invent a guard it does not have."""
    offenders = {}
    for rel in _tracked("04_PKPD"):
        if not rel.endswith(".md") or rel.endswith("test_release_hygiene_scan.py"):
            continue
        body = _read(rel)
        hits = [p for p in RETIRED_CLAIMS if p in body]
        if hits:
            offenders[rel] = hits

    ledger_hits = [p for p in RETIRED_CLAIMS if p in _read("DATA_LICENSES.md")]
    if ledger_hits:
        offenders["DATA_LICENSES.md"] = ledger_hits

    assert not offenders, "\n".join(
        f"{rel}: {p!r} — {RETIRED_CLAIMS[p]}" for rel, ps in offenders.items() for p in ps)


def test_the_ledger_imposes_no_project_wide_noncommercial_restriction():
    """The original audit's words: these "are not the current production evidence path and create
    needless restrictions/confusion". Reuse follows each ROW's licence. spot's code is MIT, and
    MIT does not override anyone's data terms — in either direction."""
    ledger = _read("DATA_LICENSES.md")
    assert "non-commercial" not in ledger.split("## ")[0], (
        "the ledger's preamble still imposes a project-wide non-commercial restriction")
    assert re.search(r"MIT.{0,160}(does not|never).{0,40}(override|extend|apply)",
                     ledger, re.S | re.I), (
        "the ledger must say that code MIT does not override the data terms")


def test_the_readme_does_not_hard_code_a_drifting_test_count():
    """The audit's minor finding 4: "The exact test-count claims in READMEs will drift; prefer
    verifier command + expected exit status over a hard-coded count." It drifted within one
    commit — 1244 was stale on arrival (1253 supplied / 1236 bare)."""
    readme = _read("04_PKPD/README.md")
    counts = re.findall(r"\b\d{3,5}\s+tests\b", readme)
    assert not counts, (
        f"README hard-codes a test count {counts}; it drifts with every commit. State the command "
        "and its expected exit status instead.")


# ---------------- the second re-audit: the scan itself was the hole (it only read .md)

# `RETIRED_CLAIMS` above scanned Markdown only. So `analysis/schemas_export.py` went on
# GENERATING "Stage 3 ... has not landed (03_druglink/ is scaffolding and emits nothing)" into
# `schemas/spot.stage03_drug_candidate_set.v1.schema.json` — a SERVED artifact — and every scan
# passed. A doc nobody reads is embarrassing; a served schema that tells a consumer the upstream
# stage does not exist is a contract lie, and it was being emitted by code.
#
# So: scan the artifacts a consumer is actually handed — Python, JSON, and the generated schemas.
SERVED_RETIRED = {
    "has not landed":
        "the two-gate Stage-3 admission is wired; the schema itself declares "
        "stage3_implementation_landed: true, so the artifact contradicted itself",
    "scaffolding and emits nothing":
        "Stage 3 emits real bundles and Stage 4 admits them",
    "NOT agreed with":
        "the contract is reconciled through the adapters, not authored unilaterally",
    "no_real_evidence_adapters_wired":
        "a refusal code that exists nowhere in the codebase",
}

# A drifting count in a SERVED artifact is worse than in a README: a consumer cannot tell a
# dropped test from a deleted one, and it is baked into the schema a downstream stage validates
# against.
SERVED_TEST_COUNT = re.compile(r"\b\d{2,5}\s+tests\b")

# The ONLY exemptions, each an immutable snapshot that may not be rewritten:
FROZEN_SNAPSHOTS = (
    # A real v1 release + the method it was BOUND to. Rewriting either would forge history.
    "04_PKPD/tests/fixtures/historical_v1_release/",
    # v1 method prose. Its bytes are hashed into the identity of every v1 release ever emitted,
    # so it CANNOT change — which is exactly why v2 must not inherit its status claim. It carries
    # `stage3_frozen: false` and an r5 pin that were true when v1 was cut and are not true now.
    # The repair is not to edit this file; it is that v2 no longer serves it. See
    # tests/test_stage3_status_is_run_bound_not_frozen.py.
    "04_PKPD/method/stage4_prose_v1.json",
)

SERVED_SUFFIXES = (".py", ".json", ".md")


def _served_files() -> list[str]:
    return [rel for rel in _tracked("04_PKPD")
            if rel.endswith(SERVED_SUFFIXES)
            and not rel.startswith(FROZEN_SNAPSHOTS)
            and "test_release_hygiene_scan.py" not in rel]


def test_no_retired_stage3_claim_is_SERVED_by_code_or_a_generated_schema():
    """Not only READMEs. The generator, and what the generator writes."""
    offenders = {}
    for rel in _served_files():
        body = _read(rel)
        hits = [p for p in SERVED_RETIRED if p in body]
        if hits:
            offenders[rel] = hits

    assert not offenders, "\n".join(
        f"{rel}: {p!r} — {SERVED_RETIRED[p]}" for rel, ps in offenders.items() for p in ps)


def test_no_served_artifact_bakes_in_a_drifting_test_count():
    """`03_druglink/ (106 tests + independent verifier)` was compiled into the exported schema."""
    offenders = {}
    for rel in _served_files():
        hits = sorted(set(SERVED_TEST_COUNT.findall(_read(rel))))
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        f"a served artifact hard-codes a test count: {offenders}. Counts drift; state the "
        "verifier command and its expected exit status instead.")
