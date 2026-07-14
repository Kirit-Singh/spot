import { describe, expect, it, vi } from 'vitest';
import { onRequest as auth } from '../../functions/auth';
import { onRequest as middleware } from '../../functions/_middleware';
import {
  CANONICAL_HOST,
  PLACEHOLDER_HOST,
  PROGRAMS_PATH,
  REVIEW_COOKIE,
  issueSession,
  productionHostDecision,
  type Env,
  type PagesContext,
} from '../../functions/lib/reviewerGate';

const ACCESS_CODE = 'unit-test-code';
const SIGNING_KEY = 'unit-test-signing-key-with-more-than-32-characters';

// Canonical-only: the end state once the custom domain certificate is active.
const canonical: Env = { SITE_MODE: 'production', ACCESS_CODE, SESSION_SIGNING_KEY: SIGNING_KEY };
// Transitional: the stable pages.dev alias still serves while the certificate provisions.
const provisioning: Env = { ...canonical, ALLOW_PAGES_DEV_ALIAS: '1' };

// Unique per-deployment and per-branch subdomains must never serve or redirect.
const DEPLOYMENT_SUBDOMAINS = [
  '0aaa3cc7.spotpathways.pages.dev',
  '6500e8a4.spotpathways.pages.dev',
  'release.spotpathways.pages.dev',
];
const FOREIGN_HOSTS = ['evil.com', 'spotpathways.com.evil.com', 'spotpathways.pages.dev.evil.com'];

function ctx(request: Request, env: Env, next = vi.fn(async () => new Response('protected bytes'))): PagesContext {
  return { request, env, next };
}

function post(url: string, origin: string, code = ACCESS_CODE): Request {
  return new Request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: origin },
    body: new URLSearchParams({ code }),
  });
}

describe('production host decision table', () => {
  it('serves the canonical host, redirects the alias, and refuses everything else', () => {
    expect(productionHostDecision(CANONICAL_HOST, canonical)).toBe('serve');
    expect(productionHostDecision('spotpathway.com', canonical)).toBe('redirect');
    expect(productionHostDecision('www.spotpathway.com', canonical)).toBe('redirect');
    expect(productionHostDecision('www.spotpathways.com', canonical)).toBe('redirect');

    // The stable alias serves only while the certificate provisions.
    expect(productionHostDecision(PLACEHOLDER_HOST, provisioning)).toBe('serve');
    expect(productionHostDecision(PLACEHOLDER_HOST, canonical)).toBe('redirect');

    for (const host of [...DEPLOYMENT_SUBDOMAINS, ...FOREIGN_HOSTS]) {
      expect(productionHostDecision(host, provisioning), host).toBe('refuse');
      expect(productionHostDecision(host, canonical), host).toBe('refuse');
    }
  });
});

describe('canonical host gate', () => {
  it('serves the public landing and gates every other asset at spotpathways.com', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/`), canonical, landingNext));
    expect(landing.status).toBe(200);
    expect(landingNext).toHaveBeenCalledOnce();

    const guarded = await middleware(ctx(new Request(`https://${CANONICAL_HOST}${PROGRAMS_PATH}`, {
      headers: { Accept: 'text/html' },
    }), canonical));
    expect(guarded.status).toBe(303);
    expect(guarded.headers.get('Location')).toBe('/');

    const token = await issueSession(SIGNING_KEY);
    const next = vi.fn(async () => new Response('placeholder body'));
    const admitted = await middleware(ctx(new Request(`https://${CANONICAL_HOST}${PROGRAMS_PATH}`, {
      headers: { Cookie: `${REVIEW_COOKIE}=${token}` },
    }), canonical, next));
    expect(admitted.status).toBe(200);
    expect(next).toHaveBeenCalledOnce();
  });

  it('authenticates a same-origin reviewer on the canonical host', async () => {
    const res = await auth(ctx(post(`https://${CANONICAL_HOST}/auth`, `https://${CANONICAL_HOST}`), canonical));
    expect(res.status).toBe(303);
    expect(res.headers.get('Location')).toBe(PROGRAMS_PATH);
    const cookie = res.headers.get('Set-Cookie') ?? '';
    expect(cookie).toContain(`${REVIEW_COOKIE}=`);
    expect(cookie).toContain('Secure');
    expect(cookie).toContain('HttpOnly');
    expect(cookie).not.toMatch(/(?:^|;)\s*Domain=/i);

    const cross = await auth(ctx(post(`https://${CANONICAL_HOST}/auth`, 'https://evil.example'), canonical));
    expect(cross.status).toBe(303);
    expect(cross.headers.get('Location')).toBe('/?access=invalid');
    expect(cross.headers.has('Set-Cookie')).toBe(false);
  });
});

describe('spotpathway.com permanent redirect', () => {
  it('308s to the canonical host before auth, preserving path and query', async () => {
    const next = vi.fn(async () => new Response('must not run'));
    const res = await middleware(ctx(new Request(`https://spotpathway.com${PROGRAMS_PATH}?view=targets&page=2`), canonical, next));
    expect(res.status).toBe(308);
    expect(res.headers.get('Location')).toBe(`https://spotpathways.com${PROGRAMS_PATH}?view=targets&page=2`);
    expect(res.headers.has('Set-Cookie')).toBe(false);
    expect(next).not.toHaveBeenCalled();
  });

  it('strips credential-like query keys and never forwards a cookie', async () => {
    const res = await middleware(ctx(new Request('https://spotpathway.com/auth?view=x&code=must-not-forward&token=t', {
      headers: { Cookie: `${REVIEW_COOKIE}=forged` },
    }), canonical));
    expect(res.status).toBe(308);
    expect(res.headers.get('Location')).toBe('https://spotpathways.com/auth?view=x');
    expect(res.headers.has('Set-Cookie')).toBe(false);
  });

  it('redirects a POST to /auth on the redirect host without issuing a cookie', async () => {
    const res = await auth(ctx(post('https://spotpathway.com/auth', 'https://spotpathway.com'), canonical));
    expect(res.status).toBe(308);
    expect(res.headers.get('Location')).toBe('https://spotpathways.com/auth');
    expect(res.headers.has('Set-Cookie')).toBe(false);
  });

  it('redirects the www forms of both zones', async () => {
    for (const host of ['www.spotpathway.com', 'www.spotpathways.com']) {
      const res = await middleware(ctx(new Request(`https://${host}/x?a=1`), canonical));
      expect(res.status, host).toBe(308);
      expect(res.headers.get('Location'), host).toBe('https://spotpathways.com/x?a=1');
    }
  });
});

describe('pages.dev alias during certificate provisioning', () => {
  it('serves the gated app on the stable alias while ALLOW_PAGES_DEV_ALIAS=1', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/`), provisioning, landingNext));
    expect(landing.status).toBe(200);
    expect(landingNext).toHaveBeenCalledOnce();

    const guarded = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}${PROGRAMS_PATH}`, {
      headers: { Accept: 'text/html' },
    }), provisioning));
    expect(guarded.status).toBe(303);
    expect(guarded.headers.get('Location')).toBe('/');

    // Same-origin auth against the alias origin issues the host-only cookie.
    const authed = await auth(ctx(post(`https://${PLACEHOLDER_HOST}/auth`, `https://${PLACEHOLDER_HOST}`), provisioning));
    expect(authed.status).toBe(303);
    expect(authed.headers.get('Set-Cookie') ?? '').toContain(`${REVIEW_COOKIE}=`);
  });

  it('redirects the alias to the canonical host once the flag is removed', async () => {
    const next = vi.fn(async () => new Response('must not run'));
    const res = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}${PROGRAMS_PATH}?a=1`), canonical, next));
    expect(res.status).toBe(308);
    expect(res.headers.get('Location')).toBe(`https://spotpathways.com${PROGRAMS_PATH}?a=1`);
    expect(res.headers.has('Set-Cookie')).toBe(false);
    expect(next).not.toHaveBeenCalled();

    const authRes = await auth(ctx(post(`https://${PLACEHOLDER_HOST}/auth`, `https://${PLACEHOLDER_HOST}`), canonical));
    expect(authRes.status).toBe(308);
    expect(authRes.headers.has('Set-Cookie')).toBe(false);
  });
});

describe('refused hosts', () => {
  it('refuses unique deployment and branch subdomains in both provisioning and canonical states', async () => {
    for (const env of [provisioning, canonical]) {
      for (const host of DEPLOYMENT_SUBDOMAINS) {
        const next = vi.fn(async () => new Response('must not run'));
        const res = await middleware(ctx(new Request(`https://${host}${PROGRAMS_PATH}`), env, next));
        expect(res.status, host).toBe(503);
        expect(res.headers.has('Set-Cookie'), host).toBe(false);
        expect(next, host).not.toHaveBeenCalled();
      }
    }
  });

  it('refuses every other host and never authenticates there', async () => {
    for (const host of FOREIGN_HOSTS) {
      const res = await middleware(ctx(new Request(`https://${host}/`), canonical));
      expect(res.status, host).toBe(503);

      const authRes = await auth(ctx(post(`https://${host}/auth`, `https://${host}`), canonical));
      expect(authRes.status, host).toBe(503);
      expect(authRes.headers.has('Set-Cookie'), host).toBe(false);
    }
  });

  it('refuses a valid cookie presented on a refused host', async () => {
    const token = await issueSession(SIGNING_KEY);
    const next = vi.fn(async () => new Response('must not run'));
    const res = await middleware(ctx(new Request(`https://release.spotpathways.pages.dev${PROGRAMS_PATH}`, {
      headers: { Cookie: `${REVIEW_COOKIE}=${token}` },
    }), provisioning, next));
    expect(res.status).toBe(503);
    expect(next).not.toHaveBeenCalled();
  });
});
