export const CANONICAL_HOST = 'spotpathways.com';
export const CANONICAL_ORIGIN = `https://${CANONICAL_HOST}`;
// The project's STABLE production alias. It is the only pages.dev host that may ever
// serve: unique per-deployment and per-branch subdomains are always refused. It serves
// only while the canonical certificate provisions, then redirects to the canonical host.
export const PLACEHOLDER_HOST = 'spotpathways.pages.dev';
export const PLACEHOLDER_ORIGIN = `https://${PLACEHOLDER_HOST}`;
// Hosts that permanently redirect to the canonical host, before auth or cookie parsing.
export const REDIRECT_HOSTS: ReadonlySet<string> = new Set([
  'spotpathway.com',
  'www.spotpathway.com',
  'www.spotpathways.com',
]);
export const REVIEW_COOKIE = '__Host-spot-review';
export const SESSION_TTL_SECONDS = 4 * 60 * 60;

export interface Env {
  ACCESS_CODE?: string;
  SESSION_SIGNING_KEY?: string;
  SITE_MODE?: 'production' | 'placeholder' | 'preview' | 'local';
  // '1' ONLY while the canonical certificate provisions: the stable pages.dev alias
  // serves the gated app. Any other value (the default) redirects it to canonical.
  ALLOW_PAGES_DEV_ALIAS?: string;
}

export type HostDecision = 'serve' | 'redirect' | 'refuse';

// The exact production host policy. Default is 'refuse': an unknown host never serves
// and is never redirected, so deployment subdomains cannot expose the app or leak a
// reviewer cookie.
export function productionHostDecision(hostname: string, env: Env): HostDecision {
  if (hostname === CANONICAL_HOST) return 'serve';
  if (REDIRECT_HOSTS.has(hostname)) return 'redirect';
  if (hostname === PLACEHOLDER_HOST) {
    return env.ALLOW_PAGES_DEV_ALIAS === '1' ? 'serve' : 'redirect';
  }
  return 'refuse';
}

export interface PagesContext {
  request: Request;
  env: Env;
  // Pages lets a Function forward a REWRITTEN request to the static asset layer. The root
  // route uses this to serve the reviewer landing from its own control surface, so the
  // manifest-bound app index.html is never overwritten to make room for it.
  next(input?: Request | string, init?: RequestInit): Promise<Response>;
}

// The reviewer landing is served at "/" from this control surface. It is deliberately NOT
// index.html: in the full release index.html is an admitted, hash-bound meta-refresh stub to
// /01_page.html, and overwriting it would both destroy an admitted byte and serve an app
// entry point publicly.
//
// EXTENSIONLESS on purpose. Pages canonicalises ".html" URLs, so forwarding to
// "/landing.html" makes the asset layer answer 308 -> "/landing" and the root route stops
// serving anything. The file on disk is landing.html; the path it is fetched at is /landing.
export const LANDING_ASSET = '/landing';

const encoder = new TextEncoder();
const sensitiveQueryKey = /^(?:access_?code|auth|code|password|session|token)$/i;

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> | null {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) return null;
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4);
  try {
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  } catch {
    return null;
  }
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify'],
  );
}

function sessionMessage(expires: number, nonce: string): string {
  return `v1\n${CANONICAL_HOST}\n${expires}\n${nonce}`;
}

export async function issueSession(signingKey: string, nowSeconds = Math.floor(Date.now() / 1000)): Promise<string> {
  const expires = nowSeconds + SESSION_TTL_SECONDS;
  const nonceBytes = new Uint8Array(16);
  crypto.getRandomValues(nonceBytes);
  const nonce = bytesToBase64Url(nonceBytes);
  const message = sessionMessage(expires, nonce);
  const signature = new Uint8Array(await crypto.subtle.sign('HMAC', await hmacKey(signingKey), encoder.encode(message)));
  return `v1.${expires}.${nonce}.${bytesToBase64Url(signature)}`;
}

export async function verifySession(
  token: string | null,
  signingKey: string | undefined,
  nowSeconds = Math.floor(Date.now() / 1000),
): Promise<boolean> {
  if (!token || !signingKey || signingKey.length < 32 || token.length > 512) return false;
  const parts = token.split('.');
  if (parts.length !== 4 || parts[0] !== 'v1') return false;
  const expires = Number(parts[1]);
  if (!Number.isSafeInteger(expires) || expires <= nowSeconds || expires > nowSeconds + SESSION_TTL_SECONDS) return false;
  if (!/^[A-Za-z0-9_-]{22}$/.test(parts[2])) return false;
  const signature = base64UrlToBytes(parts[3]);
  if (!signature || signature.length !== 32) return false;
  return crypto.subtle.verify(
    'HMAC',
    await hmacKey(signingKey),
    signature,
    encoder.encode(sessionMessage(expires, parts[2])),
  );
}

export async function constantTimeSecretEqual(candidate: string, expected: string): Promise<boolean> {
  const [left, right] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(candidate)),
    crypto.subtle.digest('SHA-256', encoder.encode(expected)),
  ]);
  const a = new Uint8Array(left);
  const b = new Uint8Array(right);
  let different = a.length ^ b.length;
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    different |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return different === 0;
}

export function readCookie(request: Request, name = REVIEW_COOKIE): string | null {
  const header = request.headers.get('Cookie');
  if (!header) return null;
  for (const part of header.split(';')) {
    const separator = part.indexOf('=');
    if (separator < 0 || part.slice(0, separator).trim() !== name) continue;
    return part.slice(separator + 1).trim();
  }
  return null;
}

export function sessionCookie(token: string): string {
  return `${REVIEW_COOKIE}=${token}; Path=/; Max-Age=${SESSION_TTL_SECONDS}; HttpOnly; Secure; SameSite=Lax`;
}

export function expiredSessionCookie(): string {
  return `${REVIEW_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;
}

export function canonicalRedirectTarget(requestUrl: string): string {
  const incoming = new URL(requestUrl);
  const target = new URL(CANONICAL_ORIGIN);
  target.pathname = incoming.pathname;
  target.search = incoming.search;
  for (const key of [...target.searchParams.keys()]) {
    if (sensitiveQueryKey.test(key)) target.searchParams.delete(key);
  }
  return target.toString();
}

export function redirect(location: string, status: 303 | 308, cookie?: string): Response {
  const headers = new Headers({ Location: location });
  if (cookie) headers.set('Set-Cookie', cookie);
  return withSecurityHeaders(new Response(null, { status, headers }));
}

export function withSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set('Cache-Control', 'private, no-store, max-age=0');
  headers.set('Pragma', 'no-cache');
  headers.set('Expires', '0');
  headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive');
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('X-Frame-Options', 'DENY');
  headers.set('Referrer-Policy', 'no-referrer');
  headers.set('Permissions-Policy', 'camera=(), geolocation=(), microphone=(), payment=(), usb=()');
  headers.set('Cross-Origin-Opener-Policy', 'same-origin');
  headers.set('Cross-Origin-Resource-Policy', 'same-origin');
  headers.set('Strict-Transport-Security', 'max-age=31536000');
  headers.set(
    'Content-Security-Policy',
    "default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self' https://fonts.gstatic.com; form-action 'self'; frame-ancestors 'none'; img-src 'self' data: blob:; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  );
  const vary = headers.get('Vary');
  if (!vary) headers.set('Vary', 'Cookie');
  else if (!vary.toLowerCase().split(',').map((entry) => entry.trim()).includes('cookie')) headers.set('Vary', `${vary}, Cookie`);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function operationalFailure(): Response {
  return withSecurityHeaders(new Response('Service unavailable', { status: 503 }));
}

export function localHostAllowed(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}
