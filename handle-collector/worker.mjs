// Draft, undeployed, separate recipient/storage. No request/header/IP/event logging.
const MAX_BYTES = 256;
const TOKEN = /^[a-f0-9]{64}$/;
const HANDLE = /^[a-z0-9_]{1,15}$/;
const RETENTION_SECONDS = 90 * 86400;
const response = (status) => new Response(null, {
  status, headers: { 'Cache-Control': 'no-store' },
});

async function payload(request) {
  if (!request.body) throw new Error('invalid');
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) {
        await reader.cancel();
        throw new Error('invalid');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  if (!value || Array.isArray(value) || typeof value !== 'object'
      || typeof value.withdrawal_token !== 'string' || !TOKEN.test(value.withdrawal_token)) {
    throw new Error('invalid');
  }
  return value;
}

async function digest(token) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!['/v1/share', '/v1/withdraw'].includes(url.pathname) || url.search) return response(404);
    if (request.method !== 'POST') return response(405);
    if (request.headers.get('content-type') !== 'application/json') return response(415);
    let data;
    try {
      data = await payload(request);
      const keys = Object.keys(data).sort().join(',');
      if (url.pathname === '/v1/share') {
        if (keys !== 'consent_revision,handle,withdrawal_token'
            || typeof data.handle !== 'string' || !HANDLE.test(data.handle)
            || data.consent_revision !== '1') throw new Error('invalid');
      } else if (keys !== 'withdrawal_token') throw new Error('invalid');
    } catch {
      return response(400);
    }
    try {
      const hash = await digest(data.withdrawal_token);
      if (url.pathname === '/v1/withdraw') {
        // Idempotent, capability-authenticated removal; never accept a handle as authorization.
        await env.HANDLES.prepare('DELETE FROM shared_handles WHERE token_hash = ?').bind(hash).run();
        return response(204);
      }
      const now = Math.floor(Date.now() / 1000);
      await env.HANDLES.batch([
        env.HANDLES.prepare('DELETE FROM shared_handles WHERE expires_at <= ?').bind(now),
        env.HANDLES.prepare(`INSERT INTO shared_handles
          (token_hash, handle, consent_revision, expires_at) VALUES (?, ?, ?, ?)
          ON CONFLICT(token_hash) DO NOTHING`)
          .bind(hash, data.handle, data.consent_revision, now + RETENTION_SECONDS),
      ]);
      return response(201);
    } catch {
      return response(503);
    }
  },
  async scheduled(_controller, env) {
    await env.HANDLES.prepare('DELETE FROM shared_handles WHERE expires_at <= ?')
      .bind(Math.floor(Date.now() / 1000)).run();
  },
};
