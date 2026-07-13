"""What a fetch has to be able to SHOW before its bytes count as evidence.

(W9's contract types, verbatim from `56864a0`. They live here rather than in `acquisition.py`
because BOTH lanes wrote a module of that name: W8's is the acquisition MECHANISM — RunRoot,
fetch, cache, `AcquisitionRecord` — and is canonical, byte-identical to `b287f72`. Two models of
one concept in one file is exactly the ambiguity a provenance system cannot afford, so the
mechanism keeps the name and the CONTRACT takes W9's own `*_records.py` convention, beside
`pk_records.py`, `assay_records.py` and `safety_records.py`.)

Stage 4 has no network code and this module adds none. It is the typed record an acquisition
would have to produce — the thing a reviewer re-runs a year later to get the same bytes.

The audit's finding, in one line: `SourceRecord` recorded an access **date**, no canonical
query, no terms URL, no HTTP status and no adapter build. So a source could be re-fetched only
approximately, its terms were an adjective rather than a document, and a parser bugfix could
change every extracted value while the bytes, the transform string and the hash all stayed put.

Four separable things are kept separate here, because collapsing any two of them loses a fact:

  raw_sha256        the exact bytes that came back
  content_sha256    the stable scientific content inside a volatile envelope (the PMC BioC
                    endpoint stamps the retrieval date into every response, so an UNCHANGED
                    paper hashes differently every day)
  extraction_transform   WHAT was taken out of those bytes
  adapter_code_sha256    WHICH build took it out

`observation_state` is the fifth: it is the difference between "we looked and found nothing",
"nobody looked", and "the sources disagree" — three sentences that a single null would render
identical.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .canonical import content_sha256
from .contracts import ID_PATTERN, SHA256_PATTERN, Strict

# RFC-3339, UTC, to the second. A DATE is not a timestamp: a database that publishes twice a
# day cannot be pinned to a day, and "which release did you actually read" is the question the
# whole record exists to answer.
UTC_TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"

# A terms URL is a document you can read, not an adjective. `license: "Public domain"` is the
# exact overclaim the audit found in the ledger for DailyMed and ClinicalTrials.gov.
_URL = re.compile(r"^https?://[^\s]+$")

# Never hashed into a public artifact, never written to disk. A response header set is useful
# provenance (etag, last-modified, content-type, an API's release header); a credential in it
# is a leak, and an artifact that carries one cannot be published.
CREDENTIAL_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "x-auth-token", "authentication",
})


class EvidenceObservationState(str, Enum):
    """The five states the audit requires. A null is not one of them.

    `NOT_EVALUATED` and `NOT_FOUND_AFTER_SEARCH` are the pair that matters most: "nobody
    looked" and "we ran this exact query against this exact release and it came back empty"
    are different scientific claims, and only the second one is evidence.
    """

    OBSERVED = "observed"
    NOT_EVALUATED = "not_evaluated"
    NOT_FOUND_AFTER_SEARCH = "not_found_after_reproducible_search"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"


class ReviewStatus(str, Enum):
    """Who, if anyone, checked that the extraction says what the source says."""

    NOT_REVIEWED = "not_reviewed"
    MACHINE_EXTRACTED = "machine_extracted"
    HUMAN_REVIEWED = "human_reviewed"
    DUAL_REVIEWED = "dual_independently_reviewed"
    DISPUTED = "disputed"


class SourceAcquisitionRecord(Strict):
    """One response, and everything needed to get it again and prove what was read out of it."""

    acquisition_id: str = Field(pattern=ID_PATTERN)
    # The `SourceRecord` these bytes belong to. One source record is one response.
    source_record_id: str = Field(pattern=ID_PATTERN)

    request_url: str
    # The exact, reproducible query — not "I searched ChEMBL". Method + path + sorted params.
    #
    # `materialize` used to substitute `rec.source_key` when the query was absent — writing the
    # STRING "chembl" where a reproducible query belongs. A source key is not a query: nobody can
    # re-issue it, and a provenance field that cannot be re-issued is decoration.
    canonical_query: str = Field(min_length=1)
    # Stage 3 stores its canonical query as a HASH, not as text. Carried as a hash, never
    # reconstructed as text — and never dropped, which is what happened.
    canonical_query_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    # WHICH Stage-3 source record these bytes came from. Dropped in materialization, so a reused
    # response could no longer name the upstream row it was carried from.
    stage3_source_record_id: Optional[str] = None
    # WHO performed the exchange. A reused Stage-3 response was fetched by STAGE 3: Stage 4 holds
    # its bytes and its hash, but never made the request, so it has no HTTP status and no access
    # time of its own. Without this field the record cannot tell the difference between "nobody
    # observed this" and "somebody upstream observed it and I am carrying their bytes", and the
    # validators below cannot judge it honestly.
    origin: Literal["fetched_public", "reused_from_stage3"] = "fetched_public"

    # The time STAGE 4 performed this access -- or absent, when it performed none.
    #
    # This was required, so a reused Stage-3 response (whose access time Stage 3 does not record)
    # had nowhere honest to go. Upstream filled the hole with `1970-01-01`, which is not a missing
    # value but a fabricated provenance claim, and the chain then crashed converting it to "".
    # A time that no source states is now stated as ABSENT, with the reason, and the bytes stay
    # pinned by the hashes that actually identify them.
    accessed_at_utc: Optional[str] = Field(default=None, pattern=UTC_TIMESTAMP_PATTERN)
    # REQUIRED whenever `accessed_at_utc` is absent. An unexplained blank is indistinguishable
    # from a value nobody bothered to record; a stated reason is auditable.
    access_time_not_stated_reason: Optional[str] = None

    http_status: Optional[int] = Field(default=None, ge=100, le=599)
    raw_media_type: Optional[str] = None
    # A SELECTED subset: etag / last-modified / content-type / an API's release header.
    response_headers: dict[str, str] = Field(default_factory=dict)

    # The source's own statement of which release this is: a version, or an API `last_updated`.
    release_or_last_updated: Optional[str] = None
    # The exact terms document. An adjective ("public domain") is refused.
    license_or_terms_url: Optional[str] = None
    license_exception_note: Optional[str] = None

    raw_bytes: Optional[int] = Field(default=None, ge=0)
    raw_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    # The stable content identity when the transport envelope is volatile. Equal to
    # `raw_sha256` when it is not.
    content_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    content_hash_rule: Optional[str] = None

    extraction_transform: str = Field(min_length=1)
    adapter_id: str = Field(pattern=ID_PATTERN)
    adapter_code_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)

    review_status: ReviewStatus
    observation_state: EvidenceObservationState

    # --- how a SINGLE record was chosen among the ones the query MATCHED.
    #
    # The vocabulary here is `analysis/selection.py`'s, not a second one invented next to it:
    # a selection is `exactly_one` (matched on an identity PIN, with zero and many both typed
    # refusals) or `sorted_unique` (collect-all in canonical order, nothing dropped, nothing
    # chosen). There is no third option and there is no `results[0]`.
    #
    # `match_total_reported` is the SOURCE's own count of what its query matched, and
    # `records_returned` is what actually arrived. A `limit=1` makes those differ — which is why
    # it did not merely risk the wrong record, it removed the evidence that would have shown the
    # risk. A truncated result set cannot prove uniqueness, so it cannot be `observed`.
    # THREE dispositions, because there are three genuinely different things an adapter can do:
    #
    #   identity_get   the request NAMED one record by its stable id (GET /spls/{setid}.xml,
    #                  /compound/cid/{cid}/...). There is NO RESULT SET, so truncation is not
    #                  possible and completeness is a property of the ENDPOINT, not of a count.
    #                  Marking these `exactly_one` and asserting completeness would be asserting a
    #                  source total nobody reported — an assumption dressed as a proof.
    #   exactly_one    a SELECTION over a result set, matched on an identity pin. Uniqueness must
    #                  be DEMONSTRATED: the source's own match total against what actually arrived.
    #                  A truncated page cannot prove uniqueness.
    #   sorted_unique  a collect-all in canonical order. Nothing chosen, nothing dropped.
    selection_disposition: Optional[
        Literal["identity_get", "exactly_one", "sorted_unique"]] = None
    selection_pin: Optional[str] = None
    match_total_reported: Optional[int] = Field(default=None, ge=0)
    records_returned: Optional[int] = Field(default=None, ge=0)
    result_set_complete: Optional[bool] = None

    # Required by `not_found_after_reproducible_search`: the SearchManifest whose acquired
    # bytes ARE the empty response.
    search_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    conflict_note: Optional[str] = None
    not_applicable_reason: Optional[str] = None

    @property
    def has_bytes(self) -> bool:
        return bool(self.raw_sha256)

    @model_validator(mode="after")
    def _rules(self) -> "SourceAcquisitionRecord":
        self._check_urls()
        self._check_headers()
        self._check_content_hash()
        self._check_state()
        self._check_selection()
        if not self.adapter_code_sha256:
            raise ValueError(
                f"acquisition {self.acquisition_id!r}: adapter_code_sha256 is required. The "
                "extraction transform says WHAT was taken out of the bytes; only the adapter "
                "hash says WHICH build took it out — a parser repair changes the extracted "
                "value while the bytes, the transform and the response hash all stay identical."
            )
        return self

    def _check_urls(self) -> None:
        if not _URL.match(self.request_url):
            raise ValueError(f"request_url is not a URL: {self.request_url!r}")
        if self.license_or_terms_url is not None and not _URL.match(self.license_or_terms_url):
            raise ValueError(
                f"license_or_terms_url must be the exact terms DOCUMENT, not a licence name: "
                f"got {self.license_or_terms_url!r}. 'Public domain' is an assertion; "
                "https://open.fda.gov/terms/ is a thing a reviewer can read."
            )

    def _check_headers(self) -> None:
        leaked = sorted(h for h in self.response_headers if h.lower() in CREDENTIAL_HEADERS)
        if leaked:
            raise ValueError(
                f"acquisition {self.acquisition_id!r} carries credential header(s) {leaked}. "
                "Response headers are provenance and get written into a public artifact; a "
                "credential in one is a leak, not a header."
            )

    def _check_content_hash(self) -> None:
        if self.content_sha256 and self.raw_sha256 and self.content_sha256 != self.raw_sha256:
            if not self.content_hash_rule:
                raise ValueError(
                    f"acquisition {self.acquisition_id!r}: content_sha256 differs from "
                    "raw_sha256 but no content_hash_rule declares the normalisation. A content "
                    "hash whose rule is unstated is not reproducible — state exactly what was "
                    "blanked (e.g. the BioC envelope's retrieval <date>)."
                )
        if self.content_sha256 and not self.raw_sha256:
            raise ValueError("content_sha256 without raw_sha256: there are no bytes to normalise")

    def _check_access_time(self) -> None:
        """A time nobody stated is stated as absent -- never blank, never invented."""
        if self.accessed_at_utc:
            if self.access_time_not_stated_reason:
                raise ValueError(
                    "accessed_at_utc is present AND a not-stated reason is given. One of them is "
                    "false; a record cannot both know and not know when it was accessed."
                )
            return
        if not (self.access_time_not_stated_reason or "").strip():
            raise ValueError(
                "accessed_at_utc is absent and nothing says why. An unexplained blank is "
                "indistinguishable from a value nobody bothered to record. State the reason -- "
                "e.g. the upstream stage acquired these bytes and does not record a timestamp -- "
                "and pin the response by raw_sha256 + release instead. Do NOT invent a time."
            )

    def _check_state(self) -> None:
        st = self.observation_state
        self._check_access_time()
        if st == EvidenceObservationState.OBSERVED:
            self._require_bytes("observed")
            # A response STAGE 4 fetched must show a 2xx: a 404 or a challenge page has bytes too,
            # and they are not an observation of the thing that was asked for.
            #
            # A response STAGE 3 fetched has no Stage-4 HTTP status, because Stage 4 made no
            # request. Demanding one here is what forced the upstream fabrications -- an invented
            # epoch, an empty-string timestamp. What Stage 4 CAN stand behind is the bytes and
            # their hash, and `_require_bytes` already insists on those.
            if self.origin == "fetched_public" and (
                    self.http_status is None or not (200 <= self.http_status < 300)):
                raise ValueError(
                    f"observed requires a 2xx HTTP status (got {self.http_status!r}). A 404 or a "
                    "challenge page has bytes too; they are not an observation of the thing that "
                    "was asked for."
                )
            if self.origin == "reused_from_stage3" and self.http_status is not None:
                raise ValueError(
                    "a reused_from_stage3 response carries an HTTP status, but Stage 4 made no "
                    "request for it. A status Stage 4 did not receive is not Stage 4's to report."
                )
            if self.search_id:
                raise ValueError("search_id is only meaningful for "
                                 "not_found_after_reproducible_search")
        elif st == EvidenceObservationState.NOT_FOUND_AFTER_SEARCH:
            if not self.search_id:
                raise ValueError(
                    "not_found_after_reproducible_search requires a search_id -> a SearchManifest "
                    "(canonical query, endpoint, release, scope, the hash of the empty response). "
                    "Without it, 'we looked and found nothing' is the same sentence as 'nobody "
                    "looked', and only one of them is evidence."
                )
            self._require_bytes("not_found_after_reproducible_search")
        elif st == EvidenceObservationState.NOT_EVALUATED:
            if self.has_bytes or self.raw_bytes or self.content_sha256:
                raise ValueError(
                    "not_evaluated means nobody looked, so there are no bytes; a hash here would "
                    "be a fiction. If a query WAS run and came back empty, the state is "
                    "not_found_after_reproducible_search."
                )
        elif st == EvidenceObservationState.CONFLICTING:
            if not self.conflict_note:
                raise ValueError(
                    "conflicting requires conflict_note: which sources disagree, and about what. "
                    "An unstated conflict cannot be adjudicated or reproduced."
                )
        elif st == EvidenceObservationState.NOT_APPLICABLE:
            if not self.not_applicable_reason:
                raise ValueError("not_applicable requires not_applicable_reason")

    def _check_silence_is_allowed(self) -> None:
        """A row that states NO disposition must earn that silence. (W9 closeout, A2.)

        This rule used to live only in `materialize`, and `_check_selection` simply RETURNED when
        the disposition was null. But materialize is not the only producer: the v2 bundle door
        validates SourceAcquisitionRecord directly, so a HAND-AUTHORED observed fetched row with no
        proof at all walked through the model, through the door, and into a release — past a gate
        that existed and was correct, by not going through it.

        A guard on the writer is not a guarantee about the artifact. This is the record CONTRACT, so
        it holds for every producer that can ever construct one: the pipeline, the bundle door, a
        test, a future adapter, or a document somebody typed by hand.

        Silence is admissible in exactly two cases, and neither is "we fetched it and said nothing":

          * NOT OBSERVED. A `not_evaluated` / `not_found_after_search` row selected nothing at all.
            Demanding a selection proof from a lane nobody looked at is demanding evidence of an
            absence.
          * REUSED FROM STAGE 3. Stage 3 issued the query; Stage 4 holds the bytes but never made
            the request and cannot attest to a selection it never performed. The proof is DELEGATED
            — and delegation is only honest if the record NAMES what it delegates to. Without
            `stage3_source_record_id` the row is not delegating, it is just quiet.

        A fetched, observed row is the one case where Stage 4 DID the selecting. It has no one to
        delegate to and nothing to be silent about.
        """
        if self.observation_state != EvidenceObservationState.OBSERVED:
            return

        if self.origin == "reused_from_stage3":
            if not self.stage3_source_record_id:
                raise ValueError(
                    f"acquisition {self.acquisition_id!r} is an OBSERVED row reused from Stage 3 "
                    "with no selection_disposition and no stage3_source_record_id. Stage 4 did not "
                    "issue this query, so it may DELEGATE the selection proof upstream — but it "
                    "must name the upstream record it is delegating to. A row that delegates to "
                    "nobody has not delegated; it has simply declined to say how its record was "
                    "chosen, which is the thing this field exists to prevent."
                )
            return

        raise ValueError(
            f"acquisition {self.acquisition_id!r} is an OBSERVED, Stage-4-fetched row that states "
            "NO selection_disposition. Stage 4 issued this request and chose this record, so there "
            "is no upstream to delegate to. Silence is not a disposition: a record picked by "
            "POSITION (`results[0]`) is indistinguishable from one pinned by IDENTITY until the row "
            "says which it was, and every selection rule in this contract is bypassed by a row that "
            "asserts nothing. State `identity_get`, `exactly_one`, or `sorted_unique`."
        )

    def _check_selection(self) -> None:
        """The record must be able to show that its selection was not a pick.

        These are `selection.py`'s guarantees, restated as invariants of the artifact, so that a
        selection which never had them cannot be written down as though it did.
        """
        if self.selection_disposition is None:
            self._check_silence_is_allowed()
            return

        # An IDENTITY GET has no result set. The request named one record by its stable id, and the
        # endpoint returns that record or nothing — there is nothing to truncate and no total to
        # report. Completeness here is a property of the ENDPOINT, and it is stated as such rather
        # than inferred from a count the source never sent.
        #
        # It still must name the identity it fetched: a GET with no pin is a GET of nothing.
        if self.selection_disposition == "identity_get":
            if not self.selection_pin:
                raise ValueError(
                    "selection_disposition='identity_get' must name the stable id it fetched. A "
                    "request that cannot say which record it asked for cannot say it got that one."
                )
            if self.match_total_reported is not None:
                raise ValueError(
                    "an identity GET has no result set, so a `match_total_reported` is a count of "
                    "something that does not exist. If the endpoint DID return a result set, the "
                    "disposition is `exactly_one` and uniqueness must be demonstrated."
                )
            if self.result_set_complete is not None:
                raise ValueError(
                    "an identity GET has no result set, so `result_set_complete` has nothing to be "
                    "true OR false ABOUT. Setting it True is a completeness boolean invented for an "
                    "endpoint that reports no total — the same assumption-dressed-as-proof this "
                    "field exists to prevent. Leave it null."
                )
            return

        if self.selection_disposition == "exactly_one" and not self.selection_pin:
            raise ValueError(
                "selection_disposition='exactly_one' must name the identity PIN it matched on. "
                "Matching on position is not matching on identity, and `results[0]` is a bet "
                "that the result set had one element -- a bet that fails silently, on the one "
                "drug where it matters."
            )

        total, returned = self.match_total_reported, self.records_returned
        if self.result_set_complete:
            if total is None or returned is None or total != returned:
                raise ValueError(
                    f"result_set_complete=True but the source reported {total!r} matching "
                    f"record(s) and {returned!r} arrived. Completeness is the source's own total "
                    "agreeing with what we can actually see; it is not a flag to be asserted."
                )
        elif total is not None and returned is not None and total == returned:
            raise ValueError(
                "the source's total equals what arrived, so the result set IS complete; saying "
                "otherwise understates the evidence"
            )

        # The `limit=1` failure, closed. A response that says `total: 7` and hands back 1 row has
        # not shown us the other 6, so nothing about that row can be called unique -- and an
        # observation is exactly a claim that we saw the thing we asked for.
        if (self.observation_state == EvidenceObservationState.OBSERVED
                and self.selection_disposition == "exactly_one"
                and not self.result_set_complete):
            raise ValueError(
                f"acquisition {self.acquisition_id!r} claims to have observed exactly one "
                f"record, but the result set is not complete (source total="
                f"{total!r}, returned={returned!r}). A truncated page cannot prove uniqueness. "
                "Raise the query limit or pin the record explicitly; do not read the rows that "
                "happened to arrive. If the candidates genuinely cannot be separated, the state "
                "is 'conflicting' and it names the conflict."
            )

    def _require_bytes(self, state: str) -> None:
        if not self.raw_sha256 or not self.raw_bytes:
            raise ValueError(
                f"{state} requires the bytes it rests on: raw_sha256 and a non-zero raw_bytes. "
                "A response nobody kept cannot be re-checked."
            )


class SourceAcquisitionManifest(Strict):
    """The content-addressed set of acquisitions behind one evidence bundle.

    `manifest_content_sha256` is a hash of the RECORDS, not of their order: a re-serialisation
    that permutes them is the same manifest, and a single changed bound field is not.
    """

    manifest_id: str = Field(pattern=ID_PATTERN)
    records: list[SourceAcquisitionRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> "SourceAcquisitionManifest":
        seen_acq: set[str] = set()
        seen_src: set[str] = set()
        for r in self.records:
            if r.acquisition_id in seen_acq:
                raise ValueError(f"duplicate acquisition_id {r.acquisition_id!r}: a row id is "
                                 "supplied once, so nothing downstream can pick")
            seen_acq.add(r.acquisition_id)
            if r.source_record_id in seen_src:
                raise ValueError(
                    f"source_record_id {r.source_record_id!r} is acquired twice. One source "
                    "record is one response; two acquisitions for it would let a reader choose "
                    "which bytes the evidence rests on."
                )
            seen_src.add(r.source_record_id)
        return self

    @property
    def manifest_content_sha256(self) -> str:
        rows = sorted((r.model_dump(mode="json") for r in self.records),
                      key=lambda r: r["acquisition_id"])
        return content_sha256(rows)

    def by_source_record_id(self) -> dict[str, SourceAcquisitionRecord]:
        return {r.source_record_id: r for r in self.records}
