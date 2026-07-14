"""Independent reconstruction of the criterion-level NEBPI table.

`nebpi_criteria.parquet` is the table that keeps NEBPI a criterion-level evidence model rather
than a decorative score. So it needs the same treatment as everything else in the release:
rebuilt from the bound inputs + the method, never read back from the generator.

Rebuilt here from `nebpi_observations` + `contexts` + `method/nebpi_grossman2026_v1.json`.
Imports nothing from `analysis/`.

The two properties this exists to hold:

  * **a criterion nobody evaluated reads `not_evaluated`, and that is never favourable.** It
    can never carry a class, and it can never quietly vanish from the table.
  * **a criterion the SOURCE gives no Part-II branch can never carry a class** — however
    strongly it was observed. `physical_characteristics` (the CNS-MPO descriptors) is graded A
    in Table 1 and appears in no Table-2 definition: it may be `observed_present` and it still
    carries nothing.
"""

from __future__ import annotations

from .reconstruct import rebuild_nebpi


def _branch_criterion(method: dict) -> dict[str, str]:
    return {k: v for k, v in method["nebpi"]["part_ii_branch_criterion"].items()
            if not k.startswith("_")}


def rebuild_criteria(tables: dict[str, list[dict]], method: dict) -> dict[tuple, dict]:
    """-> {(candidate, context, criterion): the row the release should carry}."""
    spec = {c["criterion_id"]: c for c in method["nebpi"]["part_i_criteria"]}
    nebpi = rebuild_nebpi(tables, method)

    obs_by: dict[tuple[str, str], list[dict]] = {}
    for o in tables.get("nebpi_observations", []):
        obs_by.setdefault((o["candidate_id"], o["context_id"]), []).append(o)

    out: dict[tuple, dict] = {}
    for key, decision in nebpi.items():
        obs = obs_by.get(key, [])
        carried = _carried(decision, method)
        for cid, state in decision["criterion_states"].items():
            sp = spec.get(cid, {})
            consumes = sp.get("consumes") or {}
            ids = sorted(o["observation_id"] for o in obs if o["criterion_id"] == cid)
            out[(key[0], key[1], cid)] = {
                "status": state,
                "importance": sp.get("importance"),
                "in_part_i_table": bool(sp.get("in_part_i_table")),
                "can_satisfy_part_ii_branch": bool(sp.get("can_satisfy_part_ii_branch")),
                "carried_the_assigned_class": cid in carried,
                "evidence_lane_consumed": consumes.get("stage4_lane"),
                "requires_potency_context": bool(consumes.get("requires_potency_context")),
                "n_observations": len(ids),
                "observation_ids": ids,
                "source_verbatim": sp.get("source_verbatim"),
            }
    return out


def _carried(decision: dict, method: dict) -> set[str]:
    """Which criteria carried the class that was ASSIGNED — restated from the method's own map.

    A branch of some OTHER class may be satisfied at the same time (the `impermeable`
    no-relevant-PD conjunct is satisfied whenever the `insufficiently_permeable` one is). That
    is not this candidate's class, and reporting it as if it were would overstate the evidence.
    """
    cls = decision.get("nebpi_class")
    if not cls:
        return set()

    bc = _branch_criterion(method)
    pk = decision.get("derived_pk_level")
    pd_state = decision.get("pd_state")
    rad = decision.get("radiographic_state")

    carried: set[str] = set()
    if cls == "sufficiently_permeable":
        if pk == "pk_therapeutic_in_neb":
            carried.add(bc["pk_therapeutic_in_neb"])
        if pd_state == "observed_present":
            carried.add(bc["pd_in_neb"])
        if rad == "observed_present":
            carried.add(bc["radiographic_response_in_neb"])
    elif cls == "insufficiently_permeable":
        carried.update({bc["pk_low_in_neb"], bc["no_relevant_pd_in_neb"],
                        bc["no_radiographic_response_in_neb"]})
    elif cls == "impermeable":
        carried.update({bc["pk_little_to_none_in_neb"], bc["no_relevant_pd_in_neb"],
                        bc["no_radiographic_response_in_neb"]})
    return carried


def check_criteria(tables: dict[str, list[dict]], method: dict) -> list[str]:
    """-> [] when the emitted criterion table is the one the evidence implies."""
    want = rebuild_criteria(tables, method)
    rows = tables.get("nebpi_criteria", [])
    bad: list[str] = []

    got_keys = {(r["candidate_id"], r["context_id"], r["criterion_id"]) for r in rows}
    for k in sorted(set(want) - got_keys):
        bad.append(f"{k}: the release omits this criterion. A criterion nobody evaluated must "
                   "still appear, as not_evaluated — silence is not a status.")
    for k in sorted(got_keys - set(want)):
        bad.append(f"{k}: the release carries a criterion the evidence does not imply")

    for r in rows:
        k = (r["candidate_id"], r["context_id"], r["criterion_id"])
        w = want.get(k)
        if w is None:
            continue
        for field, wv in w.items():
            gv = r.get(field)
            if isinstance(wv, list):
                gv = list(gv or [])
            if gv != wv:
                bad.append(f"{k}.{field}: release={gv!r}, rebuilt={wv!r}")

        # the two invariants, checked directly rather than inferred from the diff above
        if not r["can_satisfy_part_ii_branch"] and r["carried_the_assigned_class"]:
            bad.append(
                f"{k}: this criterion carries no Part-II branch in the source, yet the release "
                "says it carried the assigned class.")
        if r["status"] == "not_evaluated" and r["carried_the_assigned_class"]:
            bad.append(
                f"{k}: a criterion that was never evaluated cannot have carried a class. "
                "Absent evidence is not favourable evidence.")

    return sorted(bad)
