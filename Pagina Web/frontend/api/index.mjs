import { isIP } from 'node:net';
// Same-origin API gateway for Vercel. Secrets are server configuration only.
// https://vercel.com/docs/functions/runtimes/node-js
export async function proxy(
  request,
  {
    origin = process.env.BACKEND_ORIGIN,
    secret = process.env.PROXY_SHARED_SECRET,
    trustedPlatform = process.env.VERCEL === '1',
    fetchImpl = fetch,
  } = {},
) {
  const failure = (status, detail) =>
    Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } });
  let backend;
  try {
    backend = new URL(origin);
    if (
      backend.protocol !== 'https:' ||
      backend.username ||
      backend.password ||
      backend.pathname !== '/' ||
      backend.search ||
      backend.hash
    )
      throw new Error();
  } catch {
    return failure(503, 'El servicio todavía no está configurado. Inténtalo más tarde.');
  }
  const incoming = new URL(request.url);
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(secret || ''))
    return failure(503, 'El servicio todavía no está configurado.');
  const path =
    incoming.pathname === '/api'
      ? '/api/' + (incoming.searchParams.get('__tickia_path') || '')
      : incoming.pathname;
  incoming.searchParams.delete('__tickia_path');
  if (!/^\/api\/[A-Za-z0-9_/-]+$/.test(path)) return failure(404, 'Ruta no encontrada.');
  if (!['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS'].includes(request.method))
    return failure(405, 'Método no permitido.');
  const headers = new Headers();
  if (trustedPlatform) {
    // Vercel overwrites this header at its edge. Never enable this trust on an
    // arbitrary server: https://vercel.com/docs/headers/request-headers
    const address = request.headers.get('x-forwarded-for')?.trim();
    if (!address || !isIP(address))
      return failure(503, 'No pudimos verificar el origen de la conexión.');
    headers.set('X-Tickia-Proxy-Secret', secret);
    headers.set('X-Tickia-Client-IP', address);
  }
  for (const key of ['content-type', 'accept', 'authorization', 'cookie', 'origin', 'user-agent']) {
    if (request.headers.has(key)) headers.set(key, request.headers.get(key));
  }
  let body;
  if (!['GET', 'HEAD'].includes(request.method)) {
    if (Number(request.headers.get('content-length')) > 6 * 1024 * 1024)
      return failure(413, 'La solicitud es demasiado grande.');
    body = await request.arrayBuffer();
    if (body.byteLength > 6 * 1024 * 1024) return failure(413, 'La solicitud es demasiado grande.');
  }
  try {
    const target = new URL(path + incoming.search, backend);
    const upstream = await fetchImpl(target, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
      signal: AbortSignal.timeout(25000),
    });
    if (upstream.status >= 300 && upstream.status < 400)
      return failure(502, 'El servicio devolvió una respuesta inesperada.');
    const responseHeaders = new Headers(upstream.headers);
    for (const key of ['content-length', 'content-encoding', 'transfer-encoding', 'connection'])
      responseHeaders.delete(key);
    responseHeaders.set('Cache-Control', 'no-store');
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return failure(502, 'No pudimos conectar con Tickia. Inténtalo otra vez.');
  }
}

export default { fetch: (request) => proxy(request) };
