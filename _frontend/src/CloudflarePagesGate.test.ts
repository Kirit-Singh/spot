import { describe, expect, it, vi } from 'vitest';
import { onRequest as auth } from '../../functions/auth';
import { onRequest as middleware } from '../../functions/_middleware';
import {
  CANONICAL_HOST,
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
  it('redirects the singular host before auth and never sets a cookie there', async () => {
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

    const pagesDev = await middleware(context(new Request('https://release.spotpathways.pages.dev/results/current.json'), production, next));
    expect(pagesDev.status).toBe(308);
    expect(pagesDev.headers.get('Location')).toBe('https://spotpathways.com/results/current.json');
    expect(pagesDev.headers.has('Set-Cookie')).toBe(false);
    expect(next).not.toHaveBeenCalled();
  });

  it('exposes only the landing and POST /auth before session verification', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), production, landingNext));
    expect(landing.status).toBe(200);
    expect(await landing.text()).toBe('landing');
    expect(landing.headers.get('Cache-Control')).toContain('no-store');

    const document = await middleware(context(new Request(`https://${CANONICAL_HOST}/01_page.html`, {
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
    expect(authResponse.headers.get('Location')).toBe('/01_page.html');
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
    const response = await middleware(context(new Request('https://abc123.spotpathways.pages.dev/01_page.html'), preview, next));
    expect(response.status).toBe(200);
    expect(response.headers.has('Set-Cookie')).toBe(false);
    expect(next).toHaveBeenCalledOnce();

    const form = await auth(context(new Request('https://abc123.spotpathways.pages.dev/auth', { method: 'POST' }), preview));
    expect(form.status).toBe(303);
    expect(form.headers.get('Location')).toBe('/01_page.html');
    expect(form.headers.has('Set-Cookie')).toBe(false);

    const unexpectedHost = await middleware(context(new Request('https://preview.example.org/'), preview, next));
    expect(unexpectedHost.status).toBe(503);
  });

  it('sets security headers in Functions rather than relying on _headers', async () => {
    const response = await middleware(context(new Request(`https://${CANONICAL_HOST}/`), production));
    expect(response.headers.get('Content-Security-Policy')).toContain("frame-ancestors 'none'");
    expect(response.headers.get('X-Frame-Options')).toBe('DENY');
    expect(response.headers.get('X-Robots-Tag')).toContain('noindex');
    expect(response.headers.get('Vary')).toContain('Cookie');
  });
});
