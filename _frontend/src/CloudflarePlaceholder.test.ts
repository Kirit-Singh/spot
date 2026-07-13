import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { onRequest as auth } from '../../functions/auth';
import { onRequest as middleware } from '../../functions/_middleware';
import {
  CANONICAL_HOST,
  PLACEHOLDER_HOST,
  PLACEHOLDER_ORIGIN,
  REVIEW_COOKIE,
  SESSION_TTL_SECONDS,
  issueSession,
  verifySession,
  type Env,
  type PagesContext,
} from '../../functions/lib/reviewerGate';

// Vitest runs with cwd = _frontend; the deploy assets live one level up at the repo root.
const REPO = resolve(process.cwd(), '..');
function repoText(rel: string): string {
  return readFileSync(resolve(REPO, rel), 'utf8');
}

// Source of the deliberately-labelled placeholder that a reviewer sees after auth,
// and the routing manifest that guarantees every placeholder asset is gated.
const PLACEHOLDER_PAGE = repoText('deploy/cloudflare/static/placeholder.html');
const ROUTES = repoText('deploy/cloudflare/static/_routes.json');

// Tokens that would only appear if Stage-1/2/3/4 science leaked into the placeholder.
const SCIENTIFIC_TOKENS = [
  'treg', 'glioblastoma', 'glioma', 'umap', 'ensg', 'lincs', 'chembl', 'depmap',
  'foxp3', 'tbx21', 'p-value', 'q-value', 'fdr', 'enrichment', 'penetrance',
  'biomarker', 'clinical', 'gene', 'drug', 'pathway', 'perturbation', 'transcript',
  'dependency', 'log_fc', 'stage01', 'stage02', 'stage03', 'stage04',
];

const ACCESS_CODE = 'unit-test-code';
const SIGNING_KEY = 'unit-test-signing-key-with-more-than-32-characters';
const production: Env = { SITE_MODE: 'production', ACCESS_CODE, SESSION_SIGNING_KEY: SIGNING_KEY };
const placeholderEnv: Env = { SITE_MODE: 'placeholder', ACCESS_CODE, SESSION_SIGNING_KEY: SIGNING_KEY };

function ctx(request: Request, env: Env, next = vi.fn(async () => new Response('protected bytes'))): PagesContext {
  return { request, env, next };
}

function form(url: string, origin: string, code: string): Request {
  return new Request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: origin },
    body: new URLSearchParams({ code }),
  });
}

describe('Cloudflare placeholder page contract', () => {
  it('is deliberately labelled and states the workbench is being assembled', () => {
    expect(PLACEHOLDER_PAGE).toMatch(/being assembled/i);
    expect(PLACEHOLDER_PAGE).toMatch(/placeholder/i);
  });

  it('reuses the frozen Stage-1 visual language and dot mark', () => {
    expect(PLACEHOLDER_PAGE).toContain('#FAF9F7'); // warm background
    expect(PLACEHOLDER_PAGE).toContain('#3E7D8C'); // teal accent
    expect(PLACEHOLDER_PAGE).toContain('#1E1B16'); // ink
    expect(PLACEHOLDER_PAGE).toMatch(/r=['"]4\.6['"]/); // the canonical Stage-1 dot geometry
    expect(PLACEHOLDER_PAGE).toMatch(/name=["']robots["'][^>]*noindex/i);
  });

  it('embeds no reviewer secret and makes no third-party request', () => {
    expect(PLACEHOLDER_PAGE).not.toMatch(/ACCESS_CODE|SESSION_SIGNING_KEY/);
    // No access code or session material is ever written into the page.
    expect(PLACEHOLDER_PAGE).not.toMatch(/(?:code|password|token|session)\s*[:=]\s*["'`][^"'`]/i);
    // No external stylesheet/script/form endpoint. data: URIs (favicon) are allowed.
    expect(PLACEHOLDER_PAGE).not.toMatch(/(?:src|href|action)\s*=\s*["']https?:\/\//i);
  });

  it('carries no scientific claim, result, or Stage-1..4 vocabulary', () => {
    const lowered = PLACEHOLDER_PAGE.toLowerCase();
    for (const token of SCIENTIFIC_TOKENS) {
      expect(lowered, `placeholder must not contain "${token}"`).not.toContain(token);
    }
  });
});

describe('Cloudflare placeholder auth routing', () => {
  it('routes every placeholder asset through the gate with no exclusions', () => {
    expect(JSON.parse(ROUTES)).toEqual({ version: 1, include: ['/*'], exclude: [] });
  });

  it('serves the public landing but withholds the placeholder page until authenticated', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/`), production, landingNext));
    expect(landing.status).toBe(200);
    expect(landingNext).toHaveBeenCalledOnce();

    const guarded = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/01_page.html`, {
      headers: { Accept: 'text/html' },
    }), production));
    expect(guarded.status).toBe(303);
    expect(guarded.headers.get('Location')).toBe('/');

    const manifest = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/site_release_manifest.json`), production));
    expect(manifest.status).toBe(401);
  });

  it('admits the placeholder page only with a valid reviewer cookie', async () => {
    const token = await issueSession(SIGNING_KEY);
    const next = vi.fn(async () => new Response('placeholder body'));
    const admitted = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/01_page.html`, {
      headers: { Accept: 'text/html', Cookie: `${REVIEW_COOKIE}=${token}` },
    }), production, next));
    expect(admitted.status).toBe(200);
    expect(await admitted.text()).toBe('placeholder body');
    expect(admitted.headers.get('Cache-Control')).toContain('no-store');
  });
});

describe('Cloudflare placeholder SITE_MODE gate', () => {
  it('exposes the interim pages.dev host and origin constants', () => {
    expect(PLACEHOLDER_HOST).toBe('spotpathways.pages.dev');
    expect(PLACEHOLDER_ORIGIN).toBe('https://spotpathways.pages.dev');
  });

  it('serves the public landing but gates every non-landing asset at spotpathways.pages.dev', async () => {
    const landingNext = vi.fn(async () => new Response('landing'));
    const landing = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/`), placeholderEnv, landingNext));
    expect(landing.status).toBe(200);
    expect(landingNext).toHaveBeenCalledOnce();

    const page = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/01_page.html`, {
      headers: { Accept: 'text/html' },
    }), placeholderEnv));
    expect(page.status).toBe(303);
    expect(page.headers.get('Location')).toBe('/');

    for (const path of ['/01_page', '/site_release_manifest.json', '/404.html', '/data/stage01_current.json']) {
      const res = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}${path}`), placeholderEnv));
      expect([303, 401], path).toContain(res.status);
      expect(res.headers.has('Set-Cookie'), path).toBe(false);
    }
  });

  it('refuses any host other than exactly spotpathways.pages.dev', async () => {
    for (const host of ['evil.pages.dev', 'abc.spotpathways.pages.dev', 'spotpathways.com', 'spotpathways.pages.dev.evil.com']) {
      const res = await middleware(ctx(new Request(`https://${host}/01_page.html`), placeholderEnv));
      expect(res.status, host).toBe(503);
      expect(res.headers.has('Set-Cookie'), host).toBe(false);
    }
  });

  it('authenticates a same-origin reviewer with a short-lived host-only Secure cookie', async () => {
    const authed = await auth(ctx(form(`https://${PLACEHOLDER_HOST}/auth`, PLACEHOLDER_ORIGIN, ACCESS_CODE), placeholderEnv));
    expect(authed.status).toBe(303);
    expect(authed.headers.get('Location')).toBe('/01_page.html');
    const cookie = authed.headers.get('Set-Cookie') ?? '';
    expect(cookie).toContain(`${REVIEW_COOKIE}=`);
    expect(cookie).toContain('Secure');
    expect(cookie).toContain('HttpOnly');
    expect(cookie).toContain('SameSite=Lax');
    expect(cookie).toContain(`Max-Age=${SESSION_TTL_SECONDS}`);
    expect(cookie).not.toMatch(/(?:^|;)\s*Domain=/i);

    // The issued cookie admits protected placeholder bytes on the same host.
    const pair = cookie.split(';', 1)[0];
    const next = vi.fn(async () => new Response('placeholder body'));
    const admitted = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/01_page`, {
      headers: { Cookie: pair },
    }), placeholderEnv, next));
    expect(admitted.status).toBe(200);
    expect(next).toHaveBeenCalledOnce();
  });

  it('rejects a cross-origin auth submission without issuing a cookie', async () => {
    const res = await auth(ctx(form(`https://${PLACEHOLDER_HOST}/auth`, 'https://evil.example', ACCESS_CODE), placeholderEnv));
    expect(res.status).toBe(303);
    expect(res.headers.get('Location')).toBe('/?access=invalid');
    expect(res.headers.has('Set-Cookie')).toBe(false);
  });

  it('refuses auth on a non-placeholder host and fails closed when secrets are absent', async () => {
    const wrongHost = await auth(ctx(form('https://evil.pages.dev/auth', 'https://evil.pages.dev', ACCESS_CODE), placeholderEnv));
    expect(wrongHost.status).toBe(503);
    expect(wrongHost.headers.has('Set-Cookie')).toBe(false);

    const noSecret = await auth(ctx(form(`https://${PLACEHOLDER_HOST}/auth`, PLACEHOLDER_ORIGIN, ACCESS_CODE), { SITE_MODE: 'placeholder' }));
    expect(noSecret.status).toBe(503);
  });

  it('refuses a missing or unknown SITE_MODE', async () => {
    const missing = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/`), { ACCESS_CODE, SESSION_SIGNING_KEY: SIGNING_KEY }));
    expect(missing.status).toBe(503);

    const unknownEnv = { SITE_MODE: 'staging', ACCESS_CODE, SESSION_SIGNING_KEY: SIGNING_KEY } as unknown as Env;
    const unknown = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/`), unknownEnv));
    expect(unknown.status).toBe(503);
  });

  it('fails closed on a tampered or expired cookie', async () => {
    const good = await issueSession(SIGNING_KEY);
    const tamperedToken = `${good.slice(0, -1)}${good.endsWith('a') ? 'b' : 'a'}`;
    const tampered = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/01_page.html`, {
      headers: { Accept: 'text/html', Cookie: `${REVIEW_COOKIE}=${tamperedToken}` },
    }), placeholderEnv));
    expect(tampered.status).toBe(303);
    expect(tampered.headers.get('Location')).toBe('/');

    const expiredToken = await issueSession(SIGNING_KEY, 1000);
    const expired = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/site_release_manifest.json`, {
      headers: { Cookie: `${REVIEW_COOKIE}=${expiredToken}` },
    }), placeholderEnv));
    expect(expired.status).toBe(401);
  });

  it('supports the placeholder->production switch with the same cookie mechanism', async () => {
    // A session minted during the placeholder phase verifies under the same signing key,
    const token = await issueSession(SIGNING_KEY);
    expect(await verifySession(token, SIGNING_KEY)).toBe(true);

    // and is admitted after switching to production on the canonical host,
    const prodNext = vi.fn(async () => new Response('admitted'));
    const admitted = await middleware(ctx(new Request(`https://${CANONICAL_HOST}/01_page`, {
      headers: { Cookie: `${REVIEW_COOKIE}=${token}` },
    }), production, prodNext));
    expect(admitted.status).toBe(200);
    expect(prodNext).toHaveBeenCalledOnce();

    // while production still enforces the canonical host, redirecting the interim pages.dev host.
    const redirected = await middleware(ctx(new Request(`https://${PLACEHOLDER_HOST}/01_page`), production));
    expect(redirected.status).toBe(308);
    expect(redirected.headers.get('Location')).toBe(`https://${CANONICAL_HOST}/01_page`);
    expect(redirected.headers.has('Set-Cookie')).toBe(false);
  });
});
