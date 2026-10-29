// This collector deliberately never records request headers, IPs, or event-level data.
export const VERSIONS = new Set(['0.3.0']);
export const CATEGORIES = new Set(['account', 'drafts', 'publishing', 'media', 'tags', 'analytics', 'comments', 'queue']);
const MAX_BYTES = 256;

async function readPayload(request) {
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
  const data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  if (!data || Array.isArray(data) || typeof data !== 'object'
      || Object.keys(data).sort().join(',') !== 'category,version'
      || !VERSIONS.has(data.version) || !CATEGORIES.has(data.category)) {
    throw new Error('invalid');
  }
  return data;
}

const response = (status) => new Response(null, {
  status, headers: { 'Cache-Control': 'no-store' },
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/v1/count' || url.search) return response(404);
    if (request.method !== 'POST') return response(405);
    if (request.headers.get('content-type') !== 'application/json') return response(415);
    let data;
    try {
      data = await readPayload(request);
    } catch {
      return response(400);
    }
    try {
      // Only UTC day, approved release version/category, and an aggregate count reach D1.
      const day = new Date().toISOString().slice(0, 10);
      const cutoff = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10);
      await env.COUNTS.batch([
        env.COUNTS.prepare('DELETE FROM daily_counts WHERE day < ?').bind(cutoff),
        env.COUNTS.prepare(`INSERT INTO daily_counts (day, version, category, count)
          VALUES (?, ?, ?, 1)
          ON CONFLICT(day, version, category) DO UPDATE SET count = count + 1`)
          .bind(day, data.version, data.category),
      ]);
      return response(204);
    } catch {
      return response(503);
    }
  },
};
