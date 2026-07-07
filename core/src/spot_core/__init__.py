"""spot_core — the deterministic evidence engine (Lane A).

No LLM and no network at import time. Submodules land per chunk:
``data`` (loaders/lazy-stream), ``evidence`` (verification brain + scoring),
``confirm`` (Census/Open Targets/GEO adapters), ``graph`` (assembly).
"""

__version__ = "0.0.0"
