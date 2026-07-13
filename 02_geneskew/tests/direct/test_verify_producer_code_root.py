"""W10's PRODUCER CODE ROOT — the verifier hashes the tree the RUN was taken from.

THE PRODUCTION BUG. ``gate_code_identity`` re-derived the code manifest by walking
``os.path.dirname(_HERE)`` — the VERIFIER's own checkout. So the number it compared against
``code_identity.manifest_sha256`` was a fact about the machine running the checker, not about
the run under test. Two consequences, both fatal:

  * a verifier running from the producer's own tree ADMITS by construction — it hashes itself
    and finds that it agrees with itself, which is the generator signing its own homework by
    another route;
  * an INDEPENDENT verifier — a separate checkout, which is the only kind worth having — can
    never admit a real release: its own tree is not the producer's tree, so the manifest it
    derives is not the manifest the run bound, and every honest bundle REFUSES.

The tree a run was taken from is an INPUT to verification, exactly like the H5AD. So it is
supplied: ``--producer-code-root``. The verifier then proves the tree IS the one the run
claims — git HEAD is the bound commit, the working tree is in the declared state — and
re-derives the manifest FROM THAT TREE. The verifier's own identity stays where it belongs:
``verifier_code_sha256``, over the verifier's own modules, never confused with the producer's.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import verify_arm_bundle as VB  # noqa: E402
import verify_arm_gates as G  # noqa: E402

# The PRODUCER's own digest recipe. The test harness may drive the producer; the VERIFIER may
# not import it, and gate_independence proves that against the verifier's own source.
from direct import code_digest  # noqa: E402
from verify_arm_report import Report, verifier_code_sha256  # noqa: E402

VERIFIER_TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))                                  # 02_geneskew/

SUPPLIED = "code root is SUPPLIED"
HEAD = "git HEAD IS the commit"
DECLARED = "working state is the one the run DECLARED"
REDERIVES = "RE-DERIVES from the tree this run claims"
RELEASE_DIRTY = "a release-grade lane REFUSES a dirty tree"


def _git(repo: str, *args: str) -> str:
    return subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                          check=True).stdout.strip()


def _commit(repo: str, message: str = "c") -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


class ProducerTree:
    """A REAL git checkout, standing in for the tree a production run was taken from.

    It is NOT the verifier's tree: a different commit history, a different file set and a
    different manifest. That is the whole point — if the verifier still admits, it admitted
    the tree it was HANDED, and if it can be made to refuse by moving that tree, then the tree
    it was handed is the one it actually checked.
    """

    def __init__(self, tmp_path):
        self.repo = str(tmp_path / "producer_repo")
        self.root = os.path.join(self.repo, "02_geneskew")
        os.makedirs(os.path.join(self.root, "analysis", "direct"))
        self.write("analysis/direct/run_arms.py", "ARM = 'skew_toward'\n")
        self.write("analysis/direct/config.py", "METHOD_VERSION = '1'\n")
        self.write("analysis/inputs.json", json.dumps({"de": "GWCD4i"}) + "\n")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        self.commit = _commit(self.repo, "the production tree")

    def write(self, rel: str, text: str) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def code_identity(self, *, require_clean: bool = True) -> dict:
        """The producer's OWN code-identity block for this tree — its real recipe."""
        return code_digest.run_binding(self.root, self.repo, require_clean=require_clean)

    def binding(self, lane: str = "production", **over) -> dict:
        code = dict(self.code_identity(), **over.pop("code_identity", {}))
        return dict({"lane": lane, "code_identity": code}, **over)


@pytest.fixture
def producer(tmp_path):
    return ProducerTree(tmp_path)


def run_gate(binding: dict, root) -> dict:
    rep = Report(verifier_code_sha256())
    rep.bound = G.gate_code_identity(binding, root, rep)    # as verify() binds it
    return rep.doc()


def refused_at(binding: dict, root, substring: str) -> bool:
    doc = run_gate(binding, root)
    return (doc["verdict"] == "REFUSE"
            and any(substring in g for g in doc["failed_gates"]))


# --------------------------------------------------------------------------- #
# THE ADMIT: a SEPARATE tree, at the bound commit, clean.
# --------------------------------------------------------------------------- #
class TestASeparateProducerTreeAtTheBoundCommit:
    def test_it_ADMITS_every_code_identity_gate(self, producer):
        doc = run_gate(producer.binding(), producer.root)
        assert doc["failed_gates"] == []
        assert doc["verdict"] == "ADMIT"

    def test_the_tree_it_admitted_is_NOT_the_verifiers_own_checkout(self, producer):
        # If these coincided the test would prove nothing: a verifier that hashes itself
        # agrees with itself. They must be different trees, different commits.
        assert os.path.realpath(producer.root) != os.path.realpath(VERIFIER_TREE)
        assert producer.commit != _git(VERIFIER_TREE, "rev-parse", "HEAD")

    def test_the_manifest_it_checked_is_the_PRODUCER_trees_manifest(self, producer):
        # the number that must have been re-derived: the producer tree's, which the verifier's
        # own tree cannot produce (3 files vs the whole Stage-2 package)
        code = producer.code_identity()
        assert code["n_files"] == 3
        assert run_gate(producer.binding(), producer.root)["verdict"] == "ADMIT"


# --------------------------------------------------------------------------- #
# THE BUG ITSELF: the verifier's own checkout is not a producer identity.
# --------------------------------------------------------------------------- #
class TestTheVerifiersOwnCheckoutIsNeverTheProducerIdentity:
    def test_pointing_the_root_at_the_VERIFIERS_tree_REFUSES(self, producer):
        # The exact defect, as a regression: the run was taken from the producer's tree, and
        # the verifier is handed its OWN. It must refuse — the tree it is looking at is not
        # the tree the run claims, and no amount of self-agreement makes it so.
        assert refused_at(producer.binding(), VERIFIER_TREE, HEAD)

    def test_it_refuses_at_the_MANIFEST_too_not_merely_the_commit(self, producer):
        # Belt and braces: even if a forger could line the commits up, the verifier's tree
        # does not hash to the producer's manifest.
        doc = run_gate(producer.binding(), VERIFIER_TREE)
        assert any(REDERIVES in g for g in doc["failed_gates"])

    def test_the_verifiers_identity_is_reported_SEPARATELY_and_is_its_own_modules(self):
        # `verifier_code_sha256` is WHICH CHECKER RAN — hashed over the verifier's own
        # modules. It is not, and may not become, a claim about the producer.
        assert len(verifier_code_sha256()) == 64
        assert verifier_code_sha256() != code_digest.run_binding()["manifest_sha256"]

    def test_a_RELEASE_GRADE_run_may_not_be_verified_from_the_PRODUCERS_OWN_tree(self):
        # THE SELF-CHECK MODE, closed. Everything lines up here — the root IS the tree the run
        # was taken from, so its HEAD is the bound commit and its manifest re-derives exactly.
        # And it is the tree the VERIFIER is running from, so the checker is hashing itself and
        # agreeing with itself. Self-agreement is not independence. For a lane that can SHIP,
        # the separation of the two trees is the claim, and it is enforced — not reported.
        code = code_digest.run_binding()               # the real repo: this very checkout
        doc = run_gate({"lane": "production", "code_identity": code}, VERIFIER_TREE)
        assert doc["verdict"] == "REFUSE"
        assert any(SUPPLIED in g for g in doc["failed_gates"])
        # ...and it refused on the SEPARATION, not because the tree failed to line up: the
        # commit and the manifest are this tree's own, and they match.
        assert not any(HEAD in g or REDERIVES in g for g in doc["failed_gates"])

    def test_the_report_says_out_loud_which_tree_was_hashed_as_the_producers(self, producer):
        separate = run_gate(producer.binding(), producer.root)
        assert separate["bound_artifact"][
            "producer_code_root_is_the_verifier_tree"] is False

    def test_a_SYNTHETIC_fixture_may_still_be_verified_in_tree(self):
        # The asymmetry is deliberate and is the one this codebase already draws everywhere
        # else (gate profiles, dirty trees): a synthetic bundle is a TEST INPUT, not a
        # provenance record, and the harness that builds it necessarily runs the producer out
        # of the checkout it is testing. Nothing ships from this lane.
        code = code_digest.run_binding()
        doc = run_gate({"lane": "synthetic", "code_identity": code}, VERIFIER_TREE)
        assert doc["verdict"] == "ADMIT", doc["failed_gates"]


# --------------------------------------------------------------------------- #
# THE DECLARED METADATA MAY NOT LIE ABOUT THE TREE IT DESCRIBES.
# --------------------------------------------------------------------------- #
class TestTheCodeIdentityMetadataIsRE_DERIVED_NotRead:
    """`manifest_sha256` binds the BYTES. The rest of the block — the recipe ids, the digest
    root, the file count, the dirty-path count — is prose the artifact wrote about itself, and
    every one of those fields is READ downstream and cited. A run that hashed 3 files honestly
    and then wrote `n_files: 141` beside the hash has an unfalsifiable-looking provenance
    record: the number a reader checks the tree against is the number the artifact chose.

    So they are re-derived from the walk, not read. Folded into the manifest gate — the claim
    is one claim ("this block describes THIS tree"), and it does not need its own gate name.
    """

    def test_an_INFLATED_n_files_resealed_REFUSES(self, producer):
        code = dict(producer.code_identity(), n_files=141)      # honest hash, invented count
        assert producer.code_identity()["n_files"] == 3
        assert refused_at({"lane": "production", "code_identity": code},
                          producer.root, REDERIVES)

    def test_a_FORGED_digest_root_resealed_REFUSES(self, producer):
        # "02_geneskew" is the tree this recipe is defined over. A block naming a different
        # root describes a different digest — and would still carry a hash that re-derives.
        code = dict(producer.code_identity(), digest_root="01_programs")
        assert refused_at({"lane": "production", "code_identity": code},
                          producer.root, REDERIVES)

    def test_a_SWAPPED_include_rule_id_resealed_REFUSES(self, producer):
        # The rule id says WHICH recipe produced the hash. Swap it and the same number now
        # claims to have come from a different, unstated rule.
        code = dict(producer.code_identity(),
                    include_rule_id="spot.stage02.code_digest.include_rule.py_only.v9")
        assert refused_at({"lane": "production", "code_identity": code},
                          producer.root, REDERIVES)

    def test_a_SWAPPED_digest_id_or_binding_rule_id_resealed_REFUSES(self, producer):
        for field in ("digest_id", "binding_rule_id"):
            code = dict(producer.code_identity(), **{field: "spot.something.else.v1"})
            assert refused_at({"lane": "production", "code_identity": code},
                              producer.root, REDERIVES), field

    def test_a_DIRTY_tree_understating_its_dirty_path_count_REFUSES(self, producer):
        # Honest about being dirty, dishonest about HOW dirty. "1 uncommitted path" beside a
        # tree with four is a provenance record that reads as a near-clean run.
        for rel in ("analysis/direct/run_arms.py", "analysis/direct/config.py"):
            producer.write(rel, "X = 'moved'\n")               # uncommitted
        code = producer.code_identity(require_clean=False)
        assert code["n_dirty_paths"] == 2
        lying = dict(code, n_dirty_paths=0)
        assert refused_at({"lane": "synthetic", "code_identity": lying},
                          producer.root, REDERIVES)

    def test_the_HONEST_block_still_ADMITS(self, producer):
        # the guard on all of the above: the real producer's own block passes every one
        assert run_gate(producer.binding(), producer.root)["verdict"] == "ADMIT"


# --------------------------------------------------------------------------- #
# THE REFUSALS: wrong HEAD, dirty tree, omitted root.
# --------------------------------------------------------------------------- #
class TestAProducerTreeThatIsNotTheOneTheRunClaims:
    def test_a_tree_whose_HEAD_MOVED_past_the_bound_commit_REFUSES(self, producer):
        binding = producer.binding()                    # bound at the ORIGINAL commit
        producer.write("analysis/direct/config.py", "METHOD_VERSION = '2'\n")
        moved = _commit(producer.repo, "a later commit")
        assert moved != binding["code_identity"]["commit"]
        assert refused_at(binding, producer.root, HEAD)

    def test_a_DIRTY_tree_calling_itself_clean_REFUSES(self, producer):
        # The self-consistent forgery: the artifact declares clean_tree=true, and the tree on
        # disk has uncommitted bytes. The digest beside that commit id identifies nothing.
        binding = producer.binding()
        assert binding["code_identity"]["clean_tree"] is True
        producer.write("analysis/direct/run_arms.py", "ARM = 'skew_away'\n")   # uncommitted
        assert refused_at(binding, producer.root, DECLARED)

    def test_a_release_grade_lane_REFUSES_an_HONESTLY_dirty_tree(self, producer):
        # Recorded honestly this time — the producer's own --allow-dirty-tree path
        # (clean_tree=false, clean_checkout_required=false). A production release still may
        # not stand on bytes that exist on somebody's disk and in no commit.
        producer.write("analysis/direct/run_arms.py", "ARM = 'skew_away'\n")   # uncommitted
        code = producer.code_identity(require_clean=False)
        assert code["clean_tree"] is False and code["clean_checkout_required"] is False
        binding = {"lane": "production", "code_identity": code}
        assert refused_at(binding, producer.root, RELEASE_DIRTY)

    def test_a_SYNTHETIC_lane_may_stand_on_an_honestly_declared_dirty_tree(self, producer):
        # The fixture lane is not a release. It must keep working from a working tree — and it
        # says so out loud, which is the difference between a dirty run and a dishonest one.
        producer.write("analysis/direct/run_arms.py", "ARM = 'skew_away'\n")   # uncommitted
        code = producer.code_identity(require_clean=False)
        assert code["clean_tree"] is False
        doc = run_gate({"lane": "synthetic", "code_identity": code}, producer.root)
        assert doc["verdict"] == "ADMIT", doc["failed_gates"]

    def test_a_STALE_manifest_at_the_right_commit_REFUSES(self, producer):
        # HEAD lines up and the tree is clean — and the manifest was taken over other bytes.
        # Only a RE-DERIVATION from the tree can tell: the commit id cannot.
        producer.write("analysis/direct/config.py", "METHOD_VERSION = '2'\n")
        moved = _commit(producer.repo, "the bytes moved")
        stale = producer.binding()["code_identity"]
        binding = {"lane": "production",
                   "code_identity": dict(stale, commit=moved,
                                         manifest_sha256="0" * 64,
                                         canonical_digest="0" * 16)}
        assert refused_at(binding, producer.root, REDERIVES)

    def test_an_OMITTED_producer_code_root_REFUSES_rather_than_ABSTAINS(self, producer):
        # Fail-closed. "We could not check" and "we checked and it was fine" must never reach
        # a reader as the same verdict — so a missing root is a REFUSAL, not a skipped gate.
        assert refused_at(producer.binding(), None, SUPPLIED)
        assert refused_at(producer.binding(), "", SUPPLIED)

    def test_a_root_that_is_not_a_GIT_CHECKOUT_REFUSES(self, producer, tmp_path):
        loose = tmp_path / "not_a_repo" / "02_geneskew"
        loose.mkdir(parents=True)
        assert refused_at(producer.binding(), str(loose), SUPPLIED)

    def test_every_code_identity_gate_still_RUNS_when_the_root_is_missing(self, producer):
        # A gate that cannot be evaluated FAILS; it does not vanish. The gate inventory is a
        # provenance record — a verifier that silently ran fewer gates would be a different
        # verifier wearing this one's name.
        supplied = run_gate(producer.binding(), producer.root)
        omitted = run_gate(producer.binding(), None)
        assert omitted["gate_inventory"] == supplied["gate_inventory"]
        assert omitted["verdict"] == "REFUSE"


# --------------------------------------------------------------------------- #
# THE CLI AND THE API: the root is REQUIRED, and it reaches the release lane.
# --------------------------------------------------------------------------- #
class TestTheRootIsRequiredEverywhereAVerdictIsReached:
    def test_the_bundle_CLI_REFUSES_to_parse_without_it(self):
        with pytest.raises(SystemExit):
            VB.build_parser().parse_args(
                ["--bundle", "b", "--de-main", "d", "--sgrna", "s"])

    def test_the_bundle_CLI_accepts_it(self):
        ns = VB.build_parser().parse_args(
            ["--bundle", "b", "--de-main", "d", "--sgrna", "s",
             "--producer-code-root", "/p/02_geneskew"])
        assert ns.producer_code_root == "/p/02_geneskew"

    def test_the_RELEASE_CLI_requires_it_too_and_hands_it_to_every_bundle(self):
        import verify_direct_release as VR

        with pytest.raises(SystemExit):
            VR.build_parser().parse_args(["--release", "r", "--de-main", "d",
                                          "--sgrna", "s"])
        ns = VR.build_parser().parse_args(
            ["--release", "r", "--de-main", "d", "--sgrna", "s",
             "--producer-code-root", "/p/02_geneskew"])
        assert ns.producer_code_root == "/p/02_geneskew"
        # the delegation: what each per-bundle verification is actually handed
        assert VR._bundle_args(ns, "b", "Rest").producer_code_root == "/p/02_geneskew"
