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
from verify_release_binding import SELF_EXCLUDED, Refusal, verify  # noqa: E402

ADMITTED_GATE = {
    "release_gates": {"app_deployment_ready": True, "overlay_release_ok": True},
    "not_lockable_reason_codes": [],
    "missing_required_artifacts": [],
}
CONTROL = {
    "_headers": "x",
    "_routes.json": "{}",
    "404.html": "<p>nf</p>",
    "landing.html": "<h1>spot</h1>",  # reviewer landing: a control surface, NOT the admitted index
    "site_release_manifest.json": "{}",
}
# The approved manifest non-recursively self-excludes; these bytes are bound by the deploy receipt.
RELEASE_MANIFEST_BODY = '{"release":"spot-8347-same-origin"}'


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
        # index.html is the ADMITTED app index (a meta-refresh stub), manifest-bound. It must
        # survive packaging byte-for-byte; the reviewer landing ships as landing.html.
        self.app = {
            "index.html": '<meta http-equiv="refresh" content="0; url=/programs.html">',
            "programs.html": "<h1>stage one</h1>",
            "assets/app-abc123.js": "export const a=1",
            "results/current.json": json.dumps(
                {"verifier_status": "admitted", "generator_status": "generated",
                 "target_namespace": "ensembl_gene_id", "active_pathway_source": "go_bp"}
            ),
        }
        self.gate = dict(ADMITTED_GATE)

    def write_dist(self, extra: dict[str, str] | None = None) -> None:
        bodies = {**self.app, **CONTROL, SELF_EXCLUDED: RELEASE_MANIFEST_BODY, **(extra or {})}
        for rel, body in bodies.items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (self.dist / "data" / "stage01_release_manifest.json").write_text(json.dumps(self.gate), encoding="utf-8")

    def approved(self, files: dict[str, str] | None = None) -> Path:
        source = self.app if files is None else files
        manifest = {
            "release": "spot-8347-same-origin",
            # Non-recursive self-exclude: release_manifest.json is deliberately NOT in files[].
            "manifest_self": {"path": SELF_EXCLUDED, "accounting": "sha256 in external receipt"},
            "files": [{"path": rel, "sha256": sha(body), "class": "built"} for rel, body in source.items()],
        }
        manifest["files"].append(
            {"path": "data/stage01_release_manifest.json", "sha256": sha(json.dumps(self.gate)), "class": "data"}
        )
        path = self.root / "approved.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def receipt(self, body: str | None = None) -> Path:
        path = self.root / "deployed_manifest.txt"
        path.write_text(
            body if body is not None else f"{sha(RELEASE_MANIFEST_BODY)}  {SELF_EXCLUDED}  meta\n",
            encoding="utf-8",
        )
        return path

    def parked(self, lines: str = "") -> Path:
        path = self.root / "parked.allowlist"
        path.write_text(lines, encoding="utf-8")
        return path

    def run_gate(self, parked: str = "", receipt: Path | None = -1) -> list[str]:  # type: ignore[assignment]
        rcpt = self.receipt() if receipt == -1 else receipt
        return verify(self.dist, self.approved(), None, self.parked(parked), rcpt)

    def test_admits_an_exact_admitted_distribution(self) -> None:
        self.write_dist()
        self.assertEqual(self.run_gate(), [])

    def test_refuses_a_drifted_byte(self) -> None:
        self.write_dist()
        (self.dist / "programs.html").write_text("<h1>rebuilt</h1>", encoding="utf-8")
        self.assertRegex(self.run_gate()[0], r"^DRIFT: programs\.html")

    def test_refuses_a_file_absent_from_the_approved_manifest(self) -> None:
        self.write_dist({"assets/sneaky-x1.js": "1"})
        self.assertRegex(self.run_gate()[0], r"^UNLISTED: assets/sneaky-x1\.js")

    def test_refuses_a_duplicate_legacy_programs_page(self) -> None:
        self.write_dist({"01_page.html": "<h1>legacy duplicate</h1>"})
        self.assertIn("UNLISTED: 01_page.html is packaged but not in the approved release manifest", self.run_gate())

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
        self.app["programs.html"] = '<html data-placeholder="true"><p>hello</p></html>'
        self.write_dist()
        self.assertRegex(self.run_gate()[0], r"^PLACEHOLDER: programs\.html")

    def test_refuses_interim_copy_separately_from_a_placeholder_route(self) -> None:
        # Prose is not a route. The landing's About copy says the workbench is "being
        # assembled", which is true today and false at full release — report it as its own
        # finding rather than mislabelling the page a placeholder.
        self.app["programs.html"] = "<html><p>The full workbench is being assembled.</p></html>"
        self.write_dist()
        findings = self.run_gate()
        self.assertRegex(findings[0], r"^INTERIM_COPY: programs\.html")
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

    # --- self-excluded release_manifest.json is bound by the EXTERNAL receipt, not files[] ---

    def test_admits_the_self_excluded_manifest_bound_by_the_receipt(self) -> None:
        self.write_dist()
        self.assertEqual(self.run_gate(), [])  # copying it must NOT read as UNLISTED

    def test_refuses_a_drifted_self_excluded_manifest(self) -> None:
        self.write_dist({SELF_EXCLUDED: '{"release":"tampered"}'})
        self.assertRegex(self.run_gate()[0], rf"^DRIFT: {SELF_EXCLUDED} sha256 .* != receipt")

    def test_refuses_when_the_receipt_does_not_bind_the_manifest(self) -> None:
        self.write_dist()
        findings = self.run_gate(receipt=self.receipt("deadbeef  something_else  meta\n"))
        self.assertRegex(findings[0], r"^RECEIPT: .*does not bind release_manifest\.json")

    def test_refuses_when_no_receipt_is_supplied(self) -> None:
        self.write_dist()
        self.assertRegex(self.run_gate(receipt=None)[0], r"^RECEIPT: no deploy receipt supplied")

    def test_refuses_a_manifest_that_lists_itself(self) -> None:
        self.app[SELF_EXCLUDED] = RELEASE_MANIFEST_BODY  # forces it into files[]
        self.write_dist()
        self.assertRegex(self.run_gate()[0], r"^SELF_EXCLUDE:")

    # --- the admitted index.html must survive; the landing is a separate control surface ---

    def test_refuses_when_the_admitted_index_is_omitted_for_the_landing(self) -> None:
        self.write_dist()
        (self.dist / "index.html").unlink()
        findings = self.run_gate()
        self.assertTrue([f for f in findings if f.startswith("INDEX:")], findings)
        self.assertTrue([f for f in findings if f.startswith("MISSING: admitted artifact index.html")], findings)

    def test_refuses_when_the_landing_overwrites_the_admitted_index(self) -> None:
        self.write_dist({"index.html": "<h1>spot</h1>"})  # reviewer landing written over the stub
        self.assertRegex(self.run_gate()[0], r"^DRIFT: index\.html")

    def test_refuses_a_missing_landing_control_surface(self) -> None:
        self.write_dist()
        (self.dist / "landing.html").unlink()
        self.assertIn("CONTROL: required Pages control file landing.html is absent", self.run_gate())

    # --- results claims are PARSED, not pattern-matched ---

    def test_refuses_a_reactome_sourced_results_claim(self) -> None:
        self.app["results/current.json"] = json.dumps({"active_pathway_source": "reactome"})
        self.write_dist()
        finding = [f for f in self.run_gate() if f.startswith("CLAIMS:")][0]
        self.assertIn("active_pathway_source='reactome'", finding)

    def test_refuses_a_results_artifact_that_is_not_admitted(self) -> None:
        for field, bad in (("verifier_status", "pending"), ("generator_status", "fixture"),
                           ("target_namespace", "hgnc_symbol")):
            with self.subTest(field=field):
                self.app["results/current.json"] = json.dumps({field: bad})
                self.write_dist()
                findings = [f for f in self.run_gate() if f.startswith("CLAIMS:")]
                self.assertTrue(findings, f"{field}={bad} must be refused")
                self.assertIn(f"{field}={bad!r}", findings[0])

    def test_refuses_a_non_production_claim_in_any_results_field(self) -> None:
        self.app["results/current.json"] = json.dumps({"analysis_mode": "synthetic"})
        self.write_dist()
        finding = [f for f in self.run_gate() if f.startswith("CLAIMS:")][0]
        self.assertIn("non-production artifact", finding)

    def test_refuses_an_unbound_approved_manifest(self) -> None:
        self.write_dist()
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"files": [{"path": "programs.html"}]}), encoding="utf-8")
        with self.assertRaisesRegex(Refusal, "not hash-bound"):
            verify(self.dist, bad, None, self.parked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
