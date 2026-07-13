"""spot Stage-2 primary — direct measured perturbation screen.

Pure, deterministic core (hashing, config, contrast, masks, projection) is
importable without the heavy single-cell stack; ``run_screen`` is the IO
orchestrator that reads the pinned DE_stats artifacts on the configured analysis host.
"""
