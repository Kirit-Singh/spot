"""The missing bridge: an ADMITTED acquisition -> the typed Stage-4 evidence bundle.

`run_acquire` writes `acquisition_manifest.json` + raw bytes under a run root. `run_stage4`
consumes a `spot.stage04_evidence_bundle.v1/v2` document. Nothing joined them, so the pipeline
had no production path from acquired public bytes to a scorecard set at all: every green run was
scoring a fixture. This module is that join, and it is deterministic — the same manifest over the
same bytes produces a byte-identical bundle.

WHAT IT WILL NOT DO, because these are the ways a PK/safety artifact lies:

  * **Fabricate a lane it could not acquire.** Every lane with no acquired evidence is stated
    `not_evaluated`, with the reason, in `config.not_evaluated` — which is hashed into
    `scorecard_set_id`. An absence is part of the release's identity, not a gap in it.
  * **Infer brain exposure or safety from missing data.** There is no public adapter for a brain
    concentration, an efflux ratio or an fu. Those lanes materialize EMPTY, and a candidate with
    no observation is `not_classifiable` — never "impermeable", never "safe". Absence of an
    exposure measurement is not evidence of impermeability.
  * **Complete CNS-MPO from what PubChem happens to have.** PubChem supplies neither ClogD(7.4)
    nor most-basic pKa, and its XLogP3 is not Wager's BioByte ClogP. Descriptors are carried
    under their own calculator's name; whether any may serve as a CNS-MPO input is the calculator
    policy's decision, in the engine. CNS-MPO stays INCOMPLETE rather than being finished with a
    substitute.
  * **Accept fixture evidence.** A `synthetic_fixture` record is refused outright. A materialized
    bundle is made of bytes a reviewer can fetch again.
  * **Bind a label to the wrong molecule.** The identity match is proven (UNII / moiety name), not
    hoped for. A safety finding attached to the wrong drug is the worst artifact this stage could
    produce.
  * **Infer an organ system.** `organ_system` is whatever a source's own coded field states, or
    `unspecified`. `ORGAN_SYSTEM_SPECS` is empty, and that emptiness IS the finding.

Determinism: every list is sorted, ids are content-derived rather than arrival-ordered, and no
wall clock is read. The only timestamps are the ones the acquisition records already carry, which
are themselves part of the acquired evidence.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal, Optional, cast

from .acquisition import AcquisitionManifest, AcquisitionRecord, RunRoot
from .acquisition_records import EvidenceObservationState, ReviewStatus, SourceAcquisitionRecord
from .canonical import content_sha256
from .contract_version import BUNDLE_SCHEMA, ContractVersion
from .contracts import SourceRecord

if TYPE_CHECKING:
    from .contracts import AcquisitionStatus
from .firewall import Rejection
from .label_adapters import parse_dailymed_spl
from .organ_system import extract_organ_system
from .pubchem import parse_properties
from .safety import safety_rows_from_label

MATERIALIZER_ID = "spot.stage04.materializer.v1"

# The lanes a PUBLIC acquisition can populate today, and the ones it provably cannot. This table
# is the honest statement of Stage 4's reach, and every "no" below is a stated absence in the
# emitted bundle rather than an empty list a reader might mistake for "nothing was wrong".
LANE_REACH: dict[str, Optional[str]] = {
    "properties": None,                 # PubChem: MW/TPSA/HBD/XLogP3 (never ClogD7.4 or pKa)
    "safety_records": None,             # DailyMed SPL: labelled findings
    "source_acquisition": None,         # every response this bundle stands on
    "contexts": (
        "a dosing context (route, formulation, dose, schedule, tumour context) is a study "
        "design, not a public record. No public source states one."
    ),
    "potencies": (
        "potency is reused from the admitted Stage-3 bundle when Stage 3 acquired it; Stage 4 "
        "never re-queries ChEMBL, and no other public source in the ledger reports an IC50."
    ),
    "potency_context_links": (
        "a link asserts that a potency measured in one tumour context applies in another. No "
        "public source states that; it is an expert judgement and Stage 4 does not make it."
    ),
    "exposures": (
        "no public source in the ledger reports a brain-tissue, CSF or microdialysate "
        "concentration for a candidate. Absence of an exposure measurement is NOT evidence of "
        "impermeability."
    ),
    "transporters": (
        "no public source in the ledger reports an ABCB1/ABCG2 efflux ratio. A label's absence "
        "of a transporter statement is not a negative result."
    ),
    "delivery_assignments": (
        "the delivery requirement is assigned from Stage-3 mechanism evidence by a declared "
        "rule, not acquired. A public acquisition supplies no assignment."
    ),
    "nebpi_observations": (
        "an NEBPI criterion observation requires a measured exposure or a radiographic/PD "
        "endpoint. Neither is acquirable from a public label or a chemistry API, so no candidate "
        "is NEBPI-classifiable from this bundle alone."
    ),
    "search_manifests": (
        "a negative search is only evidence when the query, endpoint, release and empty-response "
        "hash are all recorded. This acquisition ran no such search."
    ),
    "fraction_unbound": (
        "fu is not reported by any public source in the ledger. It is never assumed to be 1."
    ),
}


class MaterializationError(Rejection):
    """The acquisition cannot honestly become an evidence bundle."""


def _refuse_fixture_evidence(manifest: AcquisitionManifest) -> None:
    fixtures = sorted(r.acquisition_record_id for r in manifest.records
                      if r.origin == "synthetic_fixture")
    if fixtures:
        raise MaterializationError(
            "fixture_evidence_in_materialized_bundle",
            f"{len(fixtures)} acquisition record(s) are synthetic_fixture: {fixtures[:3]}. A "
            "materialized bundle is made of bytes a reviewer can fetch again. A fixture may be "
            "run through the engine (`run_stage4 --fixtures`); it may never be laundered into a "
            "bundle that looks acquired.",
        )


def _source_record(rec: AcquisitionRecord) -> SourceRecord:
    """One acquisition response -> one SourceRecord. The bytes keep their own identity."""
    return SourceRecord(
        source_record_id=rec.acquisition_record_id,
        source_type=rec.source_type,
        source_name=rec.source_name,
        # DERIVED from whether bytes exist, never asserted. Stage 3's own registry contains
        # `not_acquired` rows -- a source it names but never fetched. Stamping `acquired_public`
        # on every record would launder those into public sources that carry no bytes, which is
        # precisely the claim `acquired_public` is supposed to make checkable.
        acquisition_status=cast(
            "AcquisitionStatus",
            "acquired_public" if rec.raw_sha256 else "not_acquired"),
        # The locator that makes the response re-fetchable. A public source must carry one: it
        # cannot simply declare itself public.
        record_id=rec.stable_record_id,
        access_date=rec.access_date,
        raw_sha256=rec.raw_sha256,
        raw_bytes=rec.raw_bytes,
        url=rec.url,
        license=rec.license,
        raw_media_type=rec.raw_media_type,
        release_version=rec.release_or_last_updated,
    )


def _selection(rec: AcquisitionRecord) -> dict[str, Any]:
    """The selection proof, READ from the record. Never inferred, never defaulted.

    THE DEFECT THIS REPLACES. This used to decide a fetch was "by identity" if `stable_record_id`
    happened to appear as a SUBSTRING of `canonical_query`, and then FABRICATE the proof:

        match_total_reported = 1, records_returned = 1, result_set_complete = True

    For an openFDA SEARCH that is simply false. The source may have reported forty matches and
    handed back one — `meta.results.total` says so — and this record would have sworn the result set
    was complete. A fabricated completeness claim is worse than an absent one: it is the exact
    truncation these fields exist to expose, wearing the proof's clothes. And a substring test is
    not a proof of anything; a query that merely CONTAINS an id is not a query FOR that id.

    The source's own numbers now travel with the bytes from the fetch. `None` means the source
    reported no total, and `None` is what is carried — never 1.
    """
    return {
        "selection_disposition": rec.selection_disposition,
        "selection_pin": rec.selection_pin,
        "match_total_reported": rec.match_total_reported,
        "records_returned": rec.records_returned,
        # NEVER `bool(...)`. An identity GET has no result set, so `result_set_complete` is null —
        # and `bool(None)` rewrites that honest null into `False`, which reads as "we looked and the
        # result set was INCOMPLETE". That is a different claim from "there was no result set", and
        # it is a claim the endpoint never made. Absent stays absent, end to end.
        "result_set_complete": rec.result_set_complete,
    }


def _assert_selection_proven(rec: AcquisitionRecord) -> None:
    """An OBSERVED row must be able to say how its record was selected.

    `selection_disposition = None` bypassed every selection rule: the row asserted nothing, so
    nothing could refuse it, and a record picked by position was indistinguishable from one pinned
    by identity. Silence is not a disposition.

    Only `observed` rows are held to this. A `not_evaluated` row selected nothing, and demanding a
    selection proof from a lane nobody looked at would be demanding evidence of an absence.
    """
    if rec.evidence_state != "observed":
        return
    if rec.selection_disposition:
        return

    # A REUSED response was selected by STAGE 3, not by Stage 4 — the same shape as the access
    # time. Stage 4 did not issue the query and cannot state a disposition for it, so the proof is
    # DELEGATED, and delegation is only honest if the record can NAME what it is delegating to.
    # `stage3_source_record_id` is that name, and the record contract already requires it.
    #
    # Fabricating a disposition here would be the original defect in a new costume; DEMANDING one
    # would be demanding that Stage 4 attest to a selection it never made.
    if rec.origin == "reused_from_stage3":
        if rec.stage3_source_record_id:
            return
        raise MaterializationError(
            "reused_row_cannot_name_its_upstream_selection",
            f"acquisition record {rec.acquisition_record_id!r} is a reused Stage-3 response with no "
            "`selection_disposition` AND no `stage3_source_record_id`. Stage 4 did not select it, so "
            "it cannot attest to how it was selected — but it must at least name the upstream row "
            "whose selection it is standing on. An unnamed delegation is not a delegation.",
        )

    raise MaterializationError(
        "acquisition_row_without_selection_proof",
        f"acquisition record {rec.acquisition_record_id!r} was FETCHED by Stage 4, is OBSERVED, and "
        "states no `selection_disposition`. It cannot say whether its record was pinned by identity "
        "(`exactly_one`) or collected in full (`sorted_unique`) — so a record chosen by position is "
        "indistinguishable from one chosen by name, and no selection rule can refuse it. Silence is "
        "not a disposition. The adapter must record how it selected, and the source's own match "
        "total: it is read at fetch time and must not be discarded.",
    )


def _why_no_access_time(rec: AcquisitionRecord) -> str:
    """Stated, not blank. The record already carries the reason when Stage 3 reused it."""
    if rec.access_time_not_stated_reason:
        return rec.access_time_not_stated_reason
    return (
        f"no access timestamp is recorded for this {rec.origin} response. Stage 4 did not perform "
        "the access and will not invent a time; the bytes are pinned by raw_sha256 and the "
        "source's own release instead."
    )


def _acquisition_row(rec: AcquisitionRecord) -> SourceAcquisitionRecord:
    _assert_selection_proven(rec)
    state = (EvidenceObservationState.OBSERVED if rec.evidence_state == "observed"
             else EvidenceObservationState(rec.evidence_state))
    return SourceAcquisitionRecord(
        acquisition_id=rec.acquisition_record_id,
        source_record_id=rec.acquisition_record_id,
        # `synthetic_fixture` is refused by `_refuse_fixture_evidence` before any row is
        # built, so only the two real origins reach here.
        origin=cast('Literal["fetched_public", "reused_from_stage3"]', rec.origin),
        request_url=rec.url or "",
        # NEVER `or rec.source_key`. A source key is not a query: nobody can re-issue "chembl",
        # and a provenance field that cannot be re-issued is decoration. Stage 3 stores its query
        # as a HASH, so a reused record carries the hash and says the text is upstream's.
        canonical_query=(rec.canonical_query
                         or f"upstream_canonical_query_sha256:{rec.canonical_query_sha256}"),
        canonical_query_sha256=rec.canonical_query_sha256,
        stage3_source_record_id=rec.stage3_source_record_id,
        # NEVER `or ""`. A missing time converted to an empty string is how a fabricated epoch
        # became a crash instead of a caught lie. The absence travels, with its reason.
        accessed_at_utc=rec.accessed_at_utc,
        access_time_not_stated_reason=(None if rec.accessed_at_utc else _why_no_access_time(rec)),
        http_status=rec.http_status,
        raw_media_type=rec.raw_media_type,
        response_headers=dict(sorted(rec.response_headers.items())),
        release_or_last_updated=rec.release_or_last_updated,
        license_or_terms_url=rec.license_or_terms_url,
        raw_bytes=rec.raw_bytes,
        raw_sha256=rec.raw_sha256,
        content_sha256=rec.content_sha256,
        content_hash_rule=rec.content_hash_rule,
        extraction_transform=rec.extraction_transform,
        adapter_id=MATERIALIZER_ID,
        adapter_code_sha256=rec.adapter_code_sha256,
        # A machine read these bytes and no human has checked the extraction. That is the
        # honest state, and it is carried into the release rather than left to be assumed.
        review_status=ReviewStatus.MACHINE_EXTRACTED,
        observation_state=state,
        **_selection(rec),
    )


# ------------------------------------------------------------------------ the evidence lanes

# WHERE THE SCIENTIFIC LINE IS, and it is the whole reason this module exists.
#
# CNS-MPO takes six inputs. PubChem can honestly supply three of them: molecular weight, TPSA and
# the hydrogen-bond donor count are the same physical quantity whoever computes them.
#
# It CANNOT supply the other three, and the difference is not pedantry:
#
#   clogp            PubChem reports XLogP3. Wager's ClogP is BioByte's. They are different
#                    estimators of the same idea and they disagree; substituting one for the other
#                    silently changes the score while looking like the same number.
#   clogd_74         PubChem does not have it. Nothing public in the ledger does.
#   pka_most_basic   PubChem does not have it. Nothing public in the ledger does.
#
# So three inputs are sourced, three are stated absent, and CNS-MPO comes out INCOMPLETE. That is
# the correct answer. A complete CNS-MPO built on XLogP3 would be a fabrication wearing the shape
# of a result.
# PubChem name -> (CNS-MPO property id, the unit the source reports it in). The unit travels with
# the value: a magnitude whose unit is guessed downstream is not a measurement.
PUBCHEM_TO_CNS_MPO = {
    "MolecularWeight": ("mw", "g/mol"),
    "TPSA": ("tpsa", "A^2"),
    "HBondDonorCount": ("hbd", "count"),
}

# Reported by PubChem, and deliberately NOT mapped to a CNS-MPO slot.
PUBCHEM_NOT_A_CNS_MPO_INPUT = {
    "XLogP": (
        "PubChem reports XLogP3. Wager 2010's ClogP is BioByte's, and the two estimators "
        "disagree. Mapping XLogP3 onto `clogp` would complete CNS-MPO with a different quantity "
        "than the method defines, so it is carried nowhere and `clogp` stays unsourced."
    ),
}

# The CNS-MPO inputs no public source in the ledger supplies. Stated, every run.
CNS_MPO_UNSOURCEABLE = {
    "clogp": PUBCHEM_NOT_A_CNS_MPO_INPUT["XLogP"],
    "clogd_74": (
        "no public source in the ledger reports a calculated logD at pH 7.4. Wager used "
        "ACD/Labs. CNS-MPO therefore stays incomplete rather than being completed with a guess."
    ),
    "pka_most_basic": (
        "no public source in the ledger reports a most-basic pKa. Wager used ACD/Labs. CNS-MPO "
        "therefore stays incomplete rather than being completed with a guess."
    ),
}


def _property_rows(rec: AcquisitionRecord, raw: bytes, candidate_id: str,
                   moiety_id: str) -> list[dict[str, Any]]:
    """PubChem descriptors -> property rows. Exactly what PubChem reported, nothing completed.

    The value stays the EXACT source string: a magnitude re-rounded on the way in can never be
    checked against the source again.

    `accepted` is deliberately NOT set here. Whether a PubChem descriptor may serve as a Wager
    CNS-MPO input is the CALCULATOR POLICY's decision, made in the engine against
    `method/calculator_policy_v1.json`. The materializer's job is to say what was sourced and by
    which calculator; deciding acceptance here would let the acquisition layer quietly complete a
    score the method says it cannot complete.
    """
    identity = parse_properties(raw, rec.stable_record_id or "")
    prov = {
        "source_record_id": rec.acquisition_record_id,
        "access_date": rec.access_date,
        "raw_response_sha256": rec.raw_sha256,
        "extraction_transform": rec.extraction_transform,
        "source_url": rec.url,
        "release_version": rec.release_or_last_updated,
    }

    rows = []
    for name, value in sorted(identity.descriptors.items()):
        mapped = PUBCHEM_TO_CNS_MPO.get(name)
        if mapped is None:
            continue          # not a CNS-MPO input -- see PUBCHEM_NOT_A_CNS_MPO_INPUT
        prop, unit = mapped
        rows.append({
            "property_record_id": f"prop.{rec.acquisition_record_id}.{prop}",
            "candidate_id": candidate_id,
            "active_moiety_id": moiety_id,
            "property_id": prop,
            "value_source_string": value,
            "units": unit,
            # PubChem's descriptors are COMPUTED, not measured. Calling them experimental would
            # dress a prediction up as an observation.
            "determination": "predicted",
            # The calculator is part of the method, not an implementation detail: Wager's ClogP is
            # BioByte's. PubChem's XLogP3 is a DIFFERENT quantity, and it is carried under its own
            # name so nothing downstream can mistake one for the other.
            "calculator_id": f"pubchem::{name}",
            "method": f"PubChem PUG REST computed property ({name})",
            "provenance": prov,
        })
    return rows


def _safety_rows(rec: AcquisitionRecord, raw: bytes, candidate_id: str, moiety_id: str,
                 unii: Optional[str], moiety_name: Optional[str]) -> list[dict[str, Any]]:
    """A DailyMed SPL -> one row per labelled finding, with the subsection it was read from."""
    parsed = parse_dailymed_spl(raw)
    if not rec.access_date:
        # A label STAGE 4 fetched must know when it fetched it -- unlike a reused upstream response,
        # nobody else holds that fact. An absent date here is a defect in the fetch, not an honest
        # gap in the world, and it is refused rather than blanked.
        raise MaterializationError(
            "fetched_label_without_access_date",
            f"acquisition record {rec.acquisition_record_id!r} is a label Stage 4 fetched, but "
            "carries no access date. Stage 4 performed this access; only Stage 4 can state when.",
        )
    rows = safety_rows_from_label(
        parsed, candidate_id, moiety_id, rec.acquisition_record_id,
        rec.access_date,
        rec.extraction_transform,
        expected_unii=unii, expected_moiety_name=moiety_name,
    )
    # organ_system is whatever a source's own CODED field states, or `unspecified`. It is never
    # inferred from a finding's wording — a hepatic warning does not make the row `hepatic`.
    # `ORGAN_SYSTEM_SPECS` is empty: no source in the ledger carries a coded organ-system field.
    # That emptiness IS the finding, and it is recorded on every row rather than hidden.
    evidence = extract_organ_system(parsed, source_key=rec.source_key)

    out = []
    for r in rows:
        row = json.loads(r.model_dump_json())
        row["organ_system_evidence"] = asdict(evidence)
        out.append(row)
    return out


# ------------------------------------------------------------------------------- the bundle

def materialize(admission: Any, manifest: AcquisitionManifest, run_root: RunRoot,
                version: ContractVersion = ContractVersion.V2) -> dict[str, Any]:
    """-> the evidence bundle document `run_stage4 --evidence-bundle` consumes.

    Deterministic: every list is sorted by id, every id is content-derived, and no wall clock is
    read. The same manifest over the same bytes produces the same document, byte for byte.
    """
    _refuse_fixture_evidence(manifest)

    cset = admission.candidate_set
    if cset is None or not cset.candidates:
        raise MaterializationError(
            "no_admitted_candidate",
            "the Stage-3 bundle admitted no candidate, so there is nothing to acquire evidence "
            "FOR. An evidence bundle with no candidate is not an empty result; it is not a "
            "result at all.",
        )

    sources: dict[str, Any] = {}
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANE_REACH}

    # Stage-3's own source records ride across untouched: Stage 3 acquired those bytes and has its
    # own provenance for them. Stage 4 never re-queries ChEMBL or UniProt.
    for sid, rec in sorted(getattr(admission, "source_records", {}).items()):
        sources[sid] = json.loads(rec.model_dump_json())

    by_moiety = {c.candidate_id: c for c in cset.candidates}

    for rec in sorted(manifest.records, key=lambda r: r.acquisition_record_id):
        sources[rec.acquisition_record_id] = json.loads(_source_record(rec).model_dump_json())

        # The acquisition lane is every RESPONSE this bundle stands on. A Stage-3 row marked
        # `not_acquired` is not a response: nobody fetched it, there are no bytes, and Stage 3
        # writes the literal string "not_acquired" where a URL would be. It belongs in `sources`
        # as not_acquired -- which it now is -- and NOT in a lane whose every row asserts that a
        # request was made and answered. Inventing a request URL for it would be the same class of
        # fabrication as inventing the access time.
        if not rec.raw_sha256:
            continue

        lanes["source_acquisition"].append(
            json.loads(_acquisition_row(rec).model_dump_json()))

        if rec.evidence_state != "observed" or not rec.cache_relpath:
            continue                     # nothing was read out of it; it is provenance, not data

        candidate = _candidate_for(rec, by_moiety)
        if candidate is None:
            continue                     # a reference probe: acquired, recorded, never a candidate

        raw = run_root.read(rec.cache_relpath)
        cid = candidate.candidate_id
        mid = _moiety_id(candidate)

        if rec.source_key.startswith("pubchem"):
            lanes["properties"].extend(_property_rows(rec, raw, cid, mid))
        elif rec.source_key.startswith("dailymed"):
            lanes["safety_records"].extend(
                _safety_rows(rec, raw, cid, mid,
                             _unii(candidate), _moiety_name(candidate)))
        # openfda: an approval/application cross-check. It carries identity, not an evidence lane.
        # rxnorm: an identity crosswalk. Same.

    return _document(cset, lanes, sources, manifest, version)


def _document(cset: Any, lanes: dict[str, list[dict[str, Any]]], sources: dict[str, Any],
              manifest: AcquisitionManifest, version: ContractVersion) -> dict[str, Any]:
    """Sort everything, and state every absence."""
    doc: dict[str, Any] = {"schema_id": BUNDLE_SCHEMA[version],
                           "sources": dict(sorted(sources.items()))}

    stated: list[dict[str, Any]] = []
    for lane, why in sorted(LANE_REACH.items()):
        rows = lanes.get(lane) or []
        doc[lane] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
        if rows:
            continue
        stated.append({
            "lane": lane,
            "evidence_state": "not_evaluated",
            "reason": why or (
                "no acquired response in this run contributed a row to this lane"),
        })

    # Every absence the acquisition itself declared, carried across verbatim.
    for m in sorted(manifest.missing, key=lambda m: (m.lane, m.reason)):
        stated.append(json.loads(m.model_dump_json()))

    doc["config"] = {
        "materializer": MATERIALIZER_ID,
        "acquisition_manifest_sha256": content_sha256(manifest.content()),
        "acquisition_run_id": manifest.run_id,
        "stage3_binding": dict(sorted(manifest.stage3_binding.items())),
        # Hashed into scorecard_set_id: an absence is part of what identifies this release, not a
        # gap in it. Silently dropping a lane could never change the id; stating it must.
        "not_evaluated": sorted(stated, key=lambda s: (s["lane"], s["reason"])),
    }
    return doc


# ------------------------------------------------------------------------------ small helpers

def _candidate_for(rec: AcquisitionRecord, by_id: dict[str, Any]) -> Any:
    """The candidate these bytes are evidence FOR — read from the record's own typed field.

    This used to GUESS: match `stage3_source_record_id` (which identifies a Stage-3 SOURCE, not a
    candidate) against the candidate id, or test whether `source_key` happened to end with the
    active-moiety's name. A freshly fetched PubChem/DailyMed/openFDA response satisfies neither, so
    every record acquired for a real queued candidate was silently treated as unmatched and
    contributed nothing — while the receipt called the probe `candidate_identity`.

    Now the acquisition layer STAMPS `candidate_id` on the record, and this reads it. A record with
    no candidate is a reference probe (temozolomide, acquired to prove an adapter works): recorded
    as provenance, and never reported as a candidate.

    An unknown candidate_id is REFUSED rather than dropped. Silently ignoring evidence that names a
    candidate this bundle does not contain would hide a genuine mismatch between the acquisition
    and the admitted bundle.
    """
    if not rec.candidate_id:
        return None
    candidate = by_id.get(rec.candidate_id)
    if candidate is None:
        raise MaterializationError(
            "acquisition_candidate_not_admitted",
            f"acquisition record {rec.acquisition_record_id!r} was acquired for candidate "
            f"{rec.candidate_id!r}, which is not in the admitted Stage-3 bundle. The evidence and "
            "the bundle disagree about who the candidates are; Stage 4 will not quietly attach it "
            "to something else, nor quietly drop it.",
        )
    return candidate


def _moiety_id(candidate: Any) -> str:
    moiety = getattr(candidate, "active_moiety", None)
    return getattr(moiety, "active_moiety_id", None) or candidate.candidate_id


def _moiety_name(candidate: Any) -> Optional[str]:
    moiety = getattr(candidate, "active_moiety", None)
    return getattr(moiety, "active_moiety_name", None)


def _unii(candidate: Any) -> Optional[str]:
    moiety = getattr(candidate, "active_moiety", None)
    return getattr(moiety, "unii", None)
