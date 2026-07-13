# Reviewer landing closeout contract

This is a closeout-only surface. It must not be merged into or deployed over the active scientific workbench until the Stage 1–4 release is admitted.

## Canonical host and routes

- Canonical origin: `https://spotpathways.com`.
- `https://spotpathway.com/<path>?<query>` permanently redirects to the same path and query on `https://spotpathways.com` before authentication or cookie handling.
- Public routes: `/` and `POST /auth` only. The landing is self-contained and makes no third-party requests.
- Reviewer routes: `/01_page.html` and every other shipped app page, asset, manifest, and data artifact. An unauthenticated deep link returns to `/`; it must never expose app bytes first.
- Successful access always returns `303 Location: /01_page.html`.

## Visual contract

The root page contains only a centered `spot` wordmark and its clickable dot, followed by the access control when expanded. It has no subtitle, footer, announcement, warning, or editorial banner.

Reuse the Stage-1 source-of-truth tokens from `01_programs/app/01_page.html`: warm background `#FAF9F7`, ink `#1E1B16`, teal accent `#3E7D8C`, line `#E7E3DC`, the `Newsreader` font stack for the wordmark, the `IBM Plex Mono` stack for the access control, and the existing focus ring. The landing must not call Google Fonts or any other third party; closeout may self-host admitted font files, otherwise the declared system fallbacks apply. The mark is the exact current tab geometry: a `16 × 16` viewBox, warm rounded-square background (`rx=4`), and centered teal circle (`cx=8`, `cy=8`, `r=4.6`). Do not use the unrelated purple-bolt `favicon.svg`.

The dot has a 48-pixel interaction box even though the visible circle is smaller. Activation expands one 44-pixel-high password field with a 44-pixel submit action. The control is no wider than 272 pixels and remains inside a 20-pixel mobile gutter.

## Interaction and accessibility

- The dot is a native `summary` disclosure named “Open reviewer access.” Mouse click, touch, Enter, and Space toggle it; its `aria-expanded` value mirrors the native open state.
- Opening moves focus to the password field. Enter in the field submits. The arrow button is named “Open spot.”
- Escape closes the disclosure and returns focus to the dot.
- Invalid access returns to `/?access=invalid`; the page removes that query marker from the address bar, reopens the control, retains focus, marks the field invalid, and announces the compact inline text “Code not recognized.” via a polite live region.
- The page respects reduced motion and forced colors. The input stays at 16 pixels to avoid mobile browser zoom. Safe-area insets and `100dvh` are supported.
- With JavaScript unavailable, the native disclosure and POST form still work; JavaScript only improves focus, Escape, and inline invalid-code feedback.

## Authentication boundary

The reviewer code is provisioned as a Cloudflare encrypted secret and is never emitted into HTML, JavaScript, Git, a URL, or an analytics/log field. The static form posts `application/x-www-form-urlencoded` data to the exact endpoint `/auth`; the Pages Function performs a constant-time comparison and rate limiting and must never log the request body.

On success, issue a signed, opaque session in a host-only cookie named with a `__Host-` prefix and attributes `Secure; HttpOnly; SameSite=Lax; Path=/`. Do not place the access code or session in `localStorage` or `sessionStorage`. The session middleware must run before serving every reviewer page and artifact, not only `/01_page.html`.

Wrong, missing, or malformed codes receive the same generic redirect and visible response. The POST response and protected responses use `Cache-Control: no-store`. Requests from the singular domain never receive a reviewer cookie; they redirect to the plural canonical host first.

## Acceptance tests

1. Static contract: `python3 deploy/test_landing_contract.py`.
2. Distribution: build to a temporary directory and byte-compare its `index.html` with `01_programs/app/index.html`; verify there is no meta refresh and `/` returns 200.
3. Browser, desktop and 320-pixel mobile: initial page contains only `spot` + dot; dot click and keyboard activation reveal one field; focus moves correctly; Escape closes; there is no horizontal overflow; reduced-motion and forced-colors modes remain operable.
4. Authentication integration: wrong/missing/malformed codes return to a generic invalid state; the provisioned reviewer code produces a host-only cookie and `303 /01_page.html`; the code never appears in URLs or response bodies.
5. Boundary: without the cookie, direct GETs of every HTML/JS/CSS/data/manifest route do not return protected bytes. With the cookie, all admitted files load and Stage 1–4 smoke tests pass.
6. Canonicalization: every singular-domain route redirects to the byte-equivalent plural-domain URL; no cookie is set on the singular response; query strings are preserved; redirect loops are absent.
7. Session: tampered, expired, and cross-host cookies fail closed. Sign-out/session expiry returns the browser to `/` without leaking protected cached content.

The access endpoint and middleware are deliberately outside this UI-only prototype and belong to the Cloudflare closeout lane.
