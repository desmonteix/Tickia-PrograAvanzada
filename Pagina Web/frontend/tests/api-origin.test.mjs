import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

async function client(env) {
  const axiosUrl = new URL('../node_modules/axios/index.js', import.meta.url).href;
  const source = (await readFile(new URL('../src/api.ts', import.meta.url), 'utf8'))
    .replace("from 'axios'", `from ${JSON.stringify(axiosUrl)}`)
    .replaceAll('import.meta.env', JSON.stringify(env));
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  }).outputText;
  return (await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`))
    .default;
}

test('production login and session stay on the app origin despite a stale backend URL', async () => {
  const api = await client({ PROD: true, VITE_API_URL: 'https://legacy-backend.example/api' });
  const seen = [];
  api.defaults.adapter = async (config) => {
    seen.push({ url: api.getUri(config), credentials: config.withCredentials });
    return { status: 200, statusText: 'OK', headers: {}, data: {}, config };
  };
  await api.post(
    '/auth/login',
    new URLSearchParams({ username: 'fixture@example.com', password: 'fixture' }),
  );
  await api.get('/auth/me');
  assert.deepEqual(seen, [
    { url: '/api/auth/login', credentials: true },
    { url: '/api/auth/me', credentials: true },
  ]);
});

test('all production builds keep the documented /api proxy path', async () => {
  for (const value of ['', '/wrong-path', 'http://localhost:8000/api', '//backend.example/api']) {
    const api = await client({ PROD: true, VITE_API_URL: value });
    assert.equal(api.defaults.baseURL, '/api');
  }
});

test('development keeps its explicit local API override and safe fallback', async () => {
  const local = await client({ PROD: false, VITE_API_URL: 'http://127.0.0.1:8001/api' });
  assert.equal(local.defaults.baseURL, 'http://127.0.0.1:8001/api');
  const fallback = await client({ PROD: false });
  assert.equal(fallback.defaults.baseURL, '/api');
});
