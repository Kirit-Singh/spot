import {
  PLACEHOLDER_HOST,
  canonicalRedirectTarget,
  expiredSessionCookie,
  localHostAllowed,
  operationalFailure,
  productionHostDecision,
  readCookie,
  redirect,
  verifySession,
  withSecurityHeaders,
  type PagesContext,
} from './lib/reviewerGate';

function isDocumentRequest(request: Request, pathname: string): boolean {
  return request.headers.get('Sec-Fetch-Dest') === 'document'
    || request.headers.get('Accept')?.includes('text/html') === true
    || pathname.endsWith('.html');
}

export async function onRequest(context: PagesContext): Promise<Response> {
  const { request, env } = context;
  const url = new URL(request.url);

  // Host policy is deliberately first. No redirect host, stale alias, deployment
  // subdomain, or unexpected host can reach auth or receive the reviewer cookie.
  if (env.SITE_MODE === 'production') {
    const decision = productionHostDecision(url.hostname, env);
    if (decision === 'redirect') return redirect(canonicalRedirectTarget(request.url), 308);
    if (decision === 'refuse') return operationalFailure();
  }

  // Preview deployments are protected by a Cloudflare Access policy upstream.
  // They never issue or accept this application's shared-reviewer cookie.
  if (env.SITE_MODE === 'preview') {
    if (!url.hostname.endsWith('.pages.dev')) return operationalFailure();
    return withSecurityHeaders(await context.next());
  }

  // The interim placeholder is the production deployment served only at the
  // project's pages.dev alias; any other host is refused, never redirected.
  if (env.SITE_MODE === 'placeholder' && url.hostname !== PLACEHOLDER_HOST) {
    return operationalFailure();
  }

  // Only production (canonical host), placeholder (pages.dev alias, host already
  // checked), and local-on-localhost reach the shared reviewer-cookie gate.
  const gated = env.SITE_MODE === 'production'
    || env.SITE_MODE === 'placeholder'
    || (env.SITE_MODE === 'local' && localHostAllowed(url.hostname));
  if (!gated) return operationalFailure();

  if (url.pathname === '/index.html' && (request.method === 'GET' || request.method === 'HEAD')) {
    return redirect('/', 308);
  }
  if (url.pathname === '/' && (request.method === 'GET' || request.method === 'HEAD')) {
    return withSecurityHeaders(await context.next());
  }
  if (url.pathname === '/auth') {
    if (request.method !== 'POST') {
      return withSecurityHeaders(new Response('Method not allowed', { status: 405, headers: { Allow: 'POST' } }));
    }
    return withSecurityHeaders(await context.next());
  }

  const token = readCookie(request);
  if (!await verifySession(token, env.SESSION_SIGNING_KEY)) {
    const clear = token ? expiredSessionCookie() : undefined;
    if (isDocumentRequest(request, url.pathname)) return redirect('/', 303, clear);
    const response = withSecurityHeaders(new Response('Unauthorized', { status: 401 }));
    if (clear) response.headers.set('Set-Cookie', clear);
    return response;
  }

  return withSecurityHeaders(await context.next());
}
