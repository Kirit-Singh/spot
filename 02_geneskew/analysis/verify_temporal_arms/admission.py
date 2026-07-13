"""ADMISSION: the producer's immutable inventory, and THIS lane's external envelope.

TWO ARTIFACTS, TWO AUTHORS, AND THEY ARE NOT THE SAME CLAIM
-----------------------------------------------------------
``temporal_arm_release.json``   THE PRODUCER'S. Immutable, content-addressed over its own
                                bytes, and MANDATORY: it is the single artifact that says
                                what the release IS. It declares its own status as PENDING
                                and names who will decide. It is never rewritten here — an
                                external verifier that edited the producer's inventory would
                                be editing the evidence it was judging.

``temporal_verification.json``  THIS LANE'S, at the RELEASE ROOT, and there is exactly ONE.
                                Not six copies inside the producer's bundle directories: a
                                verdict sitting in the directory it judges is indistinguish-
                                able, to a reader resolving it by path, from a self-verdict.

The envelope binds WHAT THE ADMISSION IS AN ADMISSION OF — the producer's release id and the
exact inventory bytes, every bundle id and hash, the Stage-1 / method / code identities — and
publishes THIS lane's gate inventory, so a reader can see what "admit" actually covered
rather than only that nothing failed.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import release as release_mod
from . import schema
from .canonical import canonical_json, content_hash, sha256_hex
from .failures import Failures

VERIFIER_ID = "spot.stage02.temporal.arm.independent_verifier.v1"
ID_LEN = 16

def inventory(f: Failures, bound, bundle_root: str, docs: list[dict[str, Any]],
               host_denylist) -> Optional[dict[str, Any]]:
    """THE PRODUCER'S IMMUTABLE ROOT INVENTORY. Mandatory, self-addressed, and re-derived.

    It is the single artifact that says what the release IS. A verifier that shrugged at its
    absence would admit whatever happened to be lying in the directory, and one that took
    its word would be admitting the producer's own account of what it produced.
    """
    path = os.path.join(os.path.abspath(str(bundle_root)), schema.INVENTORY_FILENAME)
    if not f.check("the_producer_release_inventory_is_on_disk", os.path.exists(path),
                   "release",
                   f"{schema.INVENTORY_FILENAME!r} is MANDATORY: it is what says which six "
                   "bundles this release is, and without it there is nothing to verify "
                   "AGAINST — only a directory to look at"):
        return None
    with open(path, "rb") as fh:
        raw = fh.read()
    inv = json.loads(raw)

    problems = schema.exact_keys(inv, schema.INVENTORY_KEYS, "inventory")
    f.check("inventory_keys_are_the_exact_allowlist", not problems, "release",
            "; ".join(problems))
    banned = schema.banned_keys(inv)
    f.check("inventory_carries_no_banned_field", not banned, "release", str(banned))
    machine = schema.machine_path_hits(inv, host_denylist=host_denylist)
    f.check("inventory_carries_no_machine_path_hostname_or_private_address", not machine,
            "release",
            f"{machine}. The inventory is the one artifact everybody reads; it is exactly "
            "where a machine path would travel furthest")
    if problems:
        return None

    # THE SELF-HASH, by the inventory's OWN declared rule: the canonical hash of everything
    # except the id itself. The rule is re-derived from the bytes, not taken on the
    # artifact's word — but the artifact must still say which rule it used, or two readers
    # could compute two different "correct" ids and both be right.
    payload = {k: v for k, v in inv.items() if k != "release_id"}
    derived = content_hash(payload)
    f.check("the_inventory_declares_the_rule_its_id_was_computed_under",
            bool(inv.get("release_id_rule")), "release", "")
    f.check("the_inventory_release_id_covers_its_own_content",
            inv["release_id"] == derived, "release",
            f"shipped {inv['release_id']!r}, its own content hashes to {derived!r}")
    f.check("the_inventory_schema_is_the_contract",
            inv["schema_version"] == schema.SCHEMA_INVENTORY, "release",
            str(inv["schema_version"]))

    # THE PRODUCER SAYS PENDING. It never says admit, and it names who will decide.
    ext = inv.get("external_admission") or {}
    ep = schema.exact_keys(ext, schema.EXTERNAL_ADMISSION_KEYS, "external_admission")
    f.check("external_admission_keys_are_the_exact_allowlist", not ep, "release",
            "; ".join(ep))
    f.check("the_producer_declares_its_release_PENDING_external_verification",
            str(ext.get("status", "")).startswith(schema.EXTERNAL_ADMISSION_PENDING)
            and ext.get("required_verifier_id") == VERIFIER_ID
            and ext.get("required_report_schema_version") == schema.SCHEMA_ENVELOPE,
            "release",
            f"status={ext.get('status')!r}. The producer may say its release AWAITS an "
            "external verdict and name who must issue it; it may not issue one")

    _stage1_binding(f, inv.get("stage1_binding"), bound)

    tp = schema.exact_keys(inv.get("topology") or {}, schema.TOPOLOGY_KEYS, "topology")
    f.check("inventory_topology_keys_are_the_exact_allowlist", not tp, "release",
            "; ".join(tp))

    # THE INVENTORY MUST MATCH THE DISK — every bundle, and every FILE inside it.
    on_disk = {d["doc"].get("bundle_id"): d for d in docs}
    listed = {b.get("bundle_id"): b for b in inv["bundles"]}
    f.check("the_inventory_lists_exactly_the_bundles_that_are_on_disk",
            set(listed) == set(on_disk), "release",
            f"inventory {sorted(k for k in listed if k)}, disk {sorted(on_disk)}")
    f.check("the_inventory_counts_are_the_topology_the_stage1_release_implies",
            inv["n_bundles"] == len(bound.ordered_pairs)
            and inv["n_logical_arms"] == bound.n_logical_arms
            and len(inv["bundles"]) == inv["n_bundles"], "release",
            f"n_bundles={inv['n_bundles']} n_logical_arms={inv['n_logical_arms']}; the "
            f"bound release implies {len(bound.ordered_pairs)} and "
            f"{bound.n_logical_arms}")

    root = os.path.abspath(str(bundle_root))
    n_listed_rankings = 0
    for entry in inv["bundles"]:
        bp = schema.exact_keys(entry, schema.INVENTORY_BUNDLE_KEYS, "inventory_bundle")
        if not f.check("inventory_bundle_entry_keys_are_the_exact_allowlist", not bp,
                       "release", "; ".join(bp)):
            continue
        d = str(entry["relative_dir"])

        # THE RANKING SET IS EXACTLY THE ARMS' — no more, no less.
        #
        # Checking that every file the inventory NAMES exists and hashes is only half the
        # rule. An EXTRA ranking file, fully hashed and resealed into the inventory, passes
        # that half perfectly: every named file is real. But the release then ships 121
        # ranking files while 120 arms were re-ranked, and the 121st is a ranking nobody
        # verified, sitting in the release under the producer's own hash. A consumer joining
        # by path would read it.
        listed = set((entry.get("rankings") or {}))
        n_listed_rankings += len(listed)
        doc = on_disk.get(entry.get("bundle_id"))
        if doc is not None:
            bound_paths = {str((a.get("ranking") or {}).get("path"))
                           for a in doc["doc"].get("arms", [])}
            f.check("the_inventorys_ranking_set_is_exactly_the_arms_that_were_reranked",
                    listed == bound_paths, d,
                    f"inventory lists {len(listed)} ranking files; {len(bound_paths)} arms "
                    f"bind one. extra={sorted(listed - bound_paths)} "
                    f"missing={sorted(bound_paths - listed)}. A ranking file no arm binds "
                    "is a ranking nobody re-derived")

            # ...and the DIRECTORY may not hold one either. A stale file the inventory
            # simply forgot to name is still in the release, and still readable by path.
            rdir = os.path.join(root, d, schema.RANKINGS_DIRNAME)
            if os.path.isdir(rdir):
                on_disk_paths = {f"{schema.RANKINGS_DIRNAME}/{n}"
                                 for n in os.listdir(rdir)}
                f.check("no_stale_ranking_file_sits_in_the_release_unbound_by_any_arm",
                        on_disk_paths == bound_paths, d,
                        f"unbound on disk: {sorted(on_disk_paths - bound_paths)}")
        f.check("every_inventory_dir_is_relative_and_does_not_escape",
                not os.path.isabs(d) and ".." not in d.split("/"), "release", d)
        # EVERY referenced file — bundle, provenance, preflight AND every ranking file —
        # is reopened and rehashed. A hash the inventory declares for a file nobody wrote
        # is not a binding.
        referenced = dict(entry.get("files") or {})
        referenced.update(entry.get("rankings") or {})
        for rel, want in sorted(referenced.items()):
            fp = os.path.normpath(os.path.join(root, d, rel))
            if not f.check("every_file_the_inventory_references_exists_on_disk",
                           os.path.exists(fp), d, rel):
                continue
            with open(fp, "rb") as fh:
                fraw = fh.read()
            f.check("every_file_the_inventory_references_hashes_to_what_it_declares",
                    want.get("raw_sha256") == sha256_hex(fraw)
                    and (want.get("canonical_sha256") is None
                         or want["canonical_sha256"] == content_hash(json.loads(fraw))),
                    d, f"{rel}: the bytes on disk are not the bytes the inventory pinned")

    # ONE ranking file per logical arm, across the whole release. The count is a CONSEQUENCE
    # of the topology, so a 121st file is not a rounding error — it is an extra claim.
    n_reranked = sum(len(x["doc"].get("arms", [])) for x in docs)
    f.check("the_release_lists_exactly_one_ranking_file_per_logical_arm",
            n_listed_rankings == n_reranked == bound.n_logical_arms, "release",
            f"the inventory lists {n_listed_rankings} ranking files; {n_reranked} arms were "
            f"re-ranked; the bound release implies {bound.n_logical_arms} logical arms")
    return inv


def _stage1_binding(f: Failures, sb: Any, bound) -> None:
    """THE STAGE-1 IDENTITY the release stands on. Non-null, exact, and RE-DERIVED.

    A field that is allowlisted but never checked is a field that can say anything — which
    is exactly how a release ships with its Stage-1 identity set to null and is admitted
    anyway. Every binding below is compared against what THIS lane derived from the release
    it loaded; none of them is read out of the artifact and believed.
    """
    problems = schema.exact_keys(sb if isinstance(sb, dict) else {},
                                 schema.STAGE1_BINDING_KEYS, "stage1_binding")
    if not f.check("inventory_stage1_binding_keys_are_the_exact_allowlist",
                   isinstance(sb, dict) and not problems, "release",
                   "; ".join(problems) or "the inventory carries no stage1_binding"):
        return

    nulls = sorted(k for k in schema.STAGE1_BINDING_REQUIRED_NONNULL
                   if sb.get(k) in (None, "", [], {}))
    f.check("no_stage1_binding_is_null", not nulls, "release",
            f"{nulls} are null. A NULL BINDING IS NOT A BINDING: a release whose Stage-1 "
            "identity is absent cannot be shown to stand on the release it claims, and an "
            "admission of it admits nothing in particular")

    f.check("the_stage1_scorer_view_binding_is_the_bound_releases",
            sb.get("registry_scorer_view_sha256") == bound.scorer_view_sha256
            and sb.get("scorer_view_canonical_sha256") == bound.scorer_view_sha256
            and sb.get("scorer_view_raw_sha256") == bound.scorer_view_raw_sha256,
            "release",
            f"binds {sb.get('registry_scorer_view_sha256')}, the bound release's scorer "
            f"view hashes to {bound.scorer_view_sha256}")
    f.check("the_stage1_release_self_identity_rederives",
            sb.get("release_self_sha256") == bound.release_self_sha256, "release",
            f"binds {sb.get('release_self_sha256')}, the Stage-1 release on disk hashes to "
            f"{bound.release_self_sha256}")

    # THE SCALAR: one number for the whole admitted axis. "Is this the same axis?"
    f.check("the_scalar_scorer_projection_identity_rederives",
            sb.get("registry_scorer_projection_sha256")
            == bound.scorer_projection_sha256, "release",
            f"binds {sb.get('registry_scorer_projection_sha256')}, the admitted program "
            f"axis projects to {bound.scorer_projection_sha256}")

    # THE MAP: one hash per admitted program. "...and if not, WHICH program moved?"
    # The scalar alone cannot say which program changed; the map alone lets a producer ship
    # ten self-consistent hashes over an axis Stage-2 never bound. Both, or neither is a
    # binding.
    # The artifact must say WHICH rule its map was computed under. Two readers computing two
    # different "correct" maps would both be right and would still disagree.
    f.check("the_per_program_map_declares_the_canonical_stage1_record_rule",
            sb.get("per_program_projection_rule_id")
            == release_mod.PER_PROGRAM_PROJECTION_RULE_ID, "release",
            f"declares {sb.get('per_program_projection_rule_id')!r}; the canonical rule is "
            f"{release_mod.PER_PROGRAM_PROJECTION_RULE_ID!r}")

    want = dict(bound.program_projection_sha256)
    got = sb.get("per_program_projection_sha256")
    if f.check("the_per_program_projection_map_is_keyed_by_the_admitted_programs",
               isinstance(got, dict) and sorted(got) == sorted(want), "release",
               f"map keys {sorted(got) if isinstance(got, dict) else got}; the admitted "
               f"program axis is {sorted(want)}"):
        drift = sorted(k for k in want if got.get(k) != want[k])
        f.check("every_per_program_projection_hash_rederives", not drift, "release",
                f"{drift} do not re-derive from the bound release's own program projections")

    # THE SELECTOR IDENTITY: the condition SEQUENCE, in the release's own order. A sorted
    # condition list is not a sequence — the order IS the time axis, and a lane that kept
    # only the sorted one has thrown the arrow of time away and cannot get it back.
    f.check("the_selector_condition_SEQUENCE_is_the_releases_own_order",
            list(sb.get("selector_condition_sequence") or []) == list(bound.conditions),
            "release",
            f"binds {sb.get('selector_condition_sequence')}, the release's selector "
            f"declares {list(bound.conditions)} IN THAT ORDER")
    f.check("the_stage1_binding_names_the_admitted_program_axis",
            sorted(sb.get("admitted_programs") or []) == sorted(bound.admitted_programs)
            and sb.get("n_programs") == bound.n_admitted_programs
            and sb.get("n_conditions") == len(bound.conditions), "release", "")


def _sha_of(root: str, dirname: str, filename: str) -> Optional[str]:
    path = os.path.join(root, dirname, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return sha256_hex(fh.read())


def _ranking_bindings(doc: dict[str, Any]) -> dict[str, dict[str, str]]:
    """``arm_key -> {path, raw_sha256, canonical_sha256}`` — the bytes each rank stands on."""
    out: dict[str, dict[str, str]] = {}
    for arm in doc.get("arms", []):
        b = arm.get("ranking") or {}
        out[arm["arm_key"]] = {"path": b.get("path"), "raw_sha256": b.get("raw_sha256"),
                               "canonical_sha256": b.get("canonical_sha256")}
    return out


def _rankings_digest(docs: list[dict[str, Any]]) -> str:
    """One content address over EVERY ranking file in the release. Order-independent."""
    rows = [{"bundle_key": d["doc"].get("bundle_key"), "arm_key": k, **v}
            for d in docs for k, v in _ranking_bindings(d["doc"]).items()]
    rows.sort(key=lambda r: (str(r["bundle_key"]), str(r["arm_key"])))
    return content_hash(rows)


def write_envelope(*, report: dict[str, Any], inventory: Optional[dict[str, Any]],
                   docs: list[dict[str, Any]], bundle_root: str, verifier_id: str,
                   rules_id: str, id_len: int) -> Optional[str]:
    """THE EXTERNAL ADMISSION ENVELOPE — ONE file, at the RELEASE ROOT.

    Written by THIS lane, after reopening the shipped bytes, and never inside a producer
    bundle directory: an external verifier that rewrote the producer's own artifacts would
    be editing the evidence it was judging.

    It binds what the admission is an admission OF — the producer's release id and the exact
    inventory bytes, every bundle id and hash, the Stage-1 / method / code identities — plus
    THIS lane's gate inventory and identity, so a reader can see what "admit" covered.
    """
    root = os.path.abspath(str(bundle_root))
    ipath = os.path.join(root, schema.INVENTORY_FILENAME)
    if not os.path.exists(ipath):
        return None
    with open(ipath, "rb") as fh:
        iraw = fh.read()

    envelope = {
        "schema_version": schema.SCHEMA_ENVELOPE,
        "verifier_id": verifier_id,
        "rules_id": rules_id,
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "verdict": report["verdict"],
        "n_failed": report["n_failed"],
        "failed_gates": sorted({x["gate"] for x in report["failures"]}),
        "gate_inventory": sorted(report["gates_run"]),
        # WHAT THIS ADMISSION IS AN ADMISSION OF
        "binds": {
            # THE RELEASE THIS ADMITS. Its identity AND its exact bytes: a reader holding
            # the release can prove the admission is over the one in its hands, and an
            # envelope that admits a different release admits something else.
            "producer_release_id": (inventory or {}).get("release_id"),
            "producer_release_file": schema.INVENTORY_FILENAME,
            "producer_release_raw_sha256": sha256_hex(iraw),
            "producer_release_canonical_sha256": content_hash(json.loads(iraw)),
            "bundles": [{"bundle_key": d["doc"].get("bundle_key"),
                         "bundle_id": d["doc"].get("bundle_id"),
                         "dir": d["dirname"],
                         "arm_bundle_raw_sha256": d["raw_sha256"],
                         "arm_bundle_canonical_sha256": d["canonical_sha256"],
                         "provenance_raw_sha256": _sha_of(root, d["dirname"],
                                                          schema.PROVENANCE_FILENAME),
                         # EVERY ranking file this lane actually reopened and RE-RANKED,
                         # by arm key. A downstream reader recomputes these from disk and
                         # refuses a mismatch — which is what catches a rank-swap that was
                         # resealed all the way through the producer's own inventory.
                         "rankings": _ranking_bindings(d["doc"])}
                        for d in docs],
            # ONE digest over every ranking file in the release, so a consumer can refuse a
            # tampered ranking with a single comparison rather than 120.
            "rankings_digest": _rankings_digest(docs),
            "stage1_release": report["release_binding"],
            # BOTH projection bindings, so a consumer can ask both questions: "is this the
            # same axis?" and "if not, which program moved?"
            "registry_scorer_projection_sha256":
                ((inventory or {}).get("stage1_binding") or {})
                .get("registry_scorer_projection_sha256"),
            "per_program_projection_sha256":
                ((inventory or {}).get("stage1_binding") or {})
                .get("per_program_projection_sha256"),
            "selector_condition_sequence":
                ((inventory or {}).get("stage1_binding") or {})
                .get("selector_condition_sequence"),
            "method": (docs[0]["doc"].get("method") if docs else None),
            "code_identity": (docs[0]["doc"].get("code_identity") if docs else None),
            "env_lock_sha256": ((docs[0]["doc"].get("code_identity") or {})
                                .get("env_lock_sha256") if docs else None),
        },
        "temporal_arm_run_id": report["temporal_arm_run_id"],
        "counts": report["counts"],
        "n_base_deltas_rederived": report["n_base_deltas_rederived"],
        "n_arm_values_rederived": report["n_arm_values_rederived"],
        "producer_self_report_trusted": False,
    }
    # THE SELF-HASH, by the SAME rule the producer's inventory declares: the full sha256 of
    # the canonical JSON excluding the id itself. One rule, two artifacts, and a reader that
    # already knows how to check one knows how to check the other.
    envelope["report_id_rule"] = "sha256(canonical JSON excluding report_id)"
    envelope["report_id"] = content_hash(envelope)
    path = os.path.join(root, schema.ENVELOPE_FILENAME)
    with open(path, "wb") as fh:
        fh.write(canonical_json(envelope).encode("utf-8"))
    return schema.ENVELOPE_FILENAME


