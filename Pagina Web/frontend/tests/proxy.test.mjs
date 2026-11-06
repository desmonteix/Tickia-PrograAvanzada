import test from 'node:test';
import assert from 'node:assert/strict';
import { proxy } from '../api/index.mjs';
const secret = 'isolated-proxy-fixture-' + 'a'.repeat(32);
process.env.PROXY_SHARED_SECRET = secret;

test('only platform-verified IP is forwarded with the private gateway credential', async () => {
  const response = await proxy(
    new Request('https://tickia.example/api/auth/me', {
      headers: {
        'X-Forwarded-For': '203.0.113.7',
        'X-Tickia-Client-IP': 'attacker',
        'X-Tickia-Proxy-Secret': 'attacker',
      },
    }),
    {
      origin: 'https://backend.example',
      trustedPlatform: true,
      fetchImpl: async (url, init) => {
        assert.equal(init.headers.get('X-Tickia-Client-IP'), '203.0.113.7');
        assert.equal(init.headers.get('X-Tickia-Proxy-Secret'), secret);
        return Response.json({});
      },
    },
  );
  assert.equal(response.status, 200);
  const rejected = await proxy(
    new Request('https://tickia.example/api/auth/me', {
      headers: { 'X-Forwarded-For': '203.0.113.7, 203.0.113.8' },
    }),
    { origin: 'https://backend.example', trustedPlatform: true },
  );
  assert.equal(rejected.status, 503);
});

test('rewritten API paths are explicit and cannot escape the API origin', async () => {
  const response = await proxy(new Request('https://tickia.example/api?__tickia_path=auth/me'), {
    origin: 'https://backend.example',
    fetchImpl: async (url) => {
      assert.equal(url.href, 'https://backend.example/api/auth/me');
      return Response.json({});
    },
  });
  assert.equal(response.status, 200);
  const invalid = await proxy(new Request('https://tickia.example/api?__tickia_path=../other'), {
    origin: 'https://backend.example',
  });
  assert.equal(invalid.status, 404);
});

test('missing or invalid backend fails closed', async () => {
  for (const origin of [
    undefined,
    '',
    'http://backend.example',
    'https://backend.example/api',
    'https://user:secret@backend.example',
  ]) {
    const response = await proxy(new Request('https://tickia.example/api/tickets'), {
      origin: origin || '',
    });
    assert.equal(response.status, 503);
  }
});

test('login cookies and raw form bodies survive the same-origin gateway', async () => {
  const body = 'username=fan%40example.com&password=fixture';
  const response = await proxy(
    new Request('https://tickia.example/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Origin: 'https://tickia.example',
      },
      body,
    }),
    {
      origin: 'https://backend.example',
      fetchImpl: async (url, init) => {
        assert.equal(url.href, 'https://backend.example/api/auth/login');
        assert.equal(new TextDecoder().decode(init.body), body);
        assert.equal(init.headers.get('origin'), 'https://tickia.example');
        return new Response('{}', {
          headers: {
            'Set-Cookie': 'fixture=sample; HttpOnly; Secure; SameSite=Lax',
            'Content-Type': 'application/json',
          },
        });
      },
    },
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get('set-cookie'), /HttpOnly; Secure/);
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('authenticated binary downloads keep bytes and content type', async () => {
  const bytes = new Uint8Array([137, 80, 78, 71, 0, 1]);
  const response = await proxy(
    new Request('https://tickia.example/api/download/test?x=1', {
      headers: { Cookie: 'fixture=sample' },
    }),
    {
      origin: 'https://backend.example',
      fetchImpl: async (url, init) => {
        assert.equal(url.origin, 'https://backend.example');
        assert.equal(url.search, '?x=1');
        assert.equal(init.headers.get('cookie'), 'fixture=sample');
        return new Response(bytes, { headers: { 'Content-Type': 'image/png' } });
      },
    },
  );
  assert.equal(response.headers.get('content-type'), 'image/png');
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes);
});

test('network failures and redirects do not leak internals or cookies', async () => {
  for (const fetchImpl of [
    async () => {
      throw new Error('internal hostname');
    },
    async () =>
      new Response(null, { status: 302, headers: { Location: 'https://unrelated.example' } }),
  ]) {
    const response = await proxy(new Request('https://tickia.example/api/tickets'), {
      origin: 'https://backend.example',
      fetchImpl,
    });
    assert.equal(response.status, 502);
    assert.doesNotMatch(await response.text(), /internal hostname|unrelated/);
  }
});
