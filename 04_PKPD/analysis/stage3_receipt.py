"""W16's Stage-3 membership receipt, READ FROM DISK and re-hashed. Stage 4 consumes; it does not coin.

I INVENTED A SCHEMA AND CALLED IT A CONTRACT. This module previously declared
`spot.stage03_independent_receipt.v2` — a receipt W16 does not emit and never has. Stage 4 then
"verified" a receipt Stage 4 had made up, from a dict Stage 4 handed itself, and the honest-admission
test passed. Two producers, two schemas, one of them fictional: the cross-stage check was a mirror.

The real artifact is **`spot.stage03_membership_receipt.v1`**. Its rules, verified byte-for-byte
against W16's emitted fixture rather than assumed:

    receipt_sha256   sha256(canonical_json(receipt minus receipt_sha256))
    view.raw_sha256  sha256 of the view file's BYTES, at the bundle-relative `view.path`
    view.canonical_sha256    sha256(canonical_json(the whole view document))
    view.view_content_sha256 sha256(canonical_json(view minus view_id and view_content_sha256))
    view.view_id             view_content_sha256[:16]

    canonical_json = json.dumps(sort_keys=True, separators=(",", ":"),
                                ensure_ascii=True, allow_nan=False)   -- floats rejected

WHAT STAGE 4 DOES NOT DO. It does not re-verify Stage 3; `verifier_id` names the out-of-process
verifier that did. It does not admit on this receipt alone — W16 says so in the receipt itself
(`this_receipt_is_not_admission_on_its_own`), and Stage 4 repeats it here rather than quietly
treating a receipt as an admission.

WHAT IT DOES. It reads the BYTES, recomputes every hash the receipt states, re-hashes the artifacts
the receipt NAMES from disk, and refuses a self-signed or dirty-tree receipt. A receipt the caller
passes in as a dict is refused outright: the caller is Stage 4, and a proof you write for yourself
about bytes you never read is not a proof.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping, Optional

from .arm_key_codec import MembershipError

# W16's exact schema. Not Stage-4's to version.
RECEIPT_SCHEMA = "spot.stage03_membership_receipt.v1"
SELF_HASH_FIELD = "receipt_sha256"

# The membership contract the receipt must have been sealed under. These are W16's published ids; a
# view sealed under a retired rule is a view whose membership means something else.
MEMBERSHIP_SCHEMA = "spot.stage03_candidate_membership.v2"
MEMBERSHIP_RULE_ID = "spot.stage03.candidate_membership.evidence_rederived.v2"
MEMBERSHIP_VERIFIER_ID = "spot.stage03.candidate_membership.verifier.v2"

# The tables Stage-4's typed evidence-class check READS. W16 names the same two.
CORROBORATING_TABLES: tuple[str, ...] = ("candidates", "arm_summaries")

REQUIRED_TOP_FIELDS: tuple[str, ...] = (
    "schema_version", SELF_HASH_FIELD, "verdict", "verifier_id", "generator_id",
    "producer_tree_is_clean", "code_commit", "artifact_class", "membership", "store", "view",
)
REQUIRED_VIEW_FIELDS: tuple[str, ...] = (
    "path", "raw_sha256", "canonical_sha256", "view_content_sha256", "view_id",
)
REQUIRED_MEMBERSHIP_FIELDS: tuple[str, ...] = (
    "schema", "rule_id", "verifier_id", "vocabulary_digest_in_force",
)


# The ONLY receipt fields Stage 4 emits into its own artifact. The view document, the full table
# rows, and any internal handle stay OUT: a Stage-4 artifact that carries a copy of Stage 3's whole
# view is a second, unverified copy of it, wearing Stage 3's identity.
EMITTED_RECEIPT_FIELDS: tuple[str, ...] = (
    "schema_version", "receipt_sha256", "receipt_raw_sha256", "verdict", "artifact_class",
    "generator_id", "verifier_id", "code_commit", "producer_tree_is_clean",
)


def emitted_receipt(receipt: Mapping[str, Any], view: Mapping[str, Any]) -> dict[str, Any]:
    """The receipt as it appears in a Stage-4 artifact: authoritative fields + the bound identities.

    No underscore keys, no view document, no table rows — a reader gets the ids and the hashes it
    needs to re-verify, and nothing it would have to trust us not to have altered.
    """
    out = {f: receipt.get(f) for f in EMITTED_RECEIPT_FIELDS if receipt.get(f) is not None}
    out["membership"] = {k: (receipt.get("membership") or {}).get(k)
                         for k in ("schema", "rule_id", "verifier_id",
                                   "vocabulary_digest_in_force")}
    out["view"] = {k: (receipt.get("view") or {}).get(k) for k in REQUIRED_VIEW_FIELDS}
    out["store"] = {"table_hashes": (receipt.get("store") or {}).get("table_hashes") or {},
                    "store_manifest_sha256": (receipt.get("store") or {}).get(
                        "store_manifest_sha256")}
    out["this_receipt_is_not_admission_on_its_own"] = receipt.get(
        "this_receipt_is_not_admission_on_its_own")
    out["bound_view_id"] = view.get("view_id")
    return out


def canonical_json(obj: Any) -> str:
    """W16's rule, reproduced exactly. A different rule is a different hash of the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_receipt(receipt_path: str, bundle_dir: Optional[str] = None,
                 store_dir: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read W16's receipt bytes, recompute its identity, re-hash everything it names.

    -> (receipt, view_document). SEPARATE, deliberately: the view is not a field of the receipt.

    `bundle_dir` is REQUIRED. It was optional, and the re-hash ran only `if bundle_dir:` — so a
    caller that omitted it got every artifact check skipped, and a receipt with sealed FAKE hashes
    pointing at an EMPTY bundle was admitted. An optional verification is not a verification; it is
    a verification the attacker chooses.
    """
    if not bundle_dir:
        raise MembershipError(
            "stage4_stage3_bundle_dir_is_required",
            "no bundle directory was supplied, so nothing the receipt names could be re-hashed. "
            "A receipt is a claim ABOUT bytes; without the bytes it is only a well-formed claim.",
        )
    if not os.path.isdir(bundle_dir):
        raise MembershipError(
            "stage4_stage3_bundle_dir_is_not_a_directory",
            f"the bundle directory {bundle_dir!r} does not exist.",
        )
    if not receipt_path or not os.path.isfile(receipt_path):
        raise MembershipError(
            "stage4_stage3_receipt_not_on_disk",
            f"no Stage-3 receipt at {receipt_path!r}. Stage 4 will not accept one handed to it in "
            "memory: the caller IS Stage 4, so a dict it builds is a proof it wrote for itself "
            "about bytes it never read.",
        )

    with open(receipt_path, encoding="utf-8") as fh:
        try:
            receipt = json.load(fh)
        except json.JSONDecodeError as exc:
            raise MembershipError(
                "stage4_stage3_receipt_is_not_readable",
                f"the receipt at {receipt_path!r} is not valid JSON.") from exc

    missing = [f for f in REQUIRED_TOP_FIELDS if receipt.get(f) in (None, "", {})]
    if missing:
        raise MembershipError(
            "stage4_stage3_receipt_is_incomplete",
            f"the Stage-3 receipt is missing {missing}.", {"missing": missing})

    if str(receipt["schema_version"]) != RECEIPT_SCHEMA:
        raise MembershipError(
            "stage4_stage3_receipt_schema_unknown",
            f"schema_version is {receipt['schema_version']!r}; Stage 4 consumes {RECEIPT_SCHEMA!r} "
            "— W16's actual receipt. Stage 4 does not coin a schema of its own: a receipt only one "
            "side emits is a receipt only one side checks.",
        )

    _assert_self_hash(receipt, receipt_path)
    _assert_independent(receipt)
    _assert_admits(receipt)
    _assert_membership_contract(receipt)
    _assert_store_covers_corroborating_tables(receipt)

    view_doc = _rehash_view(receipt, bundle_dir)
    _rehash_store_tables(receipt, store_dir)      # only when the STORE's parquet is on hand

    # The receipt and the view are returned SEPARATELY. Stuffing the view into the receipt dict under
    # a private key meant the whole Stage-3 view — every table, every row — was serialized into the
    # emitted Stage-4 artifact under `stage3_receipt`. An internal handle is not an output field.
    receipt["receipt_raw_sha256"] = _sha256_file(receipt_path)
    return dict(receipt), view_doc


def _assert_self_hash(receipt: Mapping[str, Any], path: str) -> None:
    """`receipt_sha256` over the canonical receipt MINUS that field. A hash cannot cover itself."""
    declared = str(receipt.get(SELF_HASH_FIELD) or "")
    body = {k: v for k, v in receipt.items() if k != SELF_HASH_FIELD}
    actual = canonical_sha256(body)
    if declared != actual:
        raise MembershipError(
            "stage4_stage3_receipt_self_hash_does_not_recompute",
            f"the receipt at {path!r} declares {SELF_HASH_FIELD}={declared[:16]}… and its own bytes "
            f"canonicalize to {actual[:16]}…. It has been edited since it was sealed — and the "
            "caller's clean dict says nothing about the bytes on disk.",
        )


def _assert_independent(receipt: Mapping[str, Any]) -> None:
    """A bundle verified by the thing that produced it has not been verified."""
    generator, verifier = str(receipt.get("generator_id")), str(receipt.get("verifier_id"))
    if generator == verifier:
        raise MembershipError(
            "stage4_stage3_receipt_is_self_signed",
            f"the receipt names {generator!r} as BOTH generator and verifier. A producer that "
            "verifies its own output has not been verified.",
        )
    if receipt.get("generator_is_not_verifier") is False:
        raise MembershipError(
            "stage4_stage3_receipt_is_self_signed",
            "the receipt itself reports generator_is_not_verifier=false.",
        )
    if receipt.get("producer_tree_is_clean") is not True:
        raise MembershipError(
            "stage4_stage3_receipt_producer_tree_is_dirty",
            f"the receipt reports a DIRTY producer tree at commit "
            f"{str(receipt.get('code_commit'))[:12]}. A receipt bound to a commit that does not "
            "describe the tree that produced the bytes is bound to nothing reproducible.",
        )


def _assert_admits(receipt: Mapping[str, Any]) -> None:
    verdict = receipt.get("verdict")
    if str(verdict) != "admit":
        raise MembershipError(
            "stage4_stage3_receipt_did_not_admit",
            f"the receipt records verdict {verdict!r} (failure: {receipt.get('failure')!r}). "
            "Emitted is not admitted, and a projection of a bundle its own verifier refused is a "
            "projection of a refusal.",
        )


def _assert_membership_contract(receipt: Mapping[str, Any]) -> None:
    """The view must have been sealed under the membership rule NOW IN FORCE.

    W16 lists the retired ids in the receipt itself. A view sealed under a retired rule computed
    membership by a rule that no longer holds — the rows would look identical and mean something
    else, which is exactly what a version is for.
    """
    membership = receipt.get("membership") or {}
    missing = [f for f in REQUIRED_MEMBERSHIP_FIELDS if not membership.get(f)]
    if missing:
        raise MembershipError(
            "stage4_stage3_receipt_membership_block_is_incomplete",
            f"the receipt's `membership` block is missing {missing}.", {"missing": missing})

    for field, expected in (("schema", MEMBERSHIP_SCHEMA),
                            ("rule_id", MEMBERSHIP_RULE_ID),
                            ("verifier_id", MEMBERSHIP_VERIFIER_ID)):
        actual = str(membership.get(field))
        if actual != expected:
            retired = list(membership.get("retired_ids") or ())
            raise MembershipError(
                "stage4_stage3_membership_rule_is_not_the_one_in_force",
                f"the view was sealed under membership.{field}={actual!r}; the rule in force is "
                f"{expected!r}"
                + (f" and {actual!r} is RETIRED" if actual in retired else "")
                + ". Rows computed under a retired membership rule look identical and mean "
                  "something else.",
                {"field": field, "declared": actual, "in_force": expected},
            )

    # The vocabulary the view was sealed under must be the vocabulary the store carries.
    store_digest = str((receipt.get("store") or {}).get("selection_view_vocabulary_digest") or "")
    in_force = str(membership.get("vocabulary_digest_in_force") or "")
    if store_digest and in_force != store_digest:
        raise MembershipError(
            "stage4_stage3_vocabulary_digest_disagrees_with_the_store",
            f"the membership rule was sealed under vocabulary {in_force[:16]}… and the store "
            f"carries {store_digest[:16]}…. The receipt contradicts itself about which vocabulary "
            "the view's terms were drawn from.",
        )


def _assert_store_covers_corroborating_tables(receipt: Mapping[str, Any]) -> None:
    store = receipt.get("store") or {}
    table_hashes = store.get("table_hashes") or {}
    uncovered = [t for t in CORROBORATING_TABLES if not table_hashes.get(t)]
    if uncovered:
        raise MembershipError(
            "stage4_stage3_receipt_does_not_cover_the_corroborating_tables",
            f"the receipt carries no hash for {uncovered}. Stage 4's typed evidence-class check "
            f"reads {list(CORROBORATING_TABLES)}; a corroboration from a table the receipt never "
            "covered comes from unverified bytes, and the check would LOOK independent while being "
            "independent of nothing.",
            {"uncovered_tables": uncovered},
        )
    declared = list(store.get("corroborating_tables_uncovered") or ())
    if declared:
        raise MembershipError(
            "stage4_stage3_receipt_does_not_cover_the_corroborating_tables",
            f"the receipt itself reports uncovered corroborating tables {declared}.",
            {"uncovered_tables": declared},
        )


def _require_bundle_file(bundle_dir: str, rel: str, code: str, what: str) -> str:
    """A referenced artifact must EXIST, as a REGULAR FILE, resolved bundle-relative.

    The re-hash used to skip a file that was not there (`if os.path.exists(path)`), so a receipt with
    sealed FAKE hashes over an EMPTY bundle directory was admitted: nothing to compare against meant
    nothing to disagree. A missing artifact is now a refusal, not a skipped step.
    """
    if os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        raise MembershipError(
            "stage4_stage3_receipt_path_is_not_bundle_relative",
            f"the receipt names {rel!r}. Only bundle-relative references are resolved: an absolute "
            "or traversing path names a document outside the bundle the receipt was sealed against.",
        )

    path = os.path.join(bundle_dir, rel)
    if not os.path.isfile(path):
        raise MembershipError(
            code,
            f"{what} {rel!r} and the bundle does not carry it as a regular file. A receipt whose "
            "artifacts are absent cannot be checked against anything — and 'nothing to compare' is "
            "not 'nothing wrong'.",
            {"path": rel},
        )
    return path


def _rehash_view(receipt: Mapping[str, Any], bundle_dir: str) -> dict[str, Any]:
    """Re-hash the view FROM DISK and RETURN it: raw bytes, canonical doc, content id, view_id.

    This is the link a forged `receipt_sha256` cannot survive. The receipt can be made
    self-consistent; it cannot make the bytes on disk hash to what it claims.

    The view is RETURNED because the corroborating tables live INSIDE it — W16 ships no parquet in
    the bundle. Those rows are therefore hash-bound by the view's own raw/canonical hashes, and
    Stage 4 reads them from here rather than from a list the caller passes in. Evidence supplied by
    the caller is evidence the caller can choose.
    """
    view = receipt.get("view") or {}
    missing = [f for f in REQUIRED_VIEW_FIELDS if not view.get(f)]
    if missing:
        raise MembershipError(
            "stage4_stage3_receipt_view_block_is_incomplete",
            f"the receipt's `view` block is missing {missing}.", {"missing": missing})

    rel = str(view["path"])
    path = _require_bundle_file(bundle_dir, rel, "stage4_stage3_view_is_not_in_the_bundle",
                                "the receipt names view")
    raw = _sha256_file(path)
    if raw != str(view["raw_sha256"]):
        raise MembershipError(
            "stage4_stage3_view_does_not_rehash_to_its_receipt",
            f"the receipt declares view raw_sha256={str(view['raw_sha256'])[:16]}… and the bytes on "
            f"disk hash to {raw[:16]}…. The rows Stage 4 would display are not the rows the verifier "
            "admitted.",
        )

    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    checks = {
        "canonical_sha256": canonical_sha256(doc),
        "view_content_sha256": canonical_sha256(
            {k: v for k, v in doc.items() if k not in ("view_id", "view_content_sha256")}),
    }
    for field, actual in checks.items():
        if actual != str(view[field]):
            raise MembershipError(
                "stage4_stage3_view_does_not_rehash_to_its_receipt",
                f"the receipt declares view {field}={str(view[field])[:16]}… and Stage 4 recomputes "
                f"{actual[:16]}… from the document on disk.",
                {"field": field},
            )

    if str(view["view_id"]) != checks["view_content_sha256"][:16]:
        raise MembershipError(
            "stage4_stage3_view_id_does_not_follow_from_its_content",
            f"view_id {view['view_id']!r} is not the first 16 hex of the recomputed content hash "
            f"{checks['view_content_sha256'][:16]!r}.",
        )

    # The corroborating tables must be IN the view Stage 4 just re-hashed.
    tables = doc.get("tables") or {}
    absent = [t for t in CORROBORATING_TABLES if not isinstance(tables.get(t), list)]
    if absent:
        raise MembershipError(
            "stage4_stage3_view_does_not_carry_the_corroborating_tables",
            f"the view carries no {absent} rows. Stage 4's typed evidence-class check reads "
            f"{list(CORROBORATING_TABLES)}; without them in the HASH-BOUND view the only rows "
            "available would be rows the caller supplied, and evidence the caller supplies is "
            "evidence the caller can choose.",
            {"absent_tables": absent},
        )
    return doc


def _rehash_store_tables(receipt: Mapping[str, Any], store_dir: Optional[str]) -> None:
    """Re-hash the STORE's parquet against `store.table_hashes` — when the store is on hand.

    W16's exported bundle ships the view and the receipt, NOT the store's parquet: the corroborating
    rows travel inside the view, hash-bound by it. `store.table_hashes` is the store's own statement
    about tables that live elsewhere. When the store IS supplied, Stage 4 re-hashes it and refuses a
    disagreement; when it is not, the rows Stage 4 reads are still hash-bound — by the view.
    """
    if not store_dir:
        return
    table_hashes = (receipt.get("store") or {}).get("table_hashes") or {}
    for table in CORROBORATING_TABLES:
        path = _require_bundle_file(
            store_dir, f"{table}.parquet",
            "stage4_stage3_corroborating_table_is_not_in_the_store",
            f"the receipt covers {table!r} and the typed evidence-class check reads")
        actual = _sha256_file(path)
        if actual != str(table_hashes[table]):
            raise MembershipError(
                "stage4_stage3_table_does_not_rehash_to_its_receipt",
                f"table {table!r}: the receipt declares {str(table_hashes[table])[:16]}… and the "
                f"bytes on disk hash to {actual[:16]}…. A hash the receipt asserts about a table it "
                "no longer matches proves only that the receipt can hash.",
                {"table": table},
            )
