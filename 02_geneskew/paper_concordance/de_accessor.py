"""Thin h5py accessor over the pinned DE object (IO glue).

The deterministic sign logic lives in ``sign_derivation`` and is tested against a fake
``observe``; this module only reads real cells. ``observe(regulator_symbol, cytokine_symbol,
condition)`` returns the exact ``log_fc`` and upstream ``adj_p_value`` at the
(perturbation row ``{ENSG}_{condition}``, cytokine column). Backed read: it never loads the
33983x10282 matrix, only the requested cells.
"""
from __future__ import annotations

from typing import Any

import h5py


def _decode(x: Any) -> Any:
    return x.decode() if isinstance(x, bytes) else str(x)


class DEAccessor:
    def __init__(self, path: str) -> None:
        self.path = path
        self._f = h5py.File(path, "r")
        names = [_decode(x) for x in self._f["var/gene_name"][:]]
        self.name2col: dict[str, int] = {}
        for i, n in enumerate(names):
            self.name2col.setdefault(n, i)
        keys = [_decode(x) for x in self._f["obs/index"][:]]
        self.rowkey2row = {k: i for i, k in enumerate(keys)}
        syms = self._read_cat("obs/target_contrast_gene_name")
        ensgs = self._read_cat("obs/target_contrast")
        self.sym2ensg: dict[str, str] = {}
        for s, e in zip(syms, ensgs):
            if s is not None and e is not None:
                self.sym2ensg.setdefault(s, e)
        self.log_fc = self._f["layers/log_fc"]
        self.adj_p = self._f["layers/adj_p_value"]

    def _read_cat(self, path: str) -> list:
        node = self._f[path]
        if isinstance(node, h5py.Group):        # anndata categorical: categories + codes
            cats = [_decode(x) for x in node["categories"][:]]
            return [cats[c] if c >= 0 else None for c in node["codes"][:]]
        return [_decode(x) for x in node[:]]

    def observe(self, regulator: str, cytokine: str, condition: str) -> dict[str, Any]:
        ensg = self.sym2ensg.get(regulator)
        col = self.name2col.get(cytokine)
        if ensg is None or col is None:
            return {"present": False}
        row = self.rowkey2row.get(f"{ensg}_{condition}")
        if row is None:
            return {"present": False}
        return {"present": True, "log_fc": float(self.log_fc[row, col]),
                "adj_p": float(self.adj_p[row, col])}

    def close(self) -> None:
        self._f.close()
