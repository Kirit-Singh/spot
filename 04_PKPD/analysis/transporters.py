"""Transporter evidence.

"Is it a P-gp substrate?" is not answerable with a boolean. An efflux ratio of 3 in
MDCKII-MDR1 at 1 µM and a negative result in a mouse Abcb1a/b knockout study are two
observations, in two systems, at two concentrations, and collapsing them loses exactly
the information a reviewer needs. So this lane only ever aggregates by *listing*.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .evidence_records import TransporterObservation

# The two the brief requires be representable at minimum; others are not excluded.
REQUIRED_TRANSPORTERS = ("ABCB1_Pgp", "ABCG2_BCRP")


def transporter_summary(observations: list[TransporterObservation], candidate_id: str, prose: dict[str, Any]) -> dict[str, Any]:
    """Per-transporter evidence, never reduced to a single unqualified state."""
    rows = [o for o in observations if o.candidate_id == candidate_id]
    by_t: dict[str, list[TransporterObservation]] = defaultdict(list)
    for o in rows:
        by_t[o.transporter].append(o)

    per_transporter = []
    for t in sorted(by_t):
        obs = sorted(by_t[t], key=lambda o: o.observation_id)
        states = sorted({o.interaction for o in obs})
        per_transporter.append(
            {
                "transporter": t,
                "n_observations": len(obs),
                "observed_states": states,
                "state_is_ambiguous": len(states) > 1,
                "unqualified_boolean": None,
                "unqualified_boolean_note": prose["transporters"]["unqualified_boolean_note"],
                "observations": [
                    {
                        "observation_id": o.observation_id,
                        "interaction": o.interaction,
                        "assay": o.assay,
                        "species": o.species,
                        "biological_system": o.biological_system,
                        "concentration": o.concentration,
                        "concentration_units": o.concentration_units,
                        "result_metric": o.result_metric,
                        "result_value": o.result_value,
                        "result_units": o.result_units,
                        "direction": o.direction,
                        "evidence_type": o.evidence_type.value,
                        "source_record_id": o.provenance.source_record_id,
                        "raw_response_sha256": o.provenance.raw_response_sha256,
                    }
                    for o in obs
                ],
            }
        )

    covered = {r["transporter"] for r in per_transporter}
    return {
        "candidate_id": candidate_id,
        "transporters": per_transporter,
        "not_evaluated": [t for t in prose["transporters"]["required_transporters"]
                          if t not in covered],
        "interpretation_guard": prose["transporters"]["interpretation_guard"],
    }
