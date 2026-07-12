"""Put the package dir (for `import canonical`, `import build_*`) and the analysis dir
(for `import verify_stage1_provenance`) on sys.path for pytest."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
for p in (HERE, ANALYSIS):
    if p not in sys.path:
        sys.path.insert(0, p)
