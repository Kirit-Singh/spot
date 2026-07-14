import {
  PLACEHOLDER_HOST,
  PROGRAMS_PATH,
  canonicalRedirectTarget,
  constantTimeSecretEqual,
  issueSession,
  localHostAllowed,
  operationalFailure,
  productionHostDecision,
  redirect,
  sessionCookie,
  withSecurityHeaders,
  type PagesContext,
} from './lib/reviewerGate';

const MAX_BODY_BYTES = 512;

function invalidAccess(): Response {
  return redirect('/?access=invalid', 303);
}

// A null expectedOrigin means "match the request's own host" (local dev); otherwise the
// Origin must equal the exact expected origin for the active mode.
//
// A same-origin form POST is a NAVIGATION, and this app serves every response with
// Referrer-Policy: no-referrer — so the browser sends `Origin: null` (an opaque origin)
// and no Referer. A strict `origin === expected` check therefore rejects every genuine
// browser submission while still admitting curl/fetch, which set a real Origin.
//
// Sec-Fetch-Site is the reliable signal: it is a forbidden header set by the browser and
// cannot be forged by a page, and a cross-context submission never gets `same-origin`.
function sameOrigin(request: Request, expectedOrigin: string | null): boolean {
  const site = request.headers.get('Sec-Fetch-Site');
  const origin = request.headers.get('Origin');

  // When the browser states the context, it is authoritative.
  if (site !== null && site !== 'same-origin') return false;

  // A real Origin must still match; this is what rejects a foreign origin outright.
  if (origin !== null && origin !== 'null') {
    if (expectedOrigin !== null) return origin === expectedOrigin;
    try {
      return new URL(origin).hostname === new URL(request.url).hostname;
    } catch {
      return false;
    }
  }

  // Opaque or absent Origin: admit only on the browser's own same-origin assertion.
  return site === 'same-origin';
}

async function submittedCode(request: Request): Promise<string | null> {
  const contentType = request.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase();
  if (contentType !== 'application/x-www-form-urlencoded') return null;
  const declaredLengthHeader = request.headers.get('Content-Length');
  if (declaredLengthHeader !== null) {
    const declaredLength = Number(declaredLengthHeader);
    if (!Number.isInteger(declaredLength) || declaredLength < 0 || declaredLength > MAX_BODY_BYTES) return null;
  }
  const body = await readBoundedBody(request);
  if (body === null) return null;
  const values = new URLSearchParams(body).getAll('code');
  if (values.length !== 1 || values[0].length > 256) return null;
  // Copy-paste of a shared code routinely carries a leading/trailing space or newline.
  // Bound the raw length first, then compare on the trimmed value.
  return values[0].trim();
}

async function readBoundedBody(request: Request): Promise<string | null> {
  if (!request.body) return '';
  const reader = request.body.getReader();
  const bytes = new Uint8Array(MAX_BODY_BYTES);
  let length = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (length + value.byteLength > MAX_BODY_BYTES) {
        await reader.cancel();
        return null;
      }
      bytes.set(value, length);
      length += value.byteLength;
    }
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length));
  } catch {
    try {
      await reader.cancel();
    } catch {
      // The stream may already be errored or closed.
    }
    return null;
  }
}

export async function onRequest(context: PagesContext): Promise<Response> {
  const { request, env } = context;
  const url = new URL(request.url);

  // Defense in depth: middleware applies this policy first, but the route can never
  // handle credentials or set a cookie for a redirect host, a stale alias, a
  // deployment subdomain, or any other unexpected production host.
  if (env.SITE_MODE === 'production') {
    const decision = productionHostDecision(url.hostname, env);
    if (decision === 'redirect') return redirect(canonicalRedirectTarget(request.url), 308);
    if (decision === 'refuse') return operationalFailure();
  }
  if (request.method !== 'POST') {
    return withSecurityHeaders(new Response('Method not allowed', { status: 405, headers: { Allow: 'POST' } }));
  }

  // Preview access is handled exclusively by Cloudflare Access. The landing form
  // remains usable for authorized preview reviewers but sets no application cookie.
  if (env.SITE_MODE === 'preview') return redirect(PROGRAMS_PATH, 303);

  // The interim placeholder auth is served only at the project's pages.dev alias.
  if (env.SITE_MODE === 'placeholder' && url.hostname !== PLACEHOLDER_HOST) {
    return operationalFailure();
  }

  const local = env.SITE_MODE === 'local' && localHostAllowed(url.hostname);
  if (env.SITE_MODE !== 'production' && env.SITE_MODE !== 'placeholder' && !local) return operationalFailure();
  if (!env.ACCESS_CODE || !env.SESSION_SIGNING_KEY || env.SESSION_SIGNING_KEY.length < 32) {
    return operationalFailure();
  }
  // The host is already validated as one that may serve (canonical, or the stable
  // alias while provisioning), so the expected origin is derived from it: the form
  // must be same-origin with the page that rendered it.
  const expectedOrigin = local ? null : `https://${url.hostname}`;
  if (!sameOrigin(request, expectedOrigin)) return invalidAccess();

  let candidate: string | null = null;
  try {
    candidate = await submittedCode(request);
  } catch {
    return invalidAccess();
  }
  // Trim the configured secret too: a value provisioned via `echo code | ... secret put`
  // carries a trailing newline, which would otherwise never match anything.
  if (candidate === null || !await constantTimeSecretEqual(candidate, env.ACCESS_CODE.trim())) return invalidAccess();

  const token = await issueSession(env.SESSION_SIGNING_KEY);
  return redirect(PROGRAMS_PATH, 303, sessionCookie(token));
}
