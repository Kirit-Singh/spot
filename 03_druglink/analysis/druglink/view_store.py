"""THE BYTES THE VIEW IS A PROJECTION OF — RE-DERIVED, NEVER COPIED.

A hash you COPY is not a hash you CHECKED.

The v2 document publishes a ``table_hashes`` block: one content hash per table, eight of them.
A materializer that copies that block into its view is not binding anything — it is
*republishing a digest about bytes it never looked at*. Project a MUTATED row and the view still
carries the OLD hash: the document says one thing, the rows say another, and the view says the
document. Every check downstream then verifies the copy against itself and passes.

So before a single row is projected:

  1. the DOCUMENT must hash to the identity it publishes (it cannot vouch for the tables if it
     cannot vouch for itself);
  2. all EIGHT tables (:data:`druglink.artifacts_v2.SCIENTIFIC_TABLES` — the producer's own
     list, restated nowhere) are RE-HASHED from the rows in hand, and must equal what the
     document declares;
  3. the same eight are RE-READ OFF DISK from the store the document claims to be, re-hashed
     there too, and must equal the same declaration — a document whose ``table_hashes`` name
     bytes that are not in the store names nothing;
  4. the rows in hand must be the rows on disk CELL FOR CELL, including the display-only columns
     that content hashes deliberately exclude;
  5. the store's own manifest must bind the document presented, and must hash to its own
     published identity (the B6 rule: an artifact that never recomputes its own id can be
     handed a forged one).

A mismatch is a NAMED REFUSAL. Never a warning, never a reconciliation, and never "use the
recomputed one": if the bytes and the declaration disagree, WHICH ONE IS THE SCIENCE is exactly
the question nobody can answer afterwards.

THE SECOND INVARIANT: THE STORE IS SELECTION-INDEPENDENT, AND THE LEAK IS SILENT
-------------------------------------------------------------------------------
The global store holds REUSABLE arms. If one question's identity — a ``selection_id``, a
``question_id``, an A/B role — leaks into it, the store has quietly become the answer to ONE
question, and every other question is either wrong or a re-run. Nothing fails: the bundle still
verifies, the tables still hash, the ids still reproduce. So the store is scanned RECURSIVELY,
over KEYS AND VALUES, at every depth — not just role columns and table headers, because a leak
arrives in a nested block written by the next author, not in the column list someone is watching.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Iterator, Mapping, Sequence

from . import artifacts_v2 as av2
from . import bundle_v2 as bv2
from . import edges_v2 as ev2
from . import stage2_aggregate as sa
from .hashing import content_hash, without

STORE_IDENTITY_VERIFIER_ID = "spot.stage03.selection_view.store_identity.v1"

# The one annotation the projection stamps on a row. Defined HERE, where the store's refusal of
# it lives, so the column the view adds and the column the store forbids cannot drift apart.
ROLE_COLUMN = "selection_roles"

GATE_NO_STORE_ON_DISK = "the_view_was_asked_to_project_a_store_whose_bytes_nobody_verified"
GATE_DOCUMENT_IDENTITY = "the_document_does_not_hash_to_the_identity_it_publishes"
GATE_TABLE_HASHES_INCOMPLETE = "the_document_does_not_name_a_hash_for_every_table_in_the_store"
GATE_TABLES_ARE_NOT_THE_HASHED_BYTES = \
    "the_tables_in_hand_are_not_the_bytes_the_documents_hashes_name"
GATE_STORE_ON_DISK_DIFFERS = \
    "the_documents_table_hashes_name_bytes_that_are_not_in_the_store_on_disk"
GATE_MANIFEST_BINDS_OTHER_BYTES = \
    "the_store_manifest_binds_a_document_that_is_not_the_one_presented"
GATE_ROLE_IN_THE_STORE = "a_selection_role_leaked_into_the_global_store"
GATE_SELECTION_IN_THE_STORE = "a_selection_identity_leaked_into_the_global_store"


class ViewRefusal(ValueError):
    """A named, fail-closed refusal. No view is produced and nothing is written."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


class StoreIdentityError(ViewRefusal):
    """The store in hand is not the store the document names."""


def _refuse(gate: str, message: str) -> None:
    raise StoreIdentityError(gate, message)


# --------------------------------------------------------------------------- #
# 1. THE LEAK SCAN. Recursive, over KEYS and VALUES, at any depth.
# --------------------------------------------------------------------------- #
# The identities of a QUESTION. A release that names one holds one question's answer.
IDENTITY_TOKENS: tuple[str, ...] = ("selection_id", "question_id")

# The A/B role vocabulary, taken from the producer's own tuple so the two cannot drift. `role`
# and `pole` are included as bare tokens because a leak arrives named `arm_role`, `ab_role` or
# `pole_of_a` at least as often as it arrives spelled `away_from_A`.
ROLE_TOKENS: tuple[str, ...] = tuple(sorted(
    {r.lower() for r in ev2.SELECTION_ROLES} | {"away_from", "toward_", "role", "pole",
                                                ROLE_COLUMN, "selection_role"}
    # AN A/B ASSIGNMENT IS A ROLE EVEN WHEN IT NEVER SAYS "ROLE". `a_arm_key`, `arm_b`,
    # `b_program_id` name ONE question's poles just as surely as `away_from_A` does — and a scan
    # that only knew the word "role" would wave every one of them through.
    | {f"{side}_{noun}" for side in ("a", "b")
       for noun in ("arm", "arm_key", "program", "program_id", "pole", "direction", "condition")}
    | {f"{noun}_{side}" for side in ("a", "b")
       for noun in ("arm", "arm_key", "program", "program_id", "pole", "direction", "condition")}))

# On a VALUE, only the PRECISE role vocabulary counts. A value that SAYS `away_from_A` is naming
# a role; a value containing the English word "role" is prose, and a scan that refused prose
# would be turned off within a week — which is how a check stops protecting anything.
ROLE_VALUE_TOKENS: tuple[str, ...] = tuple(sorted(
    {r.lower() for r in ev2.SELECTION_ROLES} | {"away_from", "toward_"}))

# A DECLARATION OF ABSENCE IS NOT A LEAK — but only while it still declares absence. Each of
# these says "no role was assigned here", and each is permitted at its declared value ONLY. Flip
# one and the store is announcing the very thing it promised not to hold, so the flip refuses.
NEGATIVE_DECLARATIONS: dict[str, Any] = {
    "selection_roles_assigned": False,
    "pair_roles_assigned": False,
    "selection_roles_are_assigned_at_join_time_not_in_this_bundle": True,
}


def _walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any, str]]:
    """Every KEY and every VALUE in the tree, with the path that reaches it."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield "key", key, f"{path}.{key}"
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")
    else:
        yield "value", node, path


def _leak(where: str, kind: str, node: Any, path: str) -> None:
    if kind == "key":
        low = str(node).lower()
        if str(node) in NEGATIVE_DECLARATIONS:
            return                      # a declaration of ABSENCE; its value is checked below
        token = next((t for t in IDENTITY_TOKENS if t in low), None)
        if token:
            _refuse(GATE_SELECTION_IN_THE_STORE,
                    f"{where} carries the key {node!r} at {path} (token {token!r}). A release "
                    "that names a selection holds ONE question's answer, and is no longer the "
                    "reusable, selection-independent store every other question needs.")
        token = next((t for t in ROLE_TOKENS if t in low), None)
        if token:
            _refuse(GATE_ROLE_IN_THE_STORE,
                    f"{where} carries the key {node!r} at {path} (token {token!r}). A role is a "
                    "property of a QUESTION, assigned when a selection joins two arms. Written "
                    "into the store, the arm stops being reusable and every other question that "
                    "would have used it is silently wrong.")
        return

    if not isinstance(node, str):
        return
    low = node.lower()
    token = next((t for t in IDENTITY_TOKENS if t in low), None)
    if token:
        _refuse(GATE_SELECTION_IN_THE_STORE,
                f"{where} carries the value {node[:60]!r} at {path} (token {token!r}). The "
                "store may not name the question it is being asked; it answers all of them.")
    token = next((t for t in ROLE_VALUE_TOKENS if t in low), None)
    if token:
        _refuse(GATE_ROLE_IN_THE_STORE,
                f"{where} carries the value {node[:60]!r} at {path} (token {token!r}). A role "
                "names a pole of ONE question. A row that carries one is a row that has already "
                "been answered, and it can never be reused by another question.")


def check_store_is_selection_independent(
        document: Mapping[str, Any],
        tables: Mapping[str, Iterable[Mapping[str, Any]]]) -> None:
    """THE ARCHITECTURAL INVARIANT: no question's identity may exist in the GLOBAL store.

    Scanned RECURSIVELY, over KEYS AND VALUES, at every depth, across the document AND every
    table row — because a leak does not announce itself in the column list somebody is watching.
    It arrives one nested block at a time, and everything downstream keeps verifying.
    """
    for where, node in _subjects(document, tables):
        for kind, item, path in _walk(node):
            _leak(where, kind, item, path)
        for key, value, path in _declared(node):
            _refuse(GATE_ROLE_IN_THE_STORE,
                    f"{where} declares {key}={value!r} at {path}; the store's only permitted "
                    f"mention of a role is the DECLARATION that it holds none "
                    f"({key}={NEGATIVE_DECLARATIONS[key]!r}). A promise that flipped is not a "
                    "promise — it is the leak, announcing itself.")


def _subjects(document: Mapping[str, Any],
              tables: Mapping[str, Iterable[Mapping[str, Any]]]) -> list[tuple[str, Any]]:
    return [("the GLOBAL bundle document", document),
            *((f"the GLOBAL table {n!r}", list(rows)) for n, rows in sorted(tables.items()))]


def _declared(node: Any, path: str = "$") -> Iterator[tuple[str, Any, str]]:
    """Every negative declaration that has STOPPED declaring absence."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if str(key) in NEGATIVE_DECLARATIONS \
                    and value != NEGATIVE_DECLARATIONS[str(key)]:
                yield str(key), value, f"{path}.{key}"
            yield from _declared(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _declared(value, f"{path}[{i}]")


# --------------------------------------------------------------------------- #
# 2. THE STORE'S IDENTITY. Re-derived from the bytes, then compared.
# --------------------------------------------------------------------------- #
def _check_document_identity(document: Mapping[str, Any]) -> None:
    """The document must hash to the identity it publishes. It vouches for the tables; something
    has to vouch for IT, and its own claim about itself is not evidence."""
    content = content_hash(without(dict(document), bv2.DOC_IDENTITY_EXCLUDED))
    if content != document.get("canonical_content_sha256"):
        _refuse(GATE_DOCUMENT_IDENTITY,
                f"the document publishes canonical_content_sha256="
                f"{str(document.get('canonical_content_sha256'))[:16]}… but its own content "
                f"hashes to {content[:16]}…. A document edited after it was addressed carries an "
                "id about bytes that no longer exist.")
    doc_sha = content_hash(without(dict(document), ("document_sha256",)))
    if doc_sha != document.get("document_sha256"):
        _refuse(GATE_DOCUMENT_IDENTITY,
                f"the document publishes document_sha256="
                f"{str(document.get('document_sha256'))[:16]}… but hashes to {doc_sha[:16]}….")


def _declared_hashes(document: Mapping[str, Any],
                     tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, str]:
    declared = dict(document.get("table_hashes") or {})
    expected = set(av2.SCIENTIFIC_TABLES)
    missing_doc = sorted(expected - set(declared))
    missing_hand = sorted(expected - set(tables))
    if missing_doc or missing_hand or sorted(declared) != sorted(expected):
        _refuse(GATE_TABLE_HASHES_INCOMPLETE,
                f"the store has {len(expected)} tables ({sorted(expected)}); the document names "
                f"hashes for {sorted(declared)} and the projection was handed {sorted(tables)}. "
                "A table nobody hashed is a table anybody can edit, and the view would be a "
                "projection of it.")
    return declared


def _compare(gate: str, declared: Mapping[str, str], got: Mapping[str, str],
             what: str, why: str) -> None:
    bad = sorted(n for n in declared if declared[n] != got.get(n))
    if bad:
        detail = ", ".join(f"{n}: document says {declared[n][:16]}…, {what} hashes to "
                           f"{str(got.get(n))[:16]}…" for n in bad)
        _refuse(gate, f"{detail}. {why} The mismatch is NOT reconciled and the recomputed hash "
                      "is NOT adopted: which of the two is the science is exactly the question "
                      "nobody can answer after the fact.")


def _read_from_disk(bundle_dir: str) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for name in av2.SCIENTIFIC_TABLES:
        path = os.path.join(bundle_dir, f"{name}.parquet")
        if not os.path.isfile(path):
            _refuse(GATE_STORE_ON_DISK_DIFFERS,
                    f"the document names a hash for {name!r}, but the store at "
                    f"{os.path.basename(bundle_dir)!r} has no {name}.parquet. A hash of bytes "
                    "that are not there names nothing.")
        rows[name] = av2.read_table(path, name)
    return rows


def _check_cells(tables: Mapping[str, Sequence[Mapping[str, Any]]],
                 on_disk: Mapping[str, list[dict[str, Any]]]) -> None:
    """The rows in hand are the rows on disk — CELL FOR CELL, display columns included.

    The content hash deliberately excludes the display-only columns (a symbol is a label; the
    typed identity is the identity), so hash equality alone would let a mislabelled row reach a
    rendered page under a name nobody wrote.
    """
    for name in av2.SCIENTIFIC_TABLES:
        hand = av2.encode(name, tables.get(name, []))
        disk = av2.encode(name, on_disk.get(name, []))
        if hand != disk:
            n = next((i for i, (a, b) in enumerate(zip(hand, disk)) if a != b), min(len(hand),
                                                                                    len(disk)))
            _refuse(GATE_STORE_ON_DISK_DIFFERS,
                    f"table {name!r} differs from the store on disk: {len(hand)} rows in hand vs "
                    f"{len(disk)} on disk, first difference at row {n}. Every column is checked, "
                    "including the display-only ones the content hash excludes — a mislabelled "
                    "row would otherwise reach a rendered page under a name nobody wrote.")


def _check_manifest(bundle_dir: str, document: Mapping[str, Any],
                    declared: Mapping[str, str]) -> dict[str, Any]:
    path = os.path.join(bundle_dir, "manifest.json")
    if not os.path.isfile(path):
        _refuse(GATE_NO_STORE_ON_DISK,
                f"no store manifest at {path!r}. The view is a projection OF something: with no "
                "store on disk there are no bytes to re-derive, and the document's hashes would "
                "be checked only against themselves — which is not a check.")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _refuse(GATE_NO_STORE_ON_DISK, f"the store manifest at {path!r} is not readable: {exc}")

    own = content_hash(without(manifest, ("manifest_sha256", "created_at")))
    if own != manifest.get("manifest_sha256"):
        _refuse(GATE_MANIFEST_BINDS_OTHER_BYTES,
                f"the store manifest publishes manifest_sha256="
                f"{str(manifest.get('manifest_sha256'))[:16]}… but its own content hashes to "
                f"{own[:16]}…. A manifest that never recomputes its own identity can be handed a "
                "forged one (audit finding B6), and it would then vouch for anything.")

    for field in ("bundle_id", "document_sha256", "canonical_content_sha256"):
        if manifest.get(field) != document.get(field):
            _refuse(GATE_MANIFEST_BINDS_OTHER_BYTES,
                    f"the store manifest binds {field}={str(manifest.get(field))[:16]}…, but the "
                    f"document presented carries {str(document.get(field))[:16]}…. The manifest "
                    "is the store's own account of what it holds; a view projected against a "
                    "manifest about OTHER bytes is a view of a bundle nobody wrote.")
    if dict(manifest.get("table_hashes") or {}) != dict(declared):
        _refuse(GATE_MANIFEST_BINDS_OTHER_BYTES,
                "the store manifest's table_hashes are not the document's table_hashes.")
    return manifest


def bind(*, document: Mapping[str, Any], tables: Mapping[str, Sequence[Mapping[str, Any]]],
         aggregate: sa.AdmittedAggregate, bundle_dir: str) -> dict[str, Any]:
    """FAIL CLOSED, then NAME THE BYTES. Called BEFORE a single row is projected.

    Returns the ``store`` block the view publishes: the identity of exactly the bytes this
    projection is over, with every hash RE-DERIVED here — never copied out of the document.
    """
    if not bundle_dir or not os.path.isdir(bundle_dir):
        _refuse(GATE_NO_STORE_ON_DISK,
                f"there is no v2 store at {bundle_dir!r}. A view is a projection OF bytes: "
                "without them the document's table_hashes could only be compared with "
                "themselves, and a hash you copy is not a hash you checked.")

    check_store_is_selection_independent(document, tables)
    _check_document_identity(document)
    declared = _declared_hashes(document, tables)

    in_hand = av2.table_content_hashes(tables)
    _compare(GATE_TABLES_ARE_NOT_THE_HASHED_BYTES, declared, in_hand, "the rows in hand",
             "The view would be built over these rows while publishing the digest of rows it is "
             "NOT over.")

    on_disk_rows = _read_from_disk(bundle_dir)
    on_disk = av2.table_content_hashes(on_disk_rows)
    _compare(GATE_STORE_ON_DISK_DIFFERS, declared, on_disk, "the store on disk",
             "The document names bytes the store does not hold.")
    _check_cells(tables, on_disk_rows)
    manifest = _check_manifest(bundle_dir, document, declared)

    method = document.get("method") or {}
    return {
        "bundle_id": document.get("bundle_id"),
        "bundle_schema": document.get("schema_version"),
        "canonical_content_sha256": document.get("canonical_content_sha256"),
        "document_sha256": document.get("document_sha256"),
        "store_manifest_sha256": manifest["manifest_sha256"],
        # RE-DERIVED, from the rows this view is actually a projection of — and proven equal to
        # the store on disk and to what the document declares. Not a copy of a claim.
        "table_hashes": dict(sorted(in_hand.items())),
        "table_hashes_are_re_derived_not_copied": True,
        "n_tables_verified": len(av2.SCIENTIFIC_TABLES),
        "store_identity_verifier_id": STORE_IDENTITY_VERIFIER_ID,
        "store_identity_checks": checks(),
        "stage2_manifest_self_hash": aggregate.manifest_self_hash,
        "stage2_manifest_raw_sha256": aggregate.manifest_raw_sha256,
        "stage2_manifest_canonical_sha256": aggregate.manifest_canonical_sha256,
        "stage1_release_sha256": aggregate.stage1_release_sha256,
        "universe_store_id": (document.get("universe_store") or {}).get("store_id"),
        "method_sha256": content_hash(method),
        "code_tree_sha256": method.get("code_tree_sha256"),
        "schemas_sha256": method.get("schemas_sha256"),
        "direction_vocabulary_digest": method.get("direction_vocabulary_digest"),
    }


def checks() -> list[str]:
    """The gates that RAN, named in the view. A gate nobody can enumerate is a gate nobody can
    notice the absence of."""
    return sorted((GATE_DOCUMENT_IDENTITY, GATE_MANIFEST_BINDS_OTHER_BYTES,
                   GATE_NO_STORE_ON_DISK, GATE_ROLE_IN_THE_STORE,
                   GATE_SELECTION_IN_THE_STORE, GATE_STORE_ON_DISK_DIFFERS,
                   GATE_TABLES_ARE_NOT_THE_HASHED_BYTES, GATE_TABLE_HASHES_INCOMPLETE))
