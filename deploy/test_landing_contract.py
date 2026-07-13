#!/usr/bin/env python3
"""Static contract checks for the reviewer landing page.

Authentication endpoint and middleware behavior are covered by the Cloudflare
closeout integration tests; this file keeps the public HTML contract fail-closed.
"""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[1]
LANDING = REPO / "01_programs" / "app" / "index.html"
BUILD = REPO / "deploy" / "build_dist.sh"


class LandingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())

    def one(self, tag: str, **attrs: str) -> dict[str, str | None]:
        matches = [
            actual
            for actual_tag, actual in self.tags
            if actual_tag == tag and all(actual.get(key) == value for key, value in attrs.items())
        ]
        if len(matches) != 1:
            raise AssertionError(f"expected one <{tag}> matching {attrs}, found {len(matches)}")
        return matches[0]


class LandingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = LANDING.read_text(encoding="utf-8")
        cls.parser = LandingParser()
        cls.parser.feed(cls.html)

    def test_brand_and_canonical_stage1_mark(self) -> None:
        self.assertIn("spot", self.parser.text)
        favicon = self.parser.one("link", rel="icon")["href"] or ""
        self.assertIn("%23FAF9F7", favicon)
        self.assertIn("%233E7D8C", favicon)
        self.assertIn("r='4.6'", favicon)
        self.assertNotIn("863bff", self.html.lower())

    def test_disclosure_and_form_are_semantic(self) -> None:
        self.parser.one("details", id="reviewer-access")
        summary = self.parser.one("summary", **{"aria-label": "Open reviewer access"})
        self.assertNotIn("aria-expanded", summary)
        form = self.parser.one("form", action="/auth")
        self.assertEqual(form.get("method"), "post")
        field = self.parser.one("input", id="access-code")
        self.assertEqual(field.get("name"), "code")
        self.assertEqual(field.get("type"), "password")
        self.assertIn("required", field)
        self.parser.one("button", **{"type": "submit", "aria-label": "Open spot"})

    def test_access_code_is_not_shipped_to_the_browser(self) -> None:
        field = self.parser.one("input", id="access-code")
        self.assertNotIn("value", field)
        self.assertNotRegex(self.html, re.compile(r"(?:code|password)\s*={2,3}", re.I))
        self.assertNotRegex(self.html, re.compile(r"location\.(?:assign|replace|href).*01_page", re.I))
        external = []
        for tag, attrs in self.parser.tags:
            for key in ("src", "href", "action"):
                value = attrs.get(key) or ""
                if re.match(r"https?://", value, re.I):
                    external.append((tag, key, value))
        self.assertEqual(external, [])

    def test_keyboard_and_error_feedback_hooks_exist(self) -> None:
        self.assertIn("event.key==='Escape'", self.html)
        self.assertIn("summary.setAttribute('aria-expanded'", self.html)
        self.assertIn("syncExpanded();", self.html)
        self.assertIn("aria-invalid", self.html)
        self.assertIn("aria-live=\"polite\"", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.html)
        self.assertIn("forced-colors:active", self.html)

    def test_build_copies_reviewed_landing_without_regenerating_redirect(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        self.assertIn('cp "$APP/index.html"', build)
        self.assertNotIn("http-equiv=\"refresh\"", build)
        self.assertNotIn("cat > \"$DIST/index.html\"", build)


if __name__ == "__main__":
    unittest.main()
