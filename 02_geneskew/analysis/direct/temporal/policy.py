"""The LOCKED batch-confound policy, loaded from a hash-pinned diagnostic artifact.

WHY A TABLE AND A RULE, NOT A LIST OF BLESSED PAIRS
---------------------------------------------------
The artifact carries what was MEASURED — which donor sat in which sequencing replicate
at each condition — and this module DERIVES the confound flag from it:

    a pair is batch_partially_confounded  <->  some donor sits in a different replicate
                                               at the two endpoints.

When every donor keeps its replicate, the batch offset attaches to the same donors at
both endpoints and cancels in the difference-of-differences; time is then not confounded
with batch. When a donor moves, it does not cancel for that donor, and the pair is
flagged.

For the pinned GWCD4i release this derivation reproduces the locked verdict exactly —
Rest<->Stim8hr clean (identical composition), every Stim48hr pair confounded (D1 and D2
flip R1->R2, D3 and D4 do not) — without this code ever naming a condition. A release
with a different design therefore gets a correct answer rather than a stale one, and a
hard-coded allowlist that silently went wrong is not a failure mode this can have.

NOTHING IS EVER REFUSED. A confounded pair is flagged, badged and emitted. Withholding
it would hide the confound instead of reporting it, and a reader cannot audit a
comparison that was never written down.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from ..hashing import file_sha256

POLICY_FILE = "batch_policy.v1.json"
SCHEMA_VERSION = "spot.stage02_temporal_batch_policy.v1"

# The typed batch statuses. UNKNOWN is deliberately NOT clean.
BATCH_CLEAN = "batch_balanced_identical_composition"
BATCH_PARTIALLY_CONFOUNDED = "batch_partially_confounded"
BATCH_COMPOSITION_UNKNOWN = "batch_composition_unknown_for_condition"
BATCH_STATUSES = (BATCH_CLEAN, BATCH_PARTIALLY_CONFOUNDED, BATCH_COMPOSITION_UNKNOWN)

CONFOUND_RULE_ID = "spot.stage02.temporal.rule.donor_replicate_flip.v1"


class PolicyError(ValueError):
    """The policy artifact is absent, malformed, or not the one that was locked."""


class BatchPolicy:
    """The frozen policy, and the small set of questions the estimator asks it."""

    def __init__(self, doc: dict[str, Any], path: str, sha256: str) -> None:
        self._doc = doc
        self.path = path
        self.sha256 = sha256
        self.policy_id = doc["policy_id"]
        self.verdict = doc["verdict"]
        self.provenance = doc["provenance"]
        self.additive_batch = doc["additive_batch"]
        self.interaction_floor_source = doc["interaction_floor_source"]
        self.not_identifiable = doc["not_identifiable"]
        self.confound_rule = doc["confound_rule"]
        self.donor_code_map = doc["donor_code_map"]
        self._composition = doc["condition_composition"]
        self._interaction_std = doc["interaction_std"]
        self.sparse_panel_caution_programs = tuple(
            doc["sparse_panel_caution_programs"])
        self.sparse_panel_caution_reason = doc["sparse_panel_caution_reason"]

    # ---- conditions -------------------------------------------------------- #
    @property
    def conditions(self) -> list[str]:
        """The conditions whose composition was measured, in a stable order."""
        return sorted(self._composition)

    def ordered_pairs(self, conditions: Optional[list[str]] = None
                      ) -> list[tuple[str, str]]:
        """EVERY ordered pair, both directions. Six of them for three conditions."""
        conds = sorted(conditions) if conditions is not None else self.conditions
        return [(a, b) for a in conds for b in conds if a != b]

    def composition(self, condition: str) -> Optional[dict[str, str]]:
        entry = self._composition.get(condition)
        return None if entry is None else dict(entry["donor_replicate"])

    # ---- THE RULE ---------------------------------------------------------- #
    def classify_pair(self, from_condition: str, to_condition: str) -> dict[str, Any]:
        """Is time confounded with batch across this ordered pair, and for whom?

        Symmetric by construction: which donors moved does not depend on which way the
        pair is read, so a direction cannot be used to escape a flag.
        """
        a = self.composition(from_condition)
        b = self.composition(to_condition)
        base: dict[str, Any] = {
            "confound_rule_id": CONFOUND_RULE_ID,
            "batch_correction_applied": False,
            # NOTHING is refused. The flag is the product; suppression is not.
            "refused": False,
            "not_identifiable_quantity": self.not_identifiable["quantity"],
            "not_identifiable_reason": self.not_identifiable["reason"],
        }
        if a is None or b is None:
            missing = [c for c, comp in ((from_condition, a), (to_condition, b))
                       if comp is None]
            return dict(base,
                        batch_status=BATCH_COMPOSITION_UNKNOWN,
                        # NOT False. An unmeasured composition has not been cleared,
                        # and a null flag cannot be read as a clean bill of health.
                        batch_partially_confounded=None,
                        donors_changing_replicate=[],
                        donors_keeping_replicate=[],
                        donors_only_at_one_condition=[],
                        batch_status_reason=(
                            "no measured donor/replicate composition for "
                            f"{sorted(missing)}"))

        shared = sorted(set(a) & set(b))
        only_one = sorted(set(a) ^ set(b))
        moved = [d for d in shared if a[d] != b[d]]
        kept = [d for d in shared if a[d] == b[d]]
        confounded = bool(moved or only_one)
        return dict(
            base,
            batch_status=(BATCH_PARTIALLY_CONFOUNDED if confounded else BATCH_CLEAN),
            batch_partially_confounded=confounded,
            donors_changing_replicate=moved,
            donors_keeping_replicate=kept,
            donors_only_at_one_condition=only_one,
            batch_status_reason=(
                (f"donors {moved} sit in a different replicate at the two endpoints"
                 if moved else
                 f"donors {only_one} are present at only one endpoint")
                if confounded else
                "every donor keeps its replicate at both endpoints, so the batch "
                "offset attaches to the same donors and cancels in the DiD"),
        )

    # ---- the interaction floor --------------------------------------------- #
    def interaction_std(self, program_id: str) -> Optional[float]:
        """This program's donor/batch interaction spread, or None if never measured.

        None is not a pass. A program with no measured floor cannot clear one, and the
        badge says exactly that rather than defaulting to reliable.
        """
        v = self._interaction_std.get(program_id)
        return None if v is None else float(v)

    def sparse_panel_caution(self, program_id: str) -> bool:
        return program_id in self.sparse_panel_caution_programs

    # ---- provenance -------------------------------------------------------- #
    def block(self) -> dict[str, Any]:
        """The policy, as it is bound into the temporal method hash and emitted."""
        return {
            "policy_id": self.policy_id,
            "policy_sha256": self.sha256,
            "verdict": self.verdict,
            "provenance": dict(self.provenance),
            "confound_rule": dict(self.confound_rule),
            "condition_composition": json.loads(json.dumps(self._composition)),
            "donor_code_map": dict(self.donor_code_map),
            "additive_batch": dict(self.additive_batch),
            "interaction_floor_source": dict(self.interaction_floor_source),
            "interaction_std": dict(self._interaction_std),
            "sparse_panel_caution_programs": list(self.sparse_panel_caution_programs),
            "sparse_panel_caution_reason": self.sparse_panel_caution_reason,
            "not_identifiable": dict(self.not_identifiable),
        }


_REQUIRED = ("policy_id", "verdict", "provenance", "condition_composition",
             "confound_rule", "additive_batch", "interaction_floor_source",
             "interaction_std", "sparse_panel_caution_programs",
             "sparse_panel_caution_reason", "not_identifiable", "donor_code_map")


def load(path: Optional[str] = None) -> BatchPolicy:
    """Load and validate the frozen policy artifact.

    A malformed or absent policy is fatal. There is no built-in default: a temporal run
    with no confound policy would be a run that never asked the question.
    """
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                POLICY_FILE)
    if not os.path.exists(path):
        raise PolicyError(f"no temporal batch policy at {path}")
    with open(path) as fh:
        doc = json.load(fh)
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise PolicyError(
            f"batch policy schema is {doc.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION!r}")
    missing = [k for k in _REQUIRED if k not in doc]
    if missing:
        raise PolicyError(f"batch policy is missing required fields: {missing}")
    for cond, entry in doc["condition_composition"].items():
        if not entry.get("donor_replicate"):
            raise PolicyError(
                f"condition {cond!r} declares no donor/replicate composition; the "
                "confound rule is derived from it and cannot be evaluated without it")
    return BatchPolicy(doc, path=path, sha256=file_sha256(path))
