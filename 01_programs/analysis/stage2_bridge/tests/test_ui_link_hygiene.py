"""Regression scan for the Stage-1 canonical page (01_page.html): no VISIBLE link may target a retired
methods / notebook / trace PAGE — the header "Methods & provenance" drawer is the sole primary methods
surface — while the reproduce.sh script link is retained. Guards the nav + drawer consolidation cleanup.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PAGE = os.path.join(REPO, "01_programs", "app", "01_page.html")

# <a href="X"> targets that must NOT appear: a separate notebook/trace/methods/provenance page.
FORBIDDEN = re.compile(r"01_notebook|01_trace|(?:^|/)(?:methods|provenance)[._-]?\w*\.html", re.I)
AHREF = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.I)


def _hrefs():
    return AHREF.findall(open(PAGE, encoding="utf-8").read())


def test_no_ui_link_targets_notebook_trace_or_methods_page():
    offenders = [h for h in _hrefs() if FORBIDDEN.search(h)]
    assert not offenders, "Stage-1 UI links to a retired methods/notebook/trace page: " + repr(offenders)


def test_reproduce_sh_link_retained():
    assert any("reproduce.sh" in h for h in _hrefs()), "the reproduce.sh script link must remain in 01_page.html"


def test_five_route_nav_present():
    """Positive control for the current five-route nav (Programs + Targets/Pathways/Drugs/PK & Safety)."""
    text = open(PAGE, encoding="utf-8").read()
    for href in ("targets.html", "pathways.html", "drugs.html", "pksafety.html"):
        assert f'href="{href}"' in text, f"nav route {href} missing"
    assert "02_page.html#/stage-" not in text, "stale /02_page.html#/stage-N nav routes must be gone"
