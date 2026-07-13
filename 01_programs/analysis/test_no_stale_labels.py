"""S1-M3 re-audit: a served-artifact stale-label scan.

No served UI/data artifact may carry a RETIRED program display label. The checkpoint program's active
label is bare ``Checkpoint`` (dropped ``Checkpoint-high`` then the ``Checkpoint+`` interim). This fails if
either retired label reappears in a served artifact — e.g. a notebook re-render or seed edit that reverts.
(Historical references in docs/ are out of scope: those record the rename intentionally.)
"""
import os

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
STALE_LABELS = ["Checkpoint-high", "Checkpoint+"]
SERVED = [
    "01_page.html",
    "01_notebook.html",
    "data/stage01_umap_seed.json",
    "data/stage01_program_registry_v3.json",
    "data/stage01_activation_association_v1.json",
    "data/stage01_selection_bundle.json",
]


def test_no_stale_program_labels_in_served_artifacts():
    hits = []
    for rel in SERVED:
        p = os.path.join(APP, rel)
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8", errors="replace").read()
        for s in STALE_LABELS:
            if s in txt:
                hits.append(f"{rel}: {s!r} x{txt.count(s)}")
    assert not hits, f"retired program label(s) present in served artifacts: {hits}"
