import {
  PLACEHOLDER_HOST,
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

// A null expectedOrigin means "match the request's own host" (local dev); otherwise
// the Origin header must equal the exact expected origin for the active mode.
function sameOrigin(request: Request, expectedOrigin: string | null): boolean {
  const origin = request.headers.get('Origin');
  if (!origin) return false;
  if (expectedOrigin !== null) return origin === expectedOrigin;
  try {
    return new URL(origin).hostname === new URL(request.url).hostname;
  } catch {
    return false;
  }
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
  return values.length === 1 && values[0].length <= 256 ? values[0] : null;
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
  if (env.SITE_MODE === 'preview') return redirect('/01_page.html', 303);

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
  if (candidate === null || !await constantTimeSecretEqual(candidate, env.ACCESS_CODE)) return invalidAccess();

  const token = await issueSession(env.SESSION_SIGNING_KEY);
  return redirect('/01_page.html', 303, sessionCookie(token));
}
