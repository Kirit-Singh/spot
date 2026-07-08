"""spot_pipeline — the from-raw ingest driver.

Owns the manifest gate + run planning; a workflow engine (Nextflow-in-container)
owns DAG execution. The gate lives in contracts.DatasetManifest.
"""

from spot_pipeline.driver import STAGES, RunPlan, load_manifest, main, plan_run

__all__ = ["STAGES", "RunPlan", "load_manifest", "main", "plan_run"]
