import {
  LANDING_ASSET,
  PLACEHOLDER_HOST,
  canonicalRedirectTarget,
  expiredSessionCookie,
  isLegacyProgramsPath,
  localHostAllowed,
  operationalFailure,
  programsCompatibilityTarget,
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

const APP_HTML_PATHS = new Set([
  '/programs.html',
  '/targets.html',
  '/pathways.html',
  '/drugs.html',
  '/pksafety.html',
]);

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
    // Cloudflare Access has already authenticated preview requests. Keep the old
    // Programs URL as a permanent compatibility redirect, never a second app copy.
    if (isLegacyProgramsPath(url.pathname)) {
      return redirect(programsCompatibilityTarget(request.url), 308);
    }
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

  // "/" is the only public app surface, and it serves the reviewer landing from its own
  // control asset. index.html is NOT the landing: in the full release it is an admitted,
  // hash-bound meta-refresh stub into /programs.html, so it stays a gated app artifact and is
  // never overwritten. Requesting it directly therefore falls through to the cookie check.
  if (url.pathname === '/' && (request.method === 'GET' || request.method === 'HEAD')) {
    const landing = new Request(new URL(LANDING_ASSET, url), request);
    return withSecurityHeaders(await context.next(landing));
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

  // Resolve the historical route only after the same reviewer gate as every other
  // protected document. This keeps old bookmarks working without making the alias public.
  if (isLegacyProgramsPath(url.pathname)) {
    return redirect(programsCompatibilityTarget(request.url), 308);
  }

  // Cloudflare Pages normally redirects `name.html` assets to extensionless pretty URLs.
  // The application contract intentionally keeps the explicit stage filenames, so fetch the
  // equivalent extensionless asset internally while preserving the reviewer's visible URL.
  if (
    APP_HTML_PATHS.has(url.pathname)
    && (request.method === 'GET' || request.method === 'HEAD')
  ) {
    const assetUrl = new URL(request.url);
    assetUrl.pathname = url.pathname.slice(0, -'.html'.length);
    return withSecurityHeaders(await context.next(new Request(assetUrl, request)));
  }

  return withSecurityHeaders(await context.next());
}
