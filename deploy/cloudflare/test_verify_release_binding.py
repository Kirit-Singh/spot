#!/usr/bin/env python3
"""Contract for the full-app release-binding gate.

Every check is fail-closed, so each test drives the gate to a REFUSAL and asserts the exact
reason. A gate that cannot be made to refuse is not a gate.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_release_binding import Refusal, verify  # noqa: E402

ADMITTED_GATE = {
    "release_gates": {"app_deployment_ready": True, "overlay_release_ok": True},
    "not_lockable_reason_codes": [],
    "missing_required_artifacts": [],
}
CONTROL = {"_headers": "x", "_routes.json": "{}", "404.html": "<p>nf</p>", "site_release_manifest.json": "{}"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ReleaseBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dist = self.root / "dist"
        (self.dist / "data").mkdir(parents=True)
        (self.dist / "assets").mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)
        self.app = {"01_page.html": "<h1>stage one</h1>", "assets/app-abc123.js": "export const a=1"}
        self.gate = dict(ADMITTED_GATE)

    def write_dist(self, extra: dict[str, str] | None = None) -> None:
        for rel, body in {**self.app, **CONTROL, **(extra or {})}.items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (self.dist / "data" / "stage01_release_manifest.json").write_text(json.dumps(self.gate), encoding="utf-8")

    def approved(self, files: dict[str, str] | None = None) -> Path:
        source = self.app if files is None else files
        manifest = {
            "release": "spot-8347-same-origin",
            "files": [{"path": rel, "sha256": sha(body), "class": "built"} for rel, body in source.items()],
        }
        # The gate manifest is itself a served artifact and must be admitted.
        manifest["files"].append(
            {"path": "data/stage01_release_manifest.json", "sha256": sha(json.dumps(self.gate)), "class": "data"}
        )
        path = self.root / "approved.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def parked(self, lines: str = "") -> Path:
        path = self.root / "parked.allowlist"
        path.write_text(lines, encoding="utf-8")
        return path

    def run_gate(self, parked: str = "") -> list[str]:
        return verify(self.dist, self.approved(), None, self.parked(parked))

    def test_admits_an_exact_admitted_distribution(self) -> None:
        self.write_dist()
        self.assertEqual(self.run_gate(), [])

    def test_refuses_a_drifted_byte(self) -> None:
        self.write_dist()
        (self.dist / "01_page.html").write_text("<h1>rebuilt</h1>", encoding="utf-8")
        self.assertRegex(self.run_gate()[0], r"^DRIFT: 01_page\.html")

    def test_refuses_a_file_absent_from_the_approved_manifest(self) -> None:
        self.write_dist({"assets/sneaky-x1.js": "1"})
        self.assertRegex(self.run_gate()[0], r"^UNLISTED: assets/sneaky-x1\.js")

    def test_refuses_a_silently_dropped_admitted_artifact(self) -> None:
        self.write_dist()
        (self.dist / "assets" / "app-abc123.js").unlink()
        self.assertRegex(self.run_gate()[0], r"^MISSING: admitted artifact assets/app-abc123\.js")

    def test_refuses_reactome_release_metadata_in_a_served_byte(self) -> None:
        self.app["assets/app-abc123.js"] = "const s=`Reactome V97 ReactomePathways.gmt.zip`"
        self.write_dist()
        finding = self.run_gate()[0]
        self.assertRegex(finding, r"^REACTOME: assets/app-abc123\.js")
        self.assertIn("GO-BP-only", finding)

    def test_permits_reactome_only_in_an_explicitly_parked_license_history_file(self) -> None:
        self.app["DATA_LICENSES.txt"] = "Reactome: CC0-1.0 (evaluated, not part of this release)"
        self.write_dist()
        self.assertEqual(self.run_gate(parked="DATA_LICENSES.txt\n"), [])
        # ...and parking one file does not park any other.
        self.app["assets/app-abc123.js"] = "const s=`Reactome V97`"
        self.write_dist()
        self.assertRegex(self.run_gate(parked="DATA_LICENSES.txt\n")[0], r"^REACTOME: assets/app-abc123\.js")

    def test_refuses_a_fixture_classed_artifact(self) -> None:
        self.app["assets/app-abc123.js"] = "const id=`fixture:stage02:arm_a@0badc0de`"
        self.write_dist()
        self.assertRegex(self.run_gate()[0], r"^FIXTURE: assets/app-abc123\.js")

    def test_refuses_a_placeholder_route(self) -> None:
        self.app["01_page.html"] = '<html data-placeholder="true"><p>hello</p></html>'
        self.write_dist()
        self.assertRegex(self.run_gate()[0], r"^PLACEHOLDER: 01_page\.html")

    def test_refuses_interim_copy_separately_from_a_placeholder_route(self) -> None:
        # Prose is not a route. The landing's About copy says the workbench is "being
        # assembled", which is true today and false at full release — report it as its own
        # finding rather than mislabelling the page a placeholder.
        self.app["01_page.html"] = "<html><p>The full workbench is being assembled.</p></html>"
        self.write_dist()
        findings = self.run_gate()
        self.assertRegex(findings[0], r"^INTERIM_COPY: 01_page\.html")
        self.assertFalse([f for f in findings if f.startswith("PLACEHOLDER:")])

    def test_refuses_a_stage1_gate_that_has_not_admitted_deployment(self) -> None:
        for gate, pattern in (
            ({**ADMITTED_GATE, "release_gates": {"app_deployment_ready": False, "overlay_release_ok": True}},
             r"app_deployment_ready"),
            ({**ADMITTED_GATE, "release_gates": {"app_deployment_ready": True, "overlay_release_ok": False}},
             r"overlay_release_ok is false"),
            ({**ADMITTED_GATE, "not_lockable_reason_codes": ["overlay_release_blocked"]}, r"not lockable"),
            ({**ADMITTED_GATE, "missing_required_artifacts": ["x.json"]}, r"missing required artifacts"),
        ):
            with self.subTest(gate=gate):
                self.gate = gate
                self.write_dist()
                findings = self.run_gate()
                self.assertTrue(findings and findings[0].startswith("GATE: "), findings)
                self.assertRegex(findings[0], pattern)

    def test_refuses_a_missing_pages_control_file(self) -> None:
        self.write_dist()
        (self.dist / "_routes.json").unlink()
        self.assertIn("CONTROL: required Pages control file _routes.json is absent", self.run_gate())

    def test_refuses_an_unbound_approved_manifest(self) -> None:
        self.write_dist()
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"files": [{"path": "01_page.html"}]}), encoding="utf-8")
        with self.assertRaisesRegex(Refusal, "not hash-bound"):
            verify(self.dist, bad, None, self.parked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
