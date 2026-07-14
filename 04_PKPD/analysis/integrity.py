"""One referential-integrity pass over every id, before anything is computed.

The audit's finding: moiety identity was checked only for CNS-MPO properties, so potency,
context, exposure, transporter, NEBPI and label rows could all point at the wrong molecule
or the wrong regimen and still be scored. This module is the single foreign-key/uniqueness
sweep that runs before the lanes do.

It refuses; it does not repair. A dangling reference is a bad evidence set, not a row to
drop quietly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .firewall import Rejection


@dataclass(frozen=True)
class IntegrityReport:
    checked: int
    candidates: int
    contexts: int


def _dupes(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for i in ids:
        (dupes if i in seen else seen).add(i)
    return sorted(dupes)


def check_referential_integrity(inputs: Any) -> IntegrityReport:
    """Every id resolves, is unique, and every row agrees with the candidate it names."""
    cset = inputs.candidate_set
    candidates = {c.candidate_id: c for c in cset.candidates}
    moiety_of = {c.candidate_id: c.active_moiety.active_moiety_id for c in cset.candidates}
    contexts = {c.context_id: c for c in inputs.contexts}
    potencies = {p.potency_id: p for p in inputs.potencies}
    measurements = {m.measurement_id: m for m in inputs.exposures}
    sources = inputs.sources
    searches = {s.search_id for s in getattr(inputs, "search_manifests", [])}
    checked = 0

    # --- uniqueness ---------------------------------------------------------------
    # Every input row carries an identity, and an identity is supplied exactly once. An id
    # given twice is a malformed evidence set, whether the two rows agree or not: agreeing
    # duplicates are the same record asserted twice, and conflicting duplicates are two
    # records claiming to be one. Both are refused, so nothing downstream can pick.
    for label, ids in (
        ("candidate_id", [c.candidate_id for c in cset.candidates]),
        ("context_id", [c.context_id for c in inputs.contexts]),
        ("property_record_id", [p.property_record_id for p in inputs.properties]),
        ("potency_id", [p.potency_id for p in inputs.potencies]),
        ("measurement_id", [m.measurement_id for m in inputs.exposures]),
        ("observation_id", [o.observation_id for o in inputs.nebpi_observations]),
        ("transporter observation_id", [t.observation_id for t in inputs.transporters]),
        ("evidence_id", [s.evidence_id for s in inputs.safety_records]),
        ("link_id", [k.link_id for k in getattr(inputs, "potency_context_links", [])]),
        ("assignment_id", [a.assignment_id for a in inputs.delivery_assignments]),
        ("search_id", [s.search_id for s in getattr(inputs, "search_manifests", [])]),
    ):
        dupes = _dupes(ids)
        if dupes:
            raise Rejection("duplicate_id", f"duplicate {label}: {dupes}")
        checked += len(ids)

    def owns(row: Any, what: str) -> None:
        """A row must name a real candidate and carry that candidate's active moiety."""
        cid = row.candidate_id
        if cid not in candidates:
            raise Rejection("dangling_candidate_ref",
                            f"{what} refers to unknown candidate {cid!r}")
        am = getattr(row, "active_moiety_id", None)
        if am is not None and am != moiety_of[cid]:
            raise Rejection(
                "moiety_mismatch",
                f"{what} is bound to active moiety {am!r}, but candidate {cid!r} has "
                f"{moiety_of[cid]!r}. A salt, prodrug or metabolite is not the same molecule, "
                "and Stage 4 will not join across them.",
            )

    def ctx_of(row: Any, what: str):
        ctx = contexts.get(getattr(row, "context_id", None))
        if ctx is None:
            raise Rejection("dangling_context_ref",
                            f"{what} refers to unknown context {row.context_id!r}")
        if ctx.candidate_id != row.candidate_id:
            raise Rejection(
                "context_candidate_mismatch",
                f"{what} names context {ctx.context_id!r}, which belongs to candidate "
                f"{ctx.candidate_id!r}, not {row.candidate_id!r}",
            )
        return ctx

    # --- contexts -----------------------------------------------------------------
    for ctx in inputs.contexts:
        owns(ctx, f"context {ctx.context_id!r}")
        checked += 1

    # --- properties / potencies / transporters ------------------------------------
    for r in inputs.properties:
        owns(r, f"property {r.property_id!r} ({r.candidate_id})")
        checked += 1
    for p in inputs.potencies:
        owns(p, f"potency {p.potency_id!r}")
        checked += 1
    for t in inputs.transporters:
        owns(t, f"transporter observation {t.observation_id!r}")
        checked += 1

    # --- exposures: the measurement must agree with the context it names -----------
    from .exposure import check_context_agreement

    for m in inputs.exposures:
        owns(m, f"exposure {m.measurement_id!r}")
        ctx = ctx_of(m, f"exposure {m.measurement_id!r}")
        mismatched = check_context_agreement(m, ctx)
        if mismatched:
            raise Rejection(
                "measurement_context_disagreement",
                f"exposure {m.measurement_id!r} does not match the regimen of the context it "
                f"names ({ctx.context_id!r}): " + "; ".join(mismatched),
            )
        checked += 1

    # --- delivery assignments ------------------------------------------------------
    for a in inputs.delivery_assignments:
        owns(a, f"delivery assignment ({a.candidate_id})")
        ctx_of(a, f"delivery assignment ({a.candidate_id})")
        checked += 1

    # --- NEBPI observations: every link must resolve to a real, matching row --------
    for o in inputs.nebpi_observations:
        owns(o, f"NEBPI observation {o.observation_id!r}")
        ctx_of(o, f"NEBPI observation {o.observation_id!r}")
        if o.measurement_id is not None:
            m = measurements.get(o.measurement_id)
            if m is None:
                raise Rejection(
                    "dangling_measurement_ref",
                    f"NEBPI observation {o.observation_id!r} names measurement "
                    f"{o.measurement_id!r}, which does not exist",
                )
            if m.candidate_id != o.candidate_id or m.context_id != o.context_id:
                raise Rejection(
                    "observation_measurement_mismatch",
                    f"NEBPI observation {o.observation_id!r} names a measurement from a "
                    "different candidate/context",
                )
        if o.potency_id is not None:
            p = potencies.get(o.potency_id)
            if p is None:
                raise Rejection(
                    "dangling_potency_ref",
                    f"NEBPI observation {o.observation_id!r} names potency {o.potency_id!r}, "
                    "which does not exist",
                )
            if p.candidate_id != o.candidate_id:
                raise Rejection(
                    "observation_potency_mismatch",
                    f"NEBPI observation {o.observation_id!r} names a potency belonging to "
                    f"candidate {p.candidate_id!r}",
                )
        checked += 1

    # --- potency-context links -----------------------------------------------------
    # A link is the ONLY way a potency measured in one tumour context may be used in
    # another, so it is a result-affecting scientific claim. Its potency must exist, and
    # exactly one link may relate a given potency to a given context — otherwise the
    # margin's cited link_id would depend on which row was scanned first.
    seen_pairs: dict[tuple[str, str], str] = {}
    for link in getattr(inputs, "potency_context_links", []):
        if link.potency_id not in potencies:
            raise Rejection("dangling_potency_ref",
                            f"potency-context link {link.link_id!r} names unknown potency "
                            f"{link.potency_id!r}")
        pair = (link.potency_id, link.tumor_context)
        if pair in seen_pairs:
            raise Rejection(
                "duplicate_potency_context_link",
                f"links {seen_pairs[pair]!r} and {link.link_id!r} both relate potency "
                f"{link.potency_id!r} to tumour context {link.tumor_context!r}. Exactly one "
                "sourced relevance link may do so; two would make the cited link depend on "
                "row order.",
            )
        seen_pairs[pair] = link.link_id
        checked += 1

    # --- delivery assignments: the reduction must be able to see a conflict ---------
    # (ownership is checked above; the permutation-invariant reducer in delivery_reduce.py
    # turns >1 distinct assignment for one context into `conflicting_assignments`, so a
    # duplicate here is not silently resolved.)

    # --- safety rows ----------------------------------------------------------------
    for s in inputs.safety_records:
        owns(s, f"safety evidence {s.evidence_id!r}")
        if s.search_id and s.search_id not in searches:
            raise Rejection(
                "dangling_search_manifest",
                f"safety row {s.evidence_id!r} claims no_evidence_found via search "
                f"{s.search_id!r}, which has no SearchManifest",
            )
        checked += 1

    # --- every provenance points at a source that exists AND has bytes ---------------
    from .pipeline import provenance_bindings

    for owner, prov in provenance_bindings(inputs):
        rec = sources.get(prov.source_record_id)
        if rec is None:
            raise Rejection("unbound_source_record",
                            f"{owner}: unknown source_record_id {prov.source_record_id!r}")
        if rec.source_class == "not_acquired":
            raise Rejection(
                "evidence_from_unacquired_source",
                f"{owner} cites source {rec.source_record_id!r}, which was never acquired. "
                "There are no bytes behind it, so there is no evidence behind the row.",
            )
        if rec.raw_sha256 != prov.raw_response_sha256:
            raise Rejection(
                "source_hash_mismatch",
                f"{owner}: raw_response_sha256 does not match source record "
                f"{prov.source_record_id!r}",
            )
        checked += 1

    return IntegrityReport(checked=checked, candidates=len(candidates), contexts=len(contexts))
