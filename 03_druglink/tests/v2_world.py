"""Shared helpers for the Stage-3 v2 verifier attacks. NON-PRODUCTION fixtures only.

The sealed world is built once per session (``v2_world`` in ``conftest.py``): a 15-bundle /
300-arm Stage-2 aggregate, a universe store, and a v2 bundle emitted from both by the
stand-in producer. Every attack starts from those honest bytes and breaks exactly one thing,
so the refusal names the thing that broke.
"""
from __future__ import annotations

import os

import pandas as pd
import v2_producer as P
from v2_fixture import write_aggregate, write_store

from verifier import v2_contract as C
from verifier import verify_stage3_v2 as V

STAGE3 = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
VERIFIER_DIR = os.path.join(STAGE3, "verifier")


def build_world(root: str) -> dict:
    paths = write_aggregate(os.path.join(root, "aggregate"))
    store = write_store(os.path.join(root, "store"))
    bundle = P.build(paths, store, os.path.join(root, "out"))
    return {"paths": paths, "store": store, "bundle": bundle, "root": root}


def verify(world, bundle=None, artifact_class="fixture", **over):
    kw = dict(bundle=bundle or world["bundle"],
              stage2_aggregate_manifest=world["paths"]["manifest"],
              stage2_aggregate_report=world["paths"]["report"],
              stage2_bundles_root=world["paths"]["bundles_root"],
              stage1_release=world["paths"]["stage1_release"],
              universe_store=world["store"], artifact_class=artifact_class)
    kw.update(over)
    return V.verify(**kw)


def rebuild(world, output_root, **hooks) -> str:
    """Re-emit the bundle with exactly one thing broken, fully sealed and self-consistent.

    A resealed forgery is the real test: a content hash catches nothing from an attacker who
    remembers to recompute it, so the verifier has to catch it on the SOURCES.
    """
    return P.build(world["paths"], world["store"], str(output_root), **hooks)


def refused(rep, gate) -> list[str]:
    """The report REFUSED at exactly this NAMED gate."""
    return [n for n, _d in rep.failures if f"[{gate}]" in n]


def named(rep, fragment) -> list[str]:
    return [n for n, _d in rep.failures if fragment in n]


def tables(bundle) -> dict:
    return {name: pd.read_parquet(os.path.join(bundle, f"{name}.parquet"))
            for name in C.TABLES}


def add_column(bundle, table, column, value) -> None:
    """Inject a column and RESEAL the file hashes, so only the column gate can catch it."""
    path = os.path.join(bundle, f"{table}.parquet")
    frame = pd.read_parquet(path)
    frame[column] = value
    frame.to_parquet(path, index=False)
    P.reseal_file_hashes(bundle)
