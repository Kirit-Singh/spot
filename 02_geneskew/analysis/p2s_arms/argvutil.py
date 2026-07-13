"""Sanitize an argv for provenance: machine-local PATHS become basenames; flags stay.

A real invocation's argv is full of ``/home/...`` paths, and the emitted provenance is checked
by a machine-path firewall that rejects the whole run for carrying one. The FLAGS and the
basenames are provenance; the absolute directory is the how-it-was-found, never the what-it-is.
Shared by ``prepare_inputs`` and ``run_p2s_arms`` so both sanitize identically.
"""
from __future__ import annotations

import os


def sanitize_argv(tokens: list[str]) -> list[str]:
    out = []
    for tok in tokens:
        if str(tok).startswith("--"):
            out.append(tok)
        elif os.path.isabs(str(tok)):
            out.append(os.path.basename(str(tok).rstrip("/")) or tok)
        else:
            out.append(tok)
    return out
