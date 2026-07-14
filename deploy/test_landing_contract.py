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

    def test_access_field_does_not_invite_password_manager_autofill(self) -> None:
        # The reviewer code is a shared deployment secret, not a saved site credential.
        # A lone type=password field with autocomplete="current-password" lets a password
        # manager silently overwrite the typed code, which surfaces as "Code not recognized."
        field = self.parser.one("input", id="access-code")
        self.assertEqual(field.get("type"), "password")  # still masked on screen
        self.assertNotEqual(field.get("autocomplete"), "current-password")
        self.assertEqual(field.get("autocomplete"), "one-time-code")
        self.assertIn("data-1p-ignore", field)
        self.assertEqual(field.get("data-lpignore"), "true")
        self.assertIn("data-bwignore", field)

    def test_access_code_is_not_shipped_to_the_browser(self) -> None:
        field = self.parser.one("input", id="access-code")
        self.assertNotIn("value", field)
        self.assertNotRegex(self.html, re.compile(r"(?:code|password)\s*={2,3}", re.I))
        self.assertNotRegex(self.html, re.compile(r"location\.(?:assign|replace|href).*01_page", re.I))

    def test_page_issues_no_third_party_request(self) -> None:
        # The guarantee is that the page FETCHES nothing third-party. An <a href> is a
        # user-initiated navigation and issues no request, so outbound links are allowed;
        # anything that would load a resource (script, stylesheet, font, image, iframe)
        # or post a form must stay first-party.
        fetching = []
        for tag, attrs in self.parser.tags:
            for key in ("src", "action"):
                value = attrs.get(key) or ""
                if re.match(r"https?://", value, re.I):
                    fetching.append((tag, key, value))
            if tag != "a":
                value = attrs.get("href") or ""
                if re.match(r"https?://", value, re.I):
                    fetching.append((tag, "href", value))
        self.assertEqual(fetching, [])

    def test_outbound_links_cannot_leak_the_opener_or_referrer(self) -> None:
        anchors = [
            attrs
            for tag, attrs in self.parser.tags
            if tag == "a" and re.match(r"https?://", attrs.get("href") or "", re.I)
        ]
        self.assertTrue(anchors, "expected the About links to be present")
        for anchor in anchors:
            self.assertTrue((anchor.get("href") or "").startswith("https://github.com/"))
            self.assertEqual(anchor.get("target"), "_blank")
            rel = anchor.get("rel") or ""
            self.assertIn("noopener", rel)
            self.assertIn("noreferrer", rel)

    def test_reveal_and_about_are_progressive_enhancements(self) -> None:
        # Both ship hidden and are unhidden by script, so no dead control is offered
        # when JavaScript is unavailable, and neither may submit the form.
        for control_id in ("reveal-code", "about-open"):
            control = self.parser.one("button", id=control_id)
            self.assertEqual(control.get("type"), "button")
            self.assertIn("hidden", control)
            self.assertIsNotNone(control.get("aria-label"))
        self.assertIn("reveal.hidden=false", self.html)
        self.assertIn("openAbout.hidden=false", self.html)
        # The field must still be shipped masked; only the toggle may reveal it.
        self.assertEqual(self.parser.one("input", id="access-code").get("type"), "password")

    def test_attribution_lives_in_the_about_dialog(self) -> None:
        # The root surface stays a bare wordmark + mark: no footer, no banner. The
        # credit is reachable only through the About control.
        self.assertIn("Kirit Singh . 2026", self.html)
        self.assertNotIn("<footer", self.html)
        self.parser.one("dialog", id="about")

    def test_keyboard_and_error_feedback_hooks_exist(self) -> None:
        self.assertIn("event.key==='Escape'", self.html)
        self.assertIn("summary.setAttribute('aria-expanded'", self.html)
        self.assertIn("syncExpanded();", self.html)
        self.assertIn("aria-invalid", self.html)
        self.assertIn("aria-live=\"polite\"", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.html)
        self.assertIn("forced-colors:active", self.html)

    def test_access_panel_starts_at_wordmark_left_edge(self) -> None:
        self.assertRegex(self.html, re.compile(r"\.panel\s*\{[^}]*\bleft:0;", re.S))
        self.assertIn("width:min(316px,calc(50vw + 50% - 20px))", self.html)
        self.assertNotIn("transform:translateX(-50%)", self.html)

    def test_build_copies_reviewed_landing_without_regenerating_redirect(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        self.assertIn('cp "$APP/index.html"', build)
        self.assertNotIn("http-equiv=\"refresh\"", build)
        self.assertNotIn("cat > \"$DIST/index.html\"", build)


if __name__ == "__main__":
    unittest.main()
