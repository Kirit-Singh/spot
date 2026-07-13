"""FIXTURE NAMESPACE. Pinned public response bytes, for offline tests only.

``fixtures_public/pinned_*.json`` are the EXACT, unmodified bytes returned by the
public APIs on 2026-07-12, fetched through the same canonical URLs
:mod:`druglink.acquire_public` builds:

  * UniProtKB search, release ``2026_02`` (``X-UniProt-Release`` header), CC BY 4.0;
  * ChEMBL REST, release ``ChEMBL_37`` (``status.json``), CC BY-SA 3.0.

They exist so the adapters can be tested against what the sources ACTUALLY return
rather than against what a document says they return. Two rules hold:

  * **No test opens a socket.** :class:`FakeTransport` serves these bytes and raises
    on any URL it was not given, so an unpinned request cannot silently escape.
  * **A fixture is never a scientific output.** These bytes are test inputs. The
    SYNTHETIC payloads below are stamped ``_spot_fixture`` precisely so that
    relabelling one as ``acquired_public`` is detectable, and the acquisition
    verifier refuses it.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

import pandas as pd

from druglink import direct_run, http_public as hp

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures_public")
FIXTURE_NAMESPACE = "fixture"

with open(os.path.join(FIXTURE_DIR, "_index.json"), "r", encoding="utf-8") as _fh:
    INDEX: dict[str, dict[str, Any]] = json.load(_fh)

# Real identities carried by the pinned bytes (asserted in the tests, not assumed).
CTLA4 = "ENSG00000163599"
IL2RA = "ENSG00000134460"
UNMAPPED = "ENSG00000000200"                 # a real "no results" UniProt response
CTLA4_ACCESSIONS = ("A0A8Q3SIR7", "A0A8Q3WKZ2", "P16410")
IL2RA_ACCESSIONS = ("A0A8V8TMM2", "H0Y5Z0", "P01589", "Q5W005", "Q5W006")
CTLA4_TARGET = "CHEMBL2364164"               # SINGLE PROTEIN
IL2RA_TARGET = "CHEMBL1778"                  # SINGLE PROTEIN
IL2_RECEPTOR_COMPLEX = "CHEMBL2364167"       # PROTEIN COMPLEX: never a gene lane
UNIPROT_RELEASE = "2026_02"
CHEMBL_RELEASE = "ChEMBL_37"                 # verbatim, as status.json capitalises it


def body(name: str) -> bytes:
    with open(os.path.join(FIXTURE_DIR, INDEX[name]["file"]), "rb") as fh:
        return fh.read()


def payload(name: str) -> dict[str, Any]:
    return json.loads(body(name).decode("utf-8"))


def url(name: str) -> str:
    return INDEX[name]["url"]


def headers(name: str) -> dict[str, str]:
    return dict(INDEX[name]["headers"])


def response(name: str) -> hp.Response:
    return hp.Response(url=url(name), status=200, headers=headers(name),
                       body=body(name))


class FakeTransport:
    """Serves pinned bytes by URL. An unpinned URL is an error, never a request.

    ``no_match_uniprot`` serves, for a UniProtKB search whose Ensembl id is NOT one of
    the pinned real genes, the EXACT bytes and headers UniProt genuinely returned for a
    nonexistent Ensembl cross-reference (``{"results":[]}``, ``x-total-results: 0``,
    release ``2026_02``). The Direct fixture's other targets are synthetic ``ENSG000000002xx``
    ids that really do have no UniProt entry, so an empty result is the TRUTHFUL answer
    for them — this is the observed no-match response, not an invented one. It is off by
    default; only the end-to-end run turns it on, and no drug evidence can come from it.
    """

    NO_MATCH = "uniprot_search_ENSG00000000200_empty"

    def __init__(self, names: Optional[Iterable[str]] = None, *,
                 no_match_uniprot: bool = False) -> None:
        self.by_url: dict[str, hp.Response] = {}
        self.calls: list[str] = []
        self.on_call = None                  # optional hook: fn(url) before serving
        self.no_match_uniprot = no_match_uniprot
        for name in (names if names is not None else INDEX):
            self.by_url[url(name)] = response(name)

    def __call__(self, request_url: str) -> hp.Response:
        if self.on_call is not None:
            self.on_call(request_url)
        self.calls.append(request_url)
        if request_url in self.by_url:
            return self.by_url[request_url]
        if self.no_match_uniprot and "/uniprotkb/search" in request_url:
            empty = response(self.NO_MATCH)
            return hp.Response(url=request_url, status=200,
                               headers=dict(empty.headers), body=empty.body)
        raise hp.HttpError(f"no pinned response for {request_url}")


def direct_double(ensgs: list[str], *, run_id: str = "fx00direct00double",
                  ranks: Optional[list[int]] = None) -> direct_run.DirectRun:
    """A Direct-run stand-in carrying REAL Ensembl IDs and test ranks.

    The gene IDs are real so the pinned public responses answer them; the ranks are
    test scaffolding. Nothing built from this object is a scientific artifact.
    """
    ranks = ranks or list(range(1, len(ensgs) + 1))
    rows = [{
        "released_estimate_id": f"est_{i:03d}", "target_id": ensg,
        "target_id_namespace": "ensembl_gene_id", "target_ensembl": ensg,
        "target_symbol": f"FXSYM{i}", "condition": "stim48",
        "away_from_A": 0.5 + i, "toward_B": 0.4 + i, "A_delta": 0.1, "B_delta": 0.2,
        "rank_away_from_A": rank, "rank_toward_B": rank,
        "A_evaluable": True, "B_evaluable": True,
        "A_evidence_tier": "tier_2", "B_evidence_tier": "tier_2",
        "A_desired_target_modulation": "decrease",
        "B_desired_target_modulation": "decrease",
    } for i, (ensg, rank) in enumerate(zip(ensgs, ranks))]
    screen = pd.DataFrame(rows)
    for col in ("rank_away_from_A", "rank_toward_B"):
        screen[col] = screen[col].astype("Int64")
    return direct_run.DirectRun(
        run_dir="<fixture-direct-double>", run_id=run_id, artifact_class="analysis",
        provenance={}, axis={}, verification={}, screen=screen, file_sha256={},
        verifier={}, binding={"stage3_namespace": "analysis",
                              "direct_run_id": run_id,
                              "direct_test_double": True})


# --------------------------------------------------------------------------- #
# synthetic payloads: stamped, so a relabel is detectable                       #
# --------------------------------------------------------------------------- #

def synthetic_chembl_mechanism(stamped: bool = True) -> bytes:
    doc: dict[str, Any] = {
        "mechanisms": [{
            "mec_id": 1, "molecule_chembl_id": "CHEMBLFIXTURE1",
            "target_chembl_id": "CHEMBLFIXTURETGT", "action_type": "INHIBITOR",
            "mechanism_of_action": "fixture inhibitor", "direct_interaction": 1,
            "mechanism_refs": [],
        }],
    }
    if stamped:
        doc["_spot_fixture"] = "synthetic payload; not a public response"
    return json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")
