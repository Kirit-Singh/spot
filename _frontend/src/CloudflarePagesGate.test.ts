import { describe, expect, it, vi } from 'vitest';
import { onRequest as auth } from '../../functions/auth';
import { onRequest as middleware } from '../../functions/_middleware';
import {
  CANONICAL_HOST,
  LEGACY_PROGRAMS_PATH,
  PROGRAMS_PATH,
  REVIEW_COOKIE,
  SESSION_TTL_SECONDS,
  issueSession,
  verifySession,
  type Env,
  type PagesContext,
} from '../../functions/lib/reviewerGate';

const SIGNING_KEY = 'unit-test-signing-key-with-more-than-32-characters';
const ACCESS_CODE = 'unit-test-code';
const production: Env = {
  SITE_MODE: 'production',
  ACCESS_CODE,
  SESSION_SIGNING_KEY: SIGNING_KEY,
};

function context(request: Request, env: Env, next = vi.fn(async () => new Response('protected bytes'))): PagesContext {
  return { request, env, next };
}

function postAuth(code: string, url = `https://${CANONICAL_HOST}/auth`): Request {
  return new Request(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: `https://${CANONICAL_HOST}`,
    },
    body: new URLSearchParams({ code }),
  });
}

describe('Cloudflare Pages canonical and reviewer gate', () => {
  it('redirects the singular host before auth and refuses deployment subdomains', async () => {
    const next = vi.fn(async () => new Response('must not run'));
    const request = new Request('https://spotpathway.com/auth?view=targets&code=must-not-forward', {
      method: 'POST',
      headers: { Cookie: `${REVIEW_COOKIE}=forged` },
      body: 'code=ignored',
    });
    const response = await middleware(context(request, production, next));
    expect(response.status).toBe(308);
    expect(response.headers.get('Location')).toBe('https://spotpathways.com/auth?view=targets');
    expect(response.headers.has('Set-Cookie')).toBe(false);
    expect(next).not.toHaveBeenCalled();

    // A per-branch/per-deployment subdomain is refused outright, never redirected:
    // it must not serve the app or hand back a reviewer cookie. See CloudflareHostPolicy.
    const pagesDev = await middleware(context(new Request('https://release.spotpathways.pages.dev/results/current.json'), production, next));
    expect(pagesDev.status).toBe(503);
    expect(pagesDev.headers.has('Set-Cookie')).toBe(false);
    expect(next).not.toHaveBeenCalled();
  });

  it('exposes only the landing and POST /auth before session verification', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), production, landingNext));
    expect(landing.status).toBe(200);
    expect(await landing.text()).toBe('landing');
    expect(landing.headers.get('Cache-Control')).toContain('no-store');

    const document = await middleware(context(new Request(`https://${CANONICAL_HOST}${PROGRAMS_PATH}`, {
      headers: { Accept: 'text/html' },
    }), production));
    expect(document.status).toBe(303);
    expect(document.headers.get('Location')).toBe('/');

    for (const path of ['/data/stage01_current.json', '/assets/app.js', '/results/current.json', '/site_release_manifest.json']) {
      const response = await middleware(context(new Request(`https://${CANONICAL_HOST}${path}`), production));
      expect(response.status, path).toBe(401);
      expect(await response.text(), path).toBe('Unauthorized');
    }
  });

  it('issues a short-lived host-only signed cookie and admits protected bytes', async () => {
    const authResponse = await auth(context(postAuth(ACCESS_CODE), production));
    expect(authResponse.status).toBe(303);
    expect(authResponse.headers.get('Location')).toBe(PROGRAMS_PATH);
    const setCookie = authResponse.headers.get('Set-Cookie') ?? '';
    expect(setCookie).toContain(`${REVIEW_COOKIE}=`);
    expect(setCookie).toContain(`Max-Age=${SESSION_TTL_SECONDS}`);
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');
    expect(setCookie).toContain('SameSite=Lax');
    expect(setCookie).not.toMatch(/(?:^|;)\s*Domain=/i);

    const cookiePair = setCookie.split(';', 1)[0];
    const next = vi.fn(async () => new Response('admitted'));
    const admitted = await middleware(context(new Request(`https://${CANONICAL_HOST}/data/stage01_current.json`, {
      headers: { Cookie: cookiePair },
    }), production, next));
    expect(admitted.status).toBe(200);
    expect(await admitted.text()).toBe('admitted');
    expect(next).toHaveBeenCalledOnce();
    expect(admitted.headers.get('Cache-Control')).toContain('no-store');
  });

  it('returns one generic invalid state for wrong, missing, duplicate, malformed, and oversized submissions', async () => {
    const wrong = await auth(context(postAuth('wrong'), production));
    const missing = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: `https://${CANONICAL_HOST}` },
      body: 'other=value',
    }), production));
    const duplicate = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: `https://${CANONICAL_HOST}` },
      body: 'code=a&code=b',
    }), production));
    const crossOrigin = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: 'https://example.org' },
      body: `code=${ACCESS_CODE}`,
    }), production));
    const wrongType = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain', Origin: `https://${CANONICAL_HOST}` },
      body: `code=${ACCESS_CODE}`,
    }), production));
    const oversized = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: `https://${CANONICAL_HOST}` },
      body: `code=${'x'.repeat(600)}`,
    }), production));
    const malformed = await auth(context(new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: `https://${CANONICAL_HOST}` },
      body: new Uint8Array([0xff]),
    }), production));
    for (const response of [wrong, missing, duplicate, crossOrigin, wrongType, oversized, malformed]) {
      expect(response.status).toBe(303);
      expect(response.headers.get('Location')).toBe('/?access=invalid');
      expect(response.headers.has('Set-Cookie')).toBe(false);
      expect(await response.text()).toBe('');
    }
  });

  it('fails closed when secrets or runtime mode are missing', async () => {
    const noSecret = await auth(context(postAuth(ACCESS_CODE), { SITE_MODE: 'production' }));
    expect(noSecret.status).toBe(503);
    const noMode = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), {}));
    expect(noMode.status).toBe(503);
  });

  it('rejects tampered and expired sessions', async () => {
    const token = await issueSession(SIGNING_KEY, 1_000);
    expect(await verifySession(token, SIGNING_KEY, 1_001)).toBe(true);
    expect(await verifySession(`${token.slice(0, -1)}x`, SIGNING_KEY, 1_001)).toBe(false);
    expect(await verifySession(token, SIGNING_KEY, 1_000 + SESSION_TTL_SECONDS)).toBe(false);
    expect(await verifySession(token, `${SIGNING_KEY}-rotated`, 1_001)).toBe(false);
  });

  it('uses Access-only previews without issuing an application cookie', async () => {
    const preview: Env = { SITE_MODE: 'preview' };
    const next = vi.fn(async () => new Response('Access already admitted'));
    const response = await middleware(context(new Request(`https://abc123.spotpathways.pages.dev${PROGRAMS_PATH}`), preview, next));
    expect(response.status).toBe(200);
    expect(response.headers.has('Set-Cookie')).toBe(false);
    expect(next).toHaveBeenCalledOnce();

    const form = await auth(context(new Request('https://abc123.spotpathways.pages.dev/auth', { method: 'POST' }), preview));
    expect(form.status).toBe(303);
    expect(form.headers.get('Location')).toBe(PROGRAMS_PATH);
    expect(form.headers.has('Set-Cookie')).toBe(false);

    const unexpectedHost = await middleware(context(new Request('https://preview.example.org/'), preview, next));
    expect(unexpectedHost.status).toBe(503);
  });

  // A same-origin form POST from a page served with Referrer-Policy: no-referrer is a
  // NAVIGATION, and Chrome sends `Origin: null` (opaque) with no Referer. Only
  // Sec-Fetch-Site carries the same-origin assertion, and a page cannot forge it.
  function browserFormPost(code: string, site: string | null = 'same-origin', origin = 'null'): Request {
    const headers: Record<string, string> = {
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: origin,
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Dest': 'document',
    };
    if (site !== null) headers['Sec-Fetch-Site'] = site;
    return new Request(`https://${CANONICAL_HOST}/auth`, {
      method: 'POST',
      headers,
      body: new URLSearchParams({ code }),
    });
  }

  it('admits a real browser form POST that carries an opaque Origin: null', async () => {
    const response = await auth(context(browserFormPost(ACCESS_CODE), production));
    expect(response.status).toBe(303);
    expect(response.headers.get('Location')).toBe(PROGRAMS_PATH);
    expect(response.headers.get('Set-Cookie') ?? '').toContain(`${REVIEW_COOKIE}=`);
  });

  it('refuses an opaque Origin when the browser does not assert same-origin', async () => {
    for (const site of ['cross-site', 'same-site', 'none', null]) {
      const response = await auth(context(browserFormPost(ACCESS_CODE, site), production));
      expect(response.status, String(site)).toBe(303);
      expect(response.headers.get('Location'), String(site)).toBe('/?access=invalid');
      expect(response.headers.has('Set-Cookie'), String(site)).toBe(false);
    }
  });

  it('still refuses a real but foreign Origin even if Sec-Fetch-Site claims same-origin', async () => {
    const response = await auth(context(browserFormPost(ACCESS_CODE, 'same-origin', 'https://evil.example'), production));
    expect(response.status).toBe(303);
    expect(response.headers.get('Location')).toBe('/?access=invalid');
    expect(response.headers.has('Set-Cookie')).toBe(false);
  });

  it('accepts a pasted code carrying surrounding whitespace', async () => {
    for (const submitted of [` ${ACCESS_CODE}`, `${ACCESS_CODE} `, `  ${ACCESS_CODE}  `, `\t${ACCESS_CODE}\r\n`]) {
      const response = await auth(context(postAuth(submitted), production));
      expect(response.status, JSON.stringify(submitted)).toBe(303);
      expect(response.headers.get('Location'), JSON.stringify(submitted)).toBe(PROGRAMS_PATH);
      expect(response.headers.get('Set-Cookie') ?? '', JSON.stringify(submitted)).toContain(`${REVIEW_COOKIE}=`);
    }
  });

  it('tolerates a configured secret stored with a trailing newline', async () => {
    const padded: Env = { SITE_MODE: 'production', ACCESS_CODE: `${ACCESS_CODE}\n`, SESSION_SIGNING_KEY: SIGNING_KEY };
    const response = await auth(context(postAuth(ACCESS_CODE), padded));
    expect(response.status).toBe(303);
    expect(response.headers.get('Location')).toBe(PROGRAMS_PATH);
  });

  it('still rejects a wrong, internally-altered, or blank code after trimming', async () => {
    for (const bad of ['wrong', ACCESS_CODE.replace('-', ' '), '   ', '']) {
      const response = await auth(context(postAuth(bad), production));
      expect(response.status, JSON.stringify(bad)).toBe(303);
      expect(response.headers.get('Location'), JSON.stringify(bad)).toBe('/?access=invalid');
      expect(response.headers.has('Set-Cookie'), JSON.stringify(bad)).toBe(false);
    }
  });

  it('serves "/" from the landing control surface, not from the admitted index.html', async () => {
    // In the full release index.html is an admitted, hash-bound meta-refresh stub into
    // /programs.html. Serving the landing by overwriting it would destroy an admitted byte AND
    // publish an app entry point, so the root route forwards to its own control asset instead.
    const next = vi.fn(async (input?: Request | string) => new Response(
      input instanceof Request ? new URL(input.url).pathname : 'no-rewrite',
    ));
    const landing = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), production, next));
    expect(landing.status).toBe(200);
    expect(await landing.text()).toBe('/landing');
  });

  it('gates the admitted index.html instead of redirecting it away', async () => {
    const blocked = await middleware(context(new Request(`https://${CANONICAL_HOST}/index.html`, {
      headers: { Accept: 'text/html' },
    }), production));
    expect(blocked.status).toBe(303);
    expect(blocked.headers.get('Location')).toBe('/');

    const token = await issueSession(SIGNING_KEY);
    const next = vi.fn(async () => new Response('admitted index stub'));
    const admitted = await middleware(context(new Request(`https://${CANONICAL_HOST}/index.html`, {
      headers: { Accept: 'text/html', Cookie: `${REVIEW_COOKIE}=${token}` },
    }), production, next));
    expect(admitted.status).toBe(200);
    expect(await admitted.text()).toBe('admitted index stub');
  });

  it('permanently redirects the legacy Programs URL only after reviewer authentication', async () => {
    const unauthenticated = await middleware(context(new Request(`https://${CANONICAL_HOST}${LEGACY_PROGRAMS_PATH}`, {
      headers: { Accept: 'text/html' },
    }), production));
    expect(unauthenticated.status).toBe(303);
    expect(unauthenticated.headers.get('Location')).toBe('/');

    const token = await issueSession(SIGNING_KEY);
    for (const legacyPath of [LEGACY_PROGRAMS_PATH, '/01_page']) {
      const next = vi.fn(async () => new Response('legacy bytes must not be served'));
      const admitted = await middleware(context(new Request(
        `https://${CANONICAL_HOST}${legacyPath}?view=targets&code=must-not-forward`,
        { headers: { Accept: 'text/html', Cookie: `${REVIEW_COOKIE}=${token}` } },
      ), production, next));
      expect(admitted.status, legacyPath).toBe(308);
      expect(admitted.headers.get('Location'), legacyPath).toBe(`${PROGRAMS_PATH}?view=targets`);
      expect(admitted.headers.has('Set-Cookie'), legacyPath).toBe(false);
      expect(next, legacyPath).not.toHaveBeenCalled();
    }
  });

  it('serves canonical stage .html URLs without the Pages pretty-URL redirect', async () => {
    const token = await issueSession(SIGNING_KEY);
    for (const pathname of ['/programs.html', '/targets.html', '/pathways.html', '/drugs.html', '/pksafety.html']) {
      const next = vi.fn(async (input?: Request | string) => new Response(
        input instanceof Request ? new URL(input.url).pathname : 'missing-rewrite',
      ));
      const response = await middleware(context(new Request(`https://${CANONICAL_HOST}${pathname}?from=Rest&to=Stim8hr`, {
        headers: { Accept: 'text/html', Cookie: `${REVIEW_COOKIE}=${token}` },
      }), production, next));
      expect(response.status, pathname).toBe(200);
      expect(await response.text(), pathname).toBe(pathname.slice(0, -'.html'.length));
    }
  });

  it('redirects the legacy Programs URL after upstream Access on previews', async () => {
    const preview: Env = { SITE_MODE: 'preview' };
    const next = vi.fn(async () => new Response('legacy bytes must not be served'));
    const response = await middleware(context(new Request(
      `https://abc123.spotpathways.pages.dev${LEGACY_PROGRAMS_PATH}?view=targets`,
    ), preview, next));
    expect(response.status).toBe(308);
    expect(response.headers.get('Location')).toBe(`${PROGRAMS_PATH}?view=targets`);
    expect(next).not.toHaveBeenCalled();
  });

  it('sets security headers in Functions rather than relying on _headers', async () => {
    const response = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), production));
    expect(response.headers.get('Content-Security-Policy')).toContain("frame-ancestors 'none'");
    expect(response.headers.get('X-Frame-Options')).toBe('DENY');
    expect(response.headers.get('X-Robots-Tag')).toContain('noindex');
    expect(response.headers.get('Vary')).toContain('Cookie');
  });
});
