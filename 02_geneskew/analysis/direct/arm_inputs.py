"""The inputs an ALL-ARM bundle actually consumes — and the pair it does not.

The legacy `run_screen.stage2_input_manifest` hashes `args.selection`. That is correct for a
pair's run, whose identity IS a function of its pair, and wrong for a physical bundle, whose
whole purpose is to be citable by every pair. Reusing it here had two consequences, and they
were the same bug wearing two hats:

  * the CLI CRASHED. The all-arm parser deliberately defines no `--selection`, so the
    manifest read an attribute that a real `argparse.Namespace` does not carry;
  * the bundle's identity MOVED with a pair it never loaded. Rewriting the A/B programs of
    an unused selection file changed the run id while every emitted row stayed identical —
    two ids for one measurement, which is exactly the cache fragmentation the all-arm
    topology exists to remove.

So an all-arm bundle gets its OWN input manifest. It binds every file the bundle genuinely
reads, and there is no pair in it to bind: not defaulted to None, not hashed and ignored —
absent, because the producer has no such input.

Every entry is {name, size_bytes, sha256}. A machine-local path is never emitted: the same
science produced on tcefold and on a laptop must yield the same identity.
"""
from __future__ import annotations

from typing import Any

from . import emit

# The pinned Stage-2 inputs, by their STABLE release names. The key is what the artifact IS,
# never where this machine happened to keep it.
INPUT_NAMES = {
    "de_main": "GWCD4i.DE_stats.h5ad",
    "by_guide": "GWCD4i.DE_stats.by_guide.h5mu",
    "by_donors": "GWCD4i.DE_stats.by_donors.h5mu",
    "sgrna": "sgrna_library_metadata.suppl_table.csv",
    "guide_manifest": "guide_contributor_manifest.json",
    "source_registry": "source_registry.json",
    "target_identity_map": "target_identity_map.json",
    "donor_crosswalk": "donor_crosswalk.json",
    "strict_replay_source": "strict_replay_raw_source",
    "pseudobulk": "pseudobulk_source",
    "registry": "stage01_program_registry.json",
}

# What an all-arm bundle may NEVER bind. A pair is a JOIN of two arms, performed by whoever
# asks a question — it is not an input to the measurement, and a bundle that hashed one
# would be answerable only to that pair.
FORBIDDEN_INPUTS = ("selection", "contrast", "pair")


def bundle_input_manifest(args) -> list[dict[str, Any]]:
    """The pinned inputs THIS bundle consumed. No pair selection is read or hashed.

    An input that was not supplied is simply not in the manifest; supplying it later adds an
    entry and therefore changes the bundle id, which is the honest outcome — the run stood on
    different evidence. An input that WAS supplied but is missing on disk raises, loudly.
    """
    files = {name: getattr(args, attr, None)
             for attr, name in INPUT_NAMES.items()}
    return emit.input_manifest({name: path for name, path in files.items() if path})


def assert_no_pair_input(manifest: list[dict[str, Any]]) -> None:
    """A physical bundle that bound a pair is not a physical bundle. Refuse before writing."""
    named = [e["name"] for e in manifest
             if any(f in e["name"].lower() for f in FORBIDDEN_INPUTS)]
    if named:
        raise ValueError(
            f"an all-arm bundle bound a pair-scoped input {named}: its identity would be a "
            "function of a pair it never loaded, and the arms inside it could not be reused "
            "by any other pair")
