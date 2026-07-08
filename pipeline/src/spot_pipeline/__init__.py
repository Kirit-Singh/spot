"""spot_pipeline — the from-raw ingest driver + tested QC logic.

The QC logic (spot_pipeline.qc) is numpy-only and imports cleanly on its own; the
driver needs spot_contracts, which the lightweight cellqc stage image does not
install. Guard the driver import so `import spot_pipeline.qc` works there.
"""

from spot_pipeline.qc import assign_guides, cell_qc_mask, mad_low_bound

try:
    from spot_pipeline.driver import STAGES, RunPlan, load_manifest, main, plan_run
except ModuleNotFoundError:  # spot_contracts absent (e.g. the cellqc stage image)
    __all__ = ["assign_guides", "cell_qc_mask", "mad_low_bound"]
else:
    __all__ = [
        "STAGES",
        "RunPlan",
        "assign_guides",
        "cell_qc_mask",
        "load_manifest",
        "mad_low_bound",
        "main",
        "plan_run",
    ]
